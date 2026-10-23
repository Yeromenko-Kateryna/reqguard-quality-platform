#requires -Version 7.6
#requires -PSEdition Core
<#
Supplementary synthetic checks only. See docs/rg05/SUPPLEMENTARY_REPRODUCTION.md.
Do not dot-source. Each invocation requires independent execution authorization.
No protected-build, operational admission, cleanup, installation or retry.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('L1','L2','L3')][string]$Stage,
    [Parameter(Mandatory)][string]$WorkDirectory,
    [Parameter(Mandatory)][string]$MsvcRoot,
    [Parameter(Mandatory)][string]$SdkRoot,
    [Parameter(Mandatory)][string]$NodeHeaders,
    [Parameter(Mandatory)][string]$NodeLibrary,
    [Parameter(Mandatory)][string]$NodeExecutable,
    [string]$Addon,
    [string]$ExpectedAddonSha256
)

$locks = [Collections.Generic.List[IDisposable]]::new()
$identity = $null
$process = $null
$started = $false
$finished = $false
$startAttempted = $false
$startRejected = $false
$retainRecovery = $false
$dedicatedHost = $false
$launchLog = $null
$launchState = $null
$outTask = $null
$errTask = $null
$receipt = $null
# A pending recovery belongs to this new host, never to the historical session.
if (Get-Variable -Name RG05SupplementaryRecovery -Scope Global -ErrorAction SilentlyContinue) {
    Write-Output 'RG05_RECOVERY_PENDING_NO_RETRY'
    return
}
try {
    Set-StrictMode -Version Latest
    $ErrorActionPreference = 'Stop'
    $WarningPreference = 'Stop'
    $VerbosePreference = 'SilentlyContinue'
    $DebugPreference = 'SilentlyContinue'
    if ($ExecutionContext.SessionState.LanguageMode -ne 'FullLanguage' -or
        $PSDefaultParameterValues.Count -ne 0 -or
        $PSVersionTable.PSVersion.ToString() -ne '7.6.5' -or
        -not [Environment]::Is64BitProcess -or -not $IsWindows) { throw 'CONTEXT' }
    # -NoExit keeps a recovery prompt alive if start/exit cannot be confirmed.
    # Known success/failure explicitly exits below; an unknown child never does.
    $hostArguments = [Environment]::GetCommandLineArgs()
    $fileArgument = [Array]::IndexOf([string[]]$hostArguments,'-File')
    if ('-NoExit' -notin $hostArguments -or $fileArgument -lt 0 -or
        $fileArgument+1 -ge $hostArguments.Length -or
        [IO.Path]::GetFullPath($hostArguments[$fileArgument+1]) -ine $PSCommandPath) {
        throw 'RECOVERY_HOST_REQUIRED'
    }
    $dedicatedHost = $true
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $impersonated = [Security.Principal.WindowsIdentity]::GetCurrent($true)
    if ($null -ne $impersonated) { $impersonated.Dispose(); throw 'IMPERSONATION' }
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $identity.IsAuthenticated -or
        $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'TOKEN' }
    $systemSid = [Security.Principal.SecurityIdentifier]::new(
        [Security.Principal.WellKnownSidType]::LocalSystemSid, $null)
    $adminSid = [Security.Principal.SecurityIdentifier]::new(
        [Security.Principal.WellKnownSidType]::BuiltinAdministratorsSid, $null)
    $installerSid = [Security.Principal.NTAccount]::new('NT SERVICE','TrustedInstaller').
        Translate([Security.Principal.SecurityIdentifier])
    $trusted = @($identity.User.Value, $systemSid.Value, $adminSid.Value, $installerSid.Value)

    function Canonical([string]$Path) {
        if ($Path -notmatch '^[A-Za-z]:\\' -or $Path.Substring(2).Contains(':') -or
            $Path -match '[/*?"<>|\x00-\x1f~]' -or
            $Path -match '(^|\\)(\.\.?|[^\\]*[. ])(\\|$)') { throw 'PATH' }
        $full = [IO.Path]::GetFullPath($Path)
        $comparison = $Path
        if ($full.Length -gt 3) { $full = $full.TrimEnd('\') }
        if ($comparison.Length -gt 3) { $comparison = $comparison.TrimEnd('\') }
        if ($full -ine $comparison) { throw 'ALIAS' }
        return $full
    }
    function Within([string]$Path, [string]$Root) {
        return $Path -ieq $Root -or $Path.StartsWith($Root.TrimEnd('\')+'\',
            [StringComparison]::OrdinalIgnoreCase)
    }
    function CheckPath([string]$Path) {
        $full = Canonical $Path
        $item = Get-Item -LiteralPath $full -Force
        $first = $true
        while ($null -ne $item) {
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'REPARSE' }
            $acl = Get-Acl -LiteralPath $item.FullName
            # Every owner matters: an ancestor owner can change its DACL even
            # without an explicit Allow ACE. Unknown metadata fails closed.
            if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $trusted) {
                throw 'OWNER'
            }
            $mask = if ($first) { 0xD0156 } else { 0xD0040 }
            foreach ($ace in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])) {
                if ($ace.AccessControlType -eq 'Allow' -and
                    -not ($ace.PropagationFlags -band
                        [Security.AccessControl.PropagationFlags]::InheritOnly) -and
                    ([int]$ace.FileSystemRights -band $mask) -ne 0 -and
                    $ace.IdentityReference.Value -notin $trusted) { throw 'WRITER' }
            }
            if ($item -is [IO.FileInfo]) { $item = $item.Directory }
            else { $item = $item.Parent }
            $first = $false
        }
        $drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($full))
        if ($drive.DriveType -ne 'Fixed' -or $drive.DriveFormat -ne 'NTFS') { throw 'STORAGE' }
        return $full
    }
    function Hash([string]$Path) {
        return (Microsoft.PowerShell.Utility\Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    }
    function Pin([string]$Path, [string]$Expected) {
        $full = CheckPath $Path
        $stream = [IO.File]::Open($full,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
        $locks.Add($stream)
        if ((Hash $full) -cne $Expected) { throw 'HASH' }
        return $full
    }
    $repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    $source = Pin (Join-Path $repo 'quality\api\scripts\rg05-v2-win32.cc') '9308AD1EB738BAE7B71D5E9A8A4C0916F5302429771B5D0B7BDE4934045274D6'
    $test = Pin (Join-Path $repo 'quality\api\tests\rg05-v2-win32-negative.test.ts') '82F2001E118482CFDD0800E116D7CC317D57F36FFA084FD146B5D4BB6C1E4A6C'
    $cl = Pin (Join-Path $MsvcRoot 'bin\Hostx64\x64\cl.exe') 'FE251EF50A1545B1B0835EE17B1E785459712B38D79E45B5C1D3D28970A36619'
    $link = Pin (Join-Path $MsvcRoot 'bin\Hostx64\x64\link.exe') 'A364AF801A8539E4324D9489313DBF001D959128451FC99A27B24676BBAC058F'
    $node = Pin $NodeExecutable '3331E1FFE19874215472217C5E94F5A0C6D8E18C4AC7111D3937AA0AD5E9B4A5'
    $nodeLib = Pin $NodeLibrary '2DAD98CD40967A4FD4A97195979E0E237E09EC292483700A51D2C20FE5A97C87'
    $headerHashes = @{
        'node_api.h'='2D4560831E525B47B060EC8A0864AB73993DF9E20215CE9F0FE7B24CD31AF32A'
        'node_api_types.h'='A25356630D3058F0A0C8937D9F297E9471E037FDA58C2696D8A505C2BD99CB00'
        'js_native_api.h'='EB03B6C850A1CFB593FD03E9E4251DB8C82E9A6D9705BCA91AC8D1A01FD7037C'
        'js_native_api_types.h'='7DD3663630849ADA3A30D39ABF42A192C9B6E7DE63017CD32C41F5371A475B34'
        'node_version.h'='F956E28E9D4F73F60E5A3E7B65AE199D49728DFDEC19E5A2CB31D7A79DB3DE1E'
    }
    foreach ($name in $headerHashes.Keys) { $null = Pin (Join-Path $NodeHeaders $name) $headerHashes[$name] }
    $includes = @((CheckPath (Join-Path $MsvcRoot 'include')), (CheckPath $NodeHeaders))
    foreach ($part in @('ucrt','shared','um')) {
        $includes += CheckPath (Join-Path $SdkRoot ('Include\10.0.26100.0\'+$part))
    }
    $libraries = @((CheckPath (Join-Path $MsvcRoot 'lib\x64')),
        (CheckPath (Join-Path $SdkRoot 'Lib\10.0.26100.0\ucrt\x64')),
        (CheckPath (Join-Path $SdkRoot 'Lib\10.0.26100.0\um\x64')))
    foreach ($required in @((Join-Path $libraries[0] 'msvcprt.lib'),
        (Join-Path $libraries[0] 'vcruntime.lib'),(Join-Path $libraries[1] 'ucrt.lib'),
        (Join-Path $libraries[2] 'kernel32.lib'))) { $null = CheckPath $required }
    if ((Get-Item -LiteralPath $cl).VersionInfo.FileVersion -ne '19.44.35229.0' -or
        (Get-Item -LiteralPath $link).VersionInfo.FileVersion -ne '14.44.35229.0' -or
        (Get-Item -LiteralPath $node).VersionInfo.FileVersion -ne '24.15.0') { throw 'VERSION' }
    foreach ($key in @('CL','_CL_','LINK','_LINK_','INCLUDE','LIB','LIBPATH',
        'NODE_OPTIONS','NODE_PATH','NODE_V8_COVERAGE','NODE_COMPILE_CACHE')) {
        if ([Environment]::GetEnvironmentVariable($key,'Process')) { throw 'AMBIENT' }
    }
    if ($null -ne [Environment]::GetEnvironmentVariable('NODE_REDIRECT_WARNINGS','Process')) {
        throw 'WARNING_REDIRECTION'
    }
    $work = Canonical $WorkDirectory
    if (Test-Path -LiteralPath $work) { throw 'COLLISION' }
    $parent = CheckPath ([IO.Path]::GetDirectoryName($work))
    if ((Within $work $repo) -or (Within $repo $work) -or
        $work -match '(?i)(onedrive|dropbox|icloud|google drive|reqguardlocal|\.runtime|reqguard[_-]rg05|rg05-v[12])') {
        throw 'WORK_BOUNDARY'
    }
    foreach ($key in @('OneDrive','OneDriveConsumer','OneDriveCommercial')) {
        $sync = [Environment]::GetEnvironmentVariable($key,'Process')
        if ($sync -and (Within $work $sync)) { throw 'SYNC' }
    }
    # Add-Type bootstrap may use existing TEMP. No environment variables are
    # cleared or changed. A protected, existing bootstrap TEMP is a prerequisite.
    foreach ($key in @('TEMP','TMP')) {
        $temp = [Environment]::GetEnvironmentVariable($key,'Process')
        if (-not $temp) { throw 'BOOTSTRAP_TEMP' }
        $null = CheckPath $temp
        if ((Within $temp $repo) -or $temp -match '(?i)(onedrive|\.runtime|reqguardlocal)') { throw 'BOOTSTRAP_TEMP' }
    }
    if ($Stage -eq 'L3') {
        if ($ExpectedAddonSha256 -cnotmatch '^[A-F0-9]{64}$') { throw 'ADDON_HASH_REQUIRED' }
        $binary = Pin $Addon $ExpectedAddonSha256
        if ((Within $binary $repo) -or (Within $binary $work)) { throw 'ADDON_BOUNDARY' }
        $l2Path = CheckPath (Join-Path ([IO.Path]::GetDirectoryName($binary)) 'result.json')
        $l2 = Microsoft.PowerShell.Utility\ConvertFrom-Json -InputObject ([IO.File]::ReadAllText($l2Path))
        if ($l2.schema -cne 'RG05-FRESH-SUPPLEMENTARY-1' -or $l2.stage -cne 'L2' -or
            $l2.exit_code -ne 0 -or $l2.artifact_verified -ne $true -or
            $l2.binary_sha256 -cne $ExpectedAddonSha256) { throw 'L2_RECEIPT' }
    } elseif ($Addon -or $ExpectedAddonSha256) { throw 'UNUSED_ADDON' }
    if ($null -ne ('RG05.SupplementaryDirectory' -as [type])) { throw 'FRESH_PROCESS_REQUIRED' }
    Microsoft.PowerShell.Utility\Add-Type -Language CSharp -ErrorAction Stop -WarningAction Stop -Verbose:$false -Debug:$false -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace RG05 {
 public static class SupplementaryDirectory {
  [StructLayout(LayoutKind.Sequential)] struct SA {
   public int length; public IntPtr descriptor; public int inherit;
  }
  [DllImport("advapi32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  static extern bool ConvertStringSecurityDescriptorToSecurityDescriptorW(
   string text, uint revision, out IntPtr descriptor, out uint size);
  [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  static extern bool CreateDirectoryW(string path, ref SA attributes);
  [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr value);
  public static void Create(string path, string sddl) {
   IntPtr sd=IntPtr.Zero; uint size;
   try {
    if(!ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl,1,out sd,out size))
     throw new InvalidOperationException("CREATE_SECURITY");
    var sa=new SA {length=Marshal.SizeOf<SA>(),descriptor=sd,inherit=0};
    if(!CreateDirectoryW(path,ref sa)) throw new InvalidOperationException("CREATE_FAILED");
   } finally {if(sd!=IntPtr.Zero) LocalFree(sd);}
  }
 }
}
'@
    $sddl = 'O:'+$identity.User.Value+'D:P(A;OICI;FA;;;'+$identity.User.Value+
        ')(A;OICI;FA;;;'+$systemSid.Value+')(A;OICI;FA;;;'+$adminSid.Value+')'
    [RG05.SupplementaryDirectory]::Create($work,$sddl)
    $null = CheckPath $work
    $acl = Get-Acl -LiteralPath $work
    $expectedPrincipals = @($identity.User.Value,$systemSid.Value,$adminSid.Value)
    $rules = @($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]))
    if (-not $acl.AreAccessRulesProtected -or
        -not $acl.AreAccessRulesCanonical -or
        $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $identity.User.Value -or
        $rules.Count -ne 3) { throw 'OUTPUT_ACL' }
    $seenPrincipals = [Collections.Generic.HashSet[string]]::new()
    foreach ($rule in $rules) {
        if ($rule.IdentityReference.Value -notin $expectedPrincipals -or
            -not $seenPrincipals.Add($rule.IdentityReference.Value) -or
            $rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
            $rule.IsInherited -or
            [int]$rule.FileSystemRights -ne [int][Security.AccessControl.FileSystemRights]::FullControl -or
            [int]$rule.InheritanceFlags -ne [int](
                [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
                [Security.AccessControl.InheritanceFlags]::ObjectInherit) -or
            $rule.PropagationFlags -ne [Security.AccessControl.PropagationFlags]::None) {
            throw 'OUTPUT_ACE'
        }
    }
    # Children inherit only from this already-protected, newly created root.
    $inputDir = Join-Path $work 'input'
    $null = [IO.Directory]::CreateDirectory($inputDir)
    $snapshot = Join-Path $inputDir 'rg05-v2-win32.cc'
    [IO.File]::Copy($source,$snapshot,$false)
    $null = Pin $snapshot (Hash $source)
    $nodeSnapshot = Join-Path $inputDir 'node'
    $null = [IO.Directory]::CreateDirectory($nodeSnapshot)
    foreach ($name in $headerHashes.Keys) {
        $dest = Join-Path $nodeSnapshot $name
        [IO.File]::Copy((Join-Path $NodeHeaders $name),$dest,$false)
        $null = Pin $dest $headerHashes[$name]
    }
    $includes[1] = $nodeSnapshot
    $common = @('/nologo','/TP','/std:c++17','/MD','/EHsc','/W4','/X',
        '/DNAPI_VERSION=8','/DRG05_SYNTHETIC_ONLY=1','/DWIN32_LEAN_AND_MEAN','/DNOMINMAX')
    foreach ($include in $includes) { $common += '/I'+$include }
    $exe = $cl
    if ($Stage -eq 'L1') { $arguments = $common + @('/Zs',$snapshot) }
    elseif ($Stage -eq 'L2') {
        $binary = Join-Path $work 'rg05-v2-win32.node'
        $arguments = $common + @('/LD',('/Fo'+(Join-Path $work 'rg05-v2-win32.obj')),
            ('/Fd'+(Join-Path $work 'compile.pdb')),$snapshot,'/link','/MACHINE:X64',
            '/INCREMENTAL:NO','/MANIFEST:NO',('/OUT:'+$binary),
            ('/IMPLIB:'+(Join-Path $work 'rg05-v2-win32.lib')),
            ('/PDB:'+(Join-Path $work 'link.pdb')),$nodeLib,'kernel32.lib')
        foreach ($library in $libraries) { $arguments += '/LIBPATH:'+$library }
    } else {
        $testDir = Join-Path $work 'snapshot\quality\api\tests'
        $null = [IO.Directory]::CreateDirectory($testDir)
        $testSnapshot = Join-Path $testDir 'rg05-v2-win32-negative.test.ts'
        [IO.File]::Copy($test,$testSnapshot,$false)
        $null = Pin $testSnapshot (Hash $test)
        $guard = 'if(process.version!=="v24.15.0"||process.platform!=="win32"||process.arch!=="x64"||Number(process.versions.napi)<8)throw Error("RUNTIME");'
        $exe = $node
        $arguments = @('--experimental-strip-types','--test','--test-isolation=none',
            '--test-concurrency=1','--test-reporter=tap','--test-timeout=30000',
            '--import',('data:text/javascript,'+[Uri]::EscapeDataString($guard)),$testSnapshot)
    }
    $psi = [Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $exe
    $psi.WorkingDirectory = $work
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    foreach ($argument in $arguments) { $psi.ArgumentList.Add($argument) }
    # Child-only environment. OneDrive variables and parent environment stay intact.
    foreach ($key in @('CL','_CL_','LINK','_LINK_','INCLUDE','LIB','LIBPATH','NODE_OPTIONS',
        'NODE_PATH','NODE_V8_COVERAGE','NODE_COMPILE_CACHE','NODE_REDIRECT_WARNINGS',
        'RG05_SYNTHETIC_ADDON')) {
        $null = $psi.Environment.Remove($key)
    }
    $psi.Environment['PATH'] = [IO.Path]::GetDirectoryName($exe)+';'+
        [IO.Path]::GetDirectoryName($cl)+';'+$env:SystemRoot+'\System32;'+$env:SystemRoot
    $psi.Environment['TEMP'] = $work
    $psi.Environment['TMP'] = $work
    $psi.Environment['NODE_DISABLE_COMPILE_CACHE'] = '1'
    if ($Stage -eq 'L3') { $psi.Environment['RG05_SYNTHETIC_ADDON'] = $binary }
    $stdout = [IO.File]::Open((Join-Path $work 'stdout.bin'),[IO.FileMode]::CreateNew)
    $locks.Add($stdout)
    $stderr = [IO.File]::Open((Join-Path $work 'stderr.bin'),[IO.FileMode]::CreateNew)
    $locks.Add($stderr)
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $psi
    # Private append-only launch evidence precedes Start. Full paths and process
    # identities remain local to this protected directory, never public output.
    $hostProcess = [Diagnostics.Process]::GetCurrentProcess()
    try { $hostStart = $hostProcess.StartTime.ToUniversalTime().ToString('O') }
    finally { $hostProcess.Dispose() }
    $launchState = [ordered]@{
        schema='RG05-PRIVATE-LAUNCH-1'; launch_id=[guid]::NewGuid().ToString('N')
        stage=$Stage; state='PREPARED'; runner_pid=$PID; runner_start_utc=$hostStart
        executable=$exe; executable_sha256=(Hash $exe); arguments=[string[]]$arguments
        child_pid=$null; child_start_utc=$null; exit_code=$null
    }
    $launchLog = [IO.File]::Open((Join-Path $work 'launch.jsonl'),[IO.FileMode]::CreateNew,
        [IO.FileAccess]::Write,[IO.FileShare]::Read)
    function RecordLaunch([string]$State) {
        $launchState.state = $State
        $line = Microsoft.PowerShell.Utility\ConvertTo-Json -InputObject $launchState -Depth 5 -Compress
        $bytes = [Text.Encoding]::UTF8.GetBytes($line+[char]10)
        $launchLog.Write($bytes)
        $launchLog.Flush($true)
    }
    RecordLaunch 'PREPARED'
    RecordLaunch 'START_ATTEMPTED'
    $startAttempted = $true
    $started = $process.Start()
    if (-not $started) {
        $startRejected = $true
        RecordLaunch 'START_REJECTED'
        throw 'START'
    }
    # Store PID first; if querying creation time fails, the live wrapper and
    # runner identity are still retained until a confirmed exit or recovery.
    $launchState.child_pid = $process.Id
    RecordLaunch 'START_CONFIRMED'
    $launchState.child_start_utc = $process.StartTime.ToUniversalTime().ToString('O')
    RecordLaunch 'START_IDENTITY_CONFIRMED'
    $outTask = $process.StandardOutput.BaseStream.CopyToAsync($stdout)
    $errTask = $process.StandardError.BaseStream.CopyToAsync($stderr)
    if (-not $process.WaitForExit(120000)) { throw 'TIMEOUT' }
    $finished = $true
    $launchState.exit_code = $process.ExitCode
    RecordLaunch 'EXIT_CONFIRMED'
    if (-not [Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]@($outTask,$errTask),30000)) { throw 'CAPTURE_TIMEOUT' }
    $stdout.Flush($true); $stderr.Flush($true)
    $stdout.Dispose(); $stderr.Dispose()
    $exitCode = $process.ExitCode
    # Preserve completion/exit/capture evidence even if later artifact checks fail.
    $completion = [ordered]@{
        stage=$Stage; exit_code=$exitCode; process_completed=$finished; capture_completed=$true
        argv_sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData(
            [Text.Encoding]::UTF8.GetBytes([string]::Join([string][char]0,[string[]]$arguments))))
        stdout_bytes=(Get-Item -LiteralPath (Join-Path $work 'stdout.bin')).Length
        stderr_bytes=(Get-Item -LiteralPath (Join-Path $work 'stderr.bin')).Length
        stdout_sha256=(Hash (Join-Path $work 'stdout.bin'))
        stderr_sha256=(Hash (Join-Path $work 'stderr.bin'))
    }
    $completionFile = [IO.File]::Open((Join-Path $work 'process.json'),[IO.FileMode]::CreateNew)
    try {
        $data = [Text.Encoding]::UTF8.GetBytes(
            (Microsoft.PowerShell.Utility\ConvertTo-Json -InputObject $completion -Compress))
        $completionFile.Write($data); $completionFile.Flush($true)
    } finally { $completionFile.Dispose() }
    $artifactVerified = $false
    if ($exitCode -ne 0) { throw 'CHILD_EXIT' }
    if ($Stage -eq 'L1') {
        if (@(Get-ChildItem -LiteralPath $work -File | Where-Object {$_.Extension -in @('.obj','.node','.exe','.dll','.pdb','.lib','.exp')}).Count) {
            throw 'L1_ARTIFACT'
        }
        $artifactVerified = $true
    } elseif ($Stage -eq 'L2') {
        # Read PE tables without loading the DLL or executing dumpbin.
        $b = [IO.File]::ReadAllBytes($binary)
        function U16([int]$o) { return [BitConverter]::ToUInt16($b,$o) }
        function U32([int]$o) { return [BitConverter]::ToUInt32($b,$o) }
        $pe = U32 60; $opt = $pe+24; $section = $opt+(U16 ($pe+20))
        if ((U16 0) -ne 0x5A4D -or (U32 $pe) -ne 0x4550 -or
            (U16 ($pe+4)) -ne 0x8664 -or (U16 $opt) -ne 0x20B -or
            -not ((U16 ($pe+22)) -band 0x2000)) { throw 'PE' }
        function Offset([uint32]$rva) {
            for ($i=0;$i -lt (U16 ($pe+6));$i++) {
                $s=$section+40*$i; $va=U32 ($s+12)
                $size=[Math]::Max((U32 ($s+8)),(U32 ($s+16)))
                if ($rva -ge $va -and $rva-$va -lt $size) { return (U32 ($s+20))+$rva-$va }
            }
            throw 'RVA'
        }
        $exportRva = U32 ($opt+112); $exportSize = U32 ($opt+116)
        $exports = Offset $exportRva
        $count = U32 ($exports+24); $names = Offset (U32 ($exports+32))
        $ordinals = Offset (U32 ($exports+36)); $functions = Offset (U32 ($exports+28))
        $found = @()
        if ($count -gt 10000) { throw 'EXPORT_COUNT' }
        for ($i=0;$i -lt $count;$i++) {
            $start = Offset (U32 ($names+4*$i)); $end = $start
            while ($b[$end] -ne 0 -and $end-$start -lt 256) { $end++ }
            $name = [Text.Encoding]::ASCII.GetString($b,$start,$end-$start)
            $ordinal = U16 ($ordinals+2*$i)
            if ($ordinal -ge (U32 ($exports+20))) { throw 'EXPORT_ORDINAL' }
            $address = U32 ($functions+4*$ordinal)
            if ($address -eq 0 -or ($address -ge $exportRva -and
                $address-$exportRva -lt $exportSize)) { throw 'FORWARDED_EXPORT' }
            $found += $name
        }
        foreach ($name in @('napi_register_module_v1','node_api_module_get_api_version_v1')) {
            if ($name -notin $found) { throw 'EXPORT_MISSING' }
        }
        $artifactVerified = $true
    } else {
        $tap = [IO.File]::ReadAllText((Join-Path $work 'stdout.bin'))
        $titles = @([regex]::Matches([IO.File]::ReadAllText($testSnapshot),"(?m)^test\('([^']+)'") |
            ForEach-Object {$_.Groups[1].Value})
        $results = @([regex]::Matches($tap,'(?m)^ok (\d+) - ([^\r\n]+)'))
        # Directives belong to result lines; "# todo 0" is a summary, not TODO.
        $directivePattern = '(?im)^[ \t]*(?:not[ \t]+)?ok[ \t]+\d+\b[^\r\n]*[ \t]+#[ \t]*(?:SKIP|TODO)\b'
        if ($titles.Count -ne 18 -or $results.Count -ne 18 -or
            $tap -match '(?im)^[ \t]*not ok\b|^[ \t]*Bail out!' -or
            $tap -match $directivePattern) { throw 'TAP' }
        for ($i=0;$i -lt 18;$i++) {
            if ([int]$results[$i].Groups[1].Value -ne $i+1 -or
                $results[$i].Groups[2].Value -cne $titles[$i]) { throw 'TAP_TITLE' }
        }
        foreach ($line in @('1..18','# tests 18','# suites 0','# pass 18','# fail 0',
            '# cancelled 0','# skipped 0','# todo 0')) {
            if ([regex]::Matches($tap,'(?m)^'+[regex]::Escape($line)+'\r?$').Count -ne 1) { throw 'TAP_TOTAL' }
        }
        $artifactVerified = $true
    }
    $receipt = [ordered]@{
        schema='RG05-FRESH-SUPPLEMENTARY-1'; stage=$Stage
        scope='supplementary synthetic only'; exit_code=$exitCode
        powershell=$PSVersionTable.PSVersion.ToString()
        windows_version=[Environment]::OSVersion.Version.ToString()
        cl_version=(Get-Item -LiteralPath $cl).VersionInfo.FileVersion
        linker_version=(Get-Item -LiteralPath $link).VersionInfo.FileVersion
        node_file_version=(Get-Item -LiteralPath $node).VersionInfo.FileVersion
        sdk='10.0.26100.0'; msvc_toolset='14.44.35207'
        process_completed=$finished; capture_completed=$true; artifact_verified=$artifactVerified
        source_sha256=(Hash $source); test_sha256=(Hash $test)
        cl_sha256=(Hash $cl); linker_sha256=(Hash $link); node_sha256=(Hash $node)
        argv_sha256=$completion.argv_sha256
        node_library_sha256=(Hash $nodeLib); node_headers=$headerHashes
        stdout_bytes=(Get-Item -LiteralPath (Join-Path $work 'stdout.bin')).Length
        stderr_bytes=(Get-Item -LiteralPath (Join-Path $work 'stderr.bin')).Length
        stdout_sha256=(Hash (Join-Path $work 'stdout.bin'))
        stderr_sha256=(Hash (Join-Path $work 'stderr.bin'))
        binary_sha256=$(if ($Stage -ne 'L1') { Hash $binary } else { $null })
        protected_build_claim=$false; operational_security_claim=$false
    }
} catch {
    # Diagnostics stay private in output streams. Never print raw exceptions.
    $receipt = $null
    Write-Output 'RG05_SUPPLEMENTARY_BLOCKED'
} finally {
    if ($startAttempted -and -not $startRejected -and -not $finished) {
        try {
            if ($process.HasExited) {
                $finished = $true
                $launchState.exit_code = $process.ExitCode
                RecordLaunch 'EXIT_CONFIRMED'
            }
        } catch { } # Unknown is retained, never interpreted as no child.
        if (-not $finished) { $retainRecovery = $true }
    }
    foreach ($task in @($outTask,$errTask)) {
        if ($null -ne $task -and -not $task.IsCompleted) { $retainRecovery=$true }
    }
    if ($retainRecovery) {
        $receipt = $null
        try {
            if ($finished) { RecordLaunch 'EXIT_CONFIRMED_CAPTURE_PENDING' }
            else { RecordLaunch 'UNKNOWN_PROCESS_STATE' }
        } catch { Write-Output 'RG05_LAUNCH_LOG_INCOMPLETE' }
        $global:RG05SupplementaryRecovery = [pscustomobject]@{
            Process=$process; Launch=$launchState; LaunchLog=$launchLog
            PinnedResources=$locks; RunnerIdentity=$identity
            StdoutTask=$outTask; StderrTask=$errTask; WorkDirectory=$work
            ExitConfirmed=$finished; RetryProhibited=$true
        }
        Write-Output 'RG05_RECOVERY_REQUIRED_NO_RETRY'
    } else {
        if ($null -ne $process) {
            try { $process.Dispose() } catch { $receipt=$null }
        }
        foreach ($handle in $locks) {
            try { $handle.Dispose() } catch { $receipt=$null }
        }
        if ($null -ne $launchLog) {
            try { $launchLog.Dispose() } catch { $receipt=$null }
        }
        if ($null -ne $identity) {
            try { $identity.Dispose() } catch { $receipt=$null }
        }
    }
}
if ($retainRecovery) { return } # -NoExit retains this host and ownership object.
# Publish only after successful process completion, verification and disposal.
if ($null -eq $receipt) {
    if ($dedicatedHost) { [Environment]::Exit(1) }
    exit 1
}
try {
    $json = Microsoft.PowerShell.Utility\ConvertTo-Json -InputObject $receipt -Depth 8 -Compress
    $bytes = [Text.Encoding]::UTF8.GetBytes($json)
    $file = [IO.File]::Open((Join-Path $work 'result.json'),[IO.FileMode]::CreateNew)
    try { $file.Write($bytes); $file.Flush($true) } finally { $file.Dispose() }
    if ((Hash (Join-Path $work 'result.json')) -cne
        [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes))) { throw 'READBACK' }
    Write-Output ('RG05_'+$Stage+'_SUPPLEMENTARY_PASS')
} catch { Write-Output 'RG05_EVIDENCE_CAPTURE_FAILED'; [Environment]::Exit(1) }
# Only the dedicated child PowerShell host ends, after owned-resource disposal.
# This branch is unreachable while recovery owns a possibly live child.
[Environment]::Exit(0)
