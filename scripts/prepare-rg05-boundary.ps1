#requires -Version 7.6
#requires -PSEdition Core
<#
Preparation only. Inspect and Prepare require separate authorization.
Use a reviewed local copy in a fresh authenticated interactive -NoProfile -File
PowerShell process. Never dot-source, run from sync storage, or reuse partials.
Inspect uses metadata and read-only Windows storage commands; no Add-Type/writes.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('Inspect','Prepare')][string]$Mode,
    [Parameter(Mandatory)][string]$DonorRoot,
    [Parameter(Mandatory)][string]$NodeHeaders,
    [Parameter(Mandatory)][string]$NodeLibrary,
    [Parameter(Mandatory)][string]$MsvcRoot,
    [Parameter(Mandatory)][string]$SdkRoot,
    [Parameter(Mandatory)][string]$NodeExecutable,
    [string]$ParentDirectory = 'C:\'
)

$owned = $null
$identity = $null
$gate = $false
$created = $false
$result = $null
try {
    Set-StrictMode -Version Latest
    $ErrorActionPreference='Stop'
    $WarningPreference='Stop'
    $VerbosePreference='SilentlyContinue'
    $DebugPreference='SilentlyContinue'
    if ($ExecutionContext.SessionState.LanguageMode -ne 'FullLanguage' -or
        $PSDefaultParameterValues.Count -ne 0 -or -not $IsWindows -or
        -not [Environment]::Is64BitProcess -or
        $PSVersionTable.PSVersion.ToString() -ne '7.6.5' -or
        -not [Environment]::UserInteractive -or [Console]::IsInputRedirected) { throw 'HOST' }
    $argsHost=[Environment]::GetCommandLineArgs()
    $fileIndex=[Array]::IndexOf([string[]]$argsHost,'-File')
    if ('-NoProfile' -notin $argsHost -or $fileIndex -lt 0 -or
        $fileIndex+1 -ge $argsHost.Length -or
        [IO.Path]::GetFullPath($argsHost[$fileIndex+1]) -ine $PSCommandPath) { throw 'ENTRYPOINT' }
    $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
    $impersonation=[Security.Principal.WindowsIdentity]::GetCurrent($true)
    if ($null -ne $impersonation) { $impersonation.Dispose(); throw 'IMPERSONATION' }
    $principal=[Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $identity.IsAuthenticated -or
        $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'TOKEN' }
    $system=[Security.Principal.SecurityIdentifier]::new(
        [Security.Principal.WellKnownSidType]::LocalSystemSid,$null)
    $admins=[Security.Principal.SecurityIdentifier]::new(
        [Security.Principal.WellKnownSidType]::BuiltinAdministratorsSid,$null)
    $installer=[Security.Principal.NTAccount]::new('NT SERVICE','TrustedInstaller').
        Translate([Security.Principal.SecurityIdentifier])
    $trusted=@($identity.User.Value,$system.Value,$admins.Value,$installer.Value)
    $owned=[Collections.Generic.List[IDisposable]]::new()
    foreach ($key in @('CL','_CL_','LINK','_LINK_','INCLUDE','LIB','LIBPATH',
        'NODE_OPTIONS','NODE_PATH','NODE_V8_COVERAGE','NODE_COMPILE_CACHE',
        'NODE_REDIRECT_WARNINGS','DOTNET_STARTUP_HOOKS','DOTNET_ADDITIONAL_DEPS',
        'DOTNET_SHARED_STORE','COR_ENABLE_PROFILING','CORECLR_ENABLE_PROFILING')) {
        if ($null -ne [Environment]::GetEnvironmentVariable($key,'Process')) { throw 'AMBIENT' }
    }

    function Canonical([string]$Path) {
        if ($Path -notmatch '^[A-Za-z]:\\' -or $Path.Substring(2).Contains(':') -or
            $Path -match '[/*?"<>|~%\x00-\x1f]' -or
            $Path -match '(^|\\)(\.\.?|[^\\]*[. ])(\\|$)') { throw 'PATH' }
        $full=[IO.Path]::GetFullPath($Path)
        if ($full.Length -gt 3) { $full=$full.TrimEnd('\') }
        if ($full -ine $Path.TrimEnd('\') -and $full -ine $Path) { throw 'ALIAS' }
        # Keep bootstrap/storage resolution deliberately limited to one volume.
        if ([IO.Path]::GetPathRoot($full) -ine 'C:\') { throw 'UNSUPPORTED_VOLUME' }
        return $full
    }
    function Within([string]$Path,[string]$Root) {
        return $Path -ieq $Root -or $Path.StartsWith($Root.TrimEnd('\')+'\',
            [StringComparison]::OrdinalIgnoreCase)
    }
    function NoSync([string]$Path) {
        if ($Path -match '(?i)(onedrive|dropbox|icloud|google drive)|(^|\\)(reqguardlocal|\.runtime|reqguard[_-]rg05[^\\]*|rg05-v[12])(\\|$)') {
            throw 'RESERVED_OR_SYNC'
        }
        foreach ($root in $syncRoots) { if (Within $Path $root) { throw 'SYNC' } }
    }
    function ReadSyncRoots {
        $roots=[Collections.Generic.List[string]]::new()
        $bases=@(
            @{Hive=[Microsoft.Win32.Registry]::CurrentUser;Key='Software\SyncEngines\Providers';Kind='Providers'},
            @{Hive=[Microsoft.Win32.Registry]::LocalMachine;Key='SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\SyncRootManager';Kind='Manager'}
        )
        foreach ($entry in $bases) {
            $base=$entry.Hive.OpenSubKey($entry.Key,$false)
            if ($null -eq $base) { continue } # A successful null result means absent.
            try {
                foreach ($name in $base.GetSubKeyNames()) {
                    $provider=$base.OpenSubKey($name,$false)
                    if ($null -eq $provider) { throw 'REGISTRY_RACE' }
                    try {
                        if ($entry.Kind -eq 'Providers') {
                            $mount=$provider.GetValue('MountPoint',$null,
                                [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
                            if ($mount -isnot [string] -or -not $mount) { throw 'UNRESOLVED_PROVIDER' }
                            $roots.Add((Canonical ([Environment]::ExpandEnvironmentVariables($mount))))
                        } else {
                            $userRoots=$provider.OpenSubKey('UserSyncRoots',$false)
                            if ($null -eq $userRoots) { throw 'UNRESOLVED_PROVIDER' }
                            try {
                                foreach ($valueName in $userRoots.GetValueNames()) {
                                    $mount=$userRoots.GetValue($valueName,$null,
                                        [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
                                    if ($mount -isnot [string] -or -not $mount) { throw 'UNRESOLVED_ROOT' }
                                    $roots.Add((Canonical ([Environment]::ExpandEnvironmentVariables($mount))))
                                }
                            } finally { $userRoots.Dispose() }
                        }
                    } finally { $provider.Dispose() }
                }
            } finally { $base.Dispose() }
        }
        foreach ($key in @('OneDrive','OneDriveConsumer','OneDriveCommercial')) {
            $root=[Environment]::GetEnvironmentVariable($key,'Process')
            if ($root) { $roots.Add((Canonical $root)) }
        }
        return $roots.ToArray()
    }
    $syncRoots=@(ReadSyncRoots)

    function Metadata([string]$Path,[bool]$RequireTrusted,[bool]$ParentOnly=$false,
        [bool]$RegisteredSyncRoot=$false) {
        $full=Canonical $Path
        if(-not $RegisteredSyncRoot){NoSync $full}
        $parts=$full.Substring(3).Split('\',[StringSplitOptions]::RemoveEmptyEntries)
        $current='C:\'
        # Walk from the root so reparse/cloud indicators are rejected before
        # inspecting descendants. Donor contents are NOT read in Inspect.
        for ($i=0;$i -le $parts.Length;$i++) {
            $item=Microsoft.PowerShell.Management\Get-Item -LiteralPath $current -Force
            if ([int]$item.Attributes -band 0x00441400) { throw 'REPARSE_OFFLINE_OR_RECALL' }
            if ($RequireTrusted) {
                $acl=Microsoft.PowerShell.Security\Get-Acl -LiteralPath $current
                if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $trusted) { throw 'OWNER' }
                $mask=if ($i -eq $parts.Length -and -not $ParentOnly) {0xD0156} else {0xD0040}
                foreach ($ace in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])) {
                    if ($ace.AccessControlType -eq 'Allow' -and
                        -not ($ace.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) -and
                        ([int]$ace.FileSystemRights -band $mask) -and
                        $ace.IdentityReference.Value -notin $trusted) { throw 'WRITER' }
                }
            }
            if ($i -lt $parts.Length) { $current=Join-Path $current $parts[$i] }
        }
        $drive=[IO.DriveInfo]::new('C:\')
        if ($drive.DriveType -ne 'Fixed' -or $drive.DriveFormat -ne 'NTFS') { throw 'STORAGE' }
        return $full
    }
    # An aliased/stale/unreadable registered root is not safely excluded by a
    # lexical prefix. This bootstrap supports ordinary local roots only.
    foreach($root in $syncRoots){$null=Metadata $root $true $false $true}
    $parent=Canonical $ParentDirectory
    if ($parent -ine 'C:\') { throw 'UNSUPPORTED_PARENT' }
    $null=Metadata $parent $true $true
    $null=Metadata $PSCommandPath $true
    $null=Metadata (Get-Location).Path $true
    foreach ($key in @('TEMP','TMP')) {
        $temp=[Environment]::GetEnvironmentVariable($key,'Process')
        if (-not $temp) { throw 'BOOTSTRAP_TEMP' }
        $null=Metadata $temp $true
        $tempItem=Microsoft.PowerShell.Management\Get-Item -LiteralPath $temp
        if(-not $tempItem.PSIsContainer){throw 'TEMP_NOT_DIRECTORY'}
        $tempAcl=Microsoft.PowerShell.Security\Get-Acl -LiteralPath $temp
        $granted=0
        foreach($ace in $tempAcl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])) {
            if($ace.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly){continue}
            $same=$ace.IdentityReference.Value -eq $identity.User.Value
            if($ace.AccessControlType -eq 'Deny' -and
                ($same -or $ace.IdentityReference.Value -in @($identity.Groups.Value)) -and
                ([int]$ace.FileSystemRights -band 7)){throw 'TEMP_ACCESS_DENIED'}
            if($ace.AccessControlType -eq 'Allow' -and
                ($same -or $principal.IsInRole($ace.IdentityReference))) {
                $granted=$granted -bor [int]$ace.FileSystemRights
            }
        }
        if(($granted -band 7) -ne 7){throw 'TEMP_ACCESS_UNVERIFIED'}
    }
    # Check enabled Allow membership and all applicable Deny memberships before
    # claiming that the non-elevated runner can create the fresh root.
    $parentAcl=Microsoft.PowerShell.Security\Get-Acl -LiteralPath $parent
    $allowCreate=$false
    foreach ($ace in $parentAcl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])) {
        if (($ace.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) -or
            -not ([int]$ace.FileSystemRights -band 4)) { continue }
        $same=$ace.IdentityReference.Value -eq $identity.User.Value
        if ($ace.AccessControlType -eq 'Deny' -and
            ($same -or $ace.IdentityReference.Value -in @($identity.Groups.Value))) { throw 'CREATE_DENIED' }
        if ($ace.AccessControlType -eq 'Allow' -and
            ($same -or $principal.IsInRole($ace.IdentityReference))) { $allowCreate=$true }
    }
    if (-not $allowCreate) { throw 'CREATE_NOT_ESTABLISHED' }
    # Trusted, installed OS utilities: fixed read-only invocations, captured in
    # memory. No shell, redirect, helper compilation or output files in Inspect.
    $windows=[Environment]::GetFolderPath([Environment+SpecialFolder]::Windows)
    $subst=Metadata (Join-Path $windows 'System32\subst.exe') $true
    $mountvol=Metadata (Join-Path $windows 'System32\mountvol.exe') $true
    $aliases=@(& $subst 2>&1)
    if ($LASTEXITCODE -ne 0) { throw 'DOS_ALIAS_QUERY' }
    foreach($line in $aliases) {
        $text=$line.ToString().Trim()
        if(-not $text){continue}
        if($text -notmatch '^(?<drive>[A-Za-z]):\\:\s*=>\s*.+$'){throw 'DOS_ALIAS_FORMAT'}
        if($Matches.drive -ieq 'C'){throw 'DOS_ALIAS'}
    }
    $volumeLines=@(& $mountvol 'C:\' '/L' 2>&1)
    if ($LASTEXITCODE -ne 0) { throw 'VOLUME_QUERY' }
    $volumes=@($volumeLines | ForEach-Object {$_.ToString().Trim()} | Where-Object {$_})
    if ($volumes.Count -ne 1 -or $volumes[0] -notmatch '^\\\\\?\\Volume\{[0-9a-fA-F-]{36}\}\\$') { throw 'VOLUME_ALIAS' }
    $volume=$volumes[0]
    $osVolumes=@(CimCmdlets\Get-CimInstance -ClassName Win32_Volume -Filter "DriveLetter='C:'" -ErrorAction Stop)
    if ($osVolumes.Count -ne 1 -or $osVolumes[0].DeviceID -ine $volume -or
        $osVolumes[0].FileSystem -ne 'NTFS' -or $osVolumes[0].DriveType -ne 3) { throw 'VOLUME_UNVERIFIED' }
    # Toolchain remains trusted in place. Do not copy partial installations.
    $tools=@(
        @{Role='cl';Path=(Join-Path $MsvcRoot 'bin\Hostx64\x64\cl.exe');Version='19.44.35229.0';Hash='FE251EF50A1545B1B0835EE17B1E785459712B38D79E45B5C1D3D28970A36619'},
        @{Role='link';Path=(Join-Path $MsvcRoot 'bin\Hostx64\x64\link.exe');Version='14.44.35229.0';Hash='A364AF801A8539E4324D9489313DBF001D959128451FC99A27B24676BBAC058F'},
        @{Role='node';Path=$NodeExecutable;Version='24.15.0';Hash='3331E1FFE19874215472217C5E94F5A0C6D8E18C4AC7111D3937AA0AD5E9B4A5'}
    )
    foreach ($tool in $tools) {
        $tool.Path=Metadata $tool.Path $true
        $stream=[IO.File]::Open($tool.Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
        $owned.Add($stream)
        $hash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($stream))
        if ($hash -cne $tool.Hash) { throw 'TOOL_HASH' }
        if((Microsoft.PowerShell.Management\Get-Item -LiteralPath $tool.Path).VersionInfo.FileVersion -ne $tool.Version) {
            throw 'TOOL_VERSION'
        }
    }
    foreach ($path in @((Join-Path $MsvcRoot 'include'),(Join-Path $MsvcRoot 'lib\x64'),
        (Join-Path $SdkRoot 'Include\10.0.26100.0\ucrt'),(Join-Path $SdkRoot 'Include\10.0.26100.0\shared'),
        (Join-Path $SdkRoot 'Include\10.0.26100.0\um'),(Join-Path $SdkRoot 'Lib\10.0.26100.0\ucrt\x64'),
        (Join-Path $SdkRoot 'Lib\10.0.26100.0\um\x64'))) { $null=Metadata $path $true }
    foreach($path in @((Join-Path $MsvcRoot 'lib\x64\msvcprt.lib'),(Join-Path $MsvcRoot 'lib\x64\vcruntime.lib'),
        (Join-Path $SdkRoot 'Lib\10.0.26100.0\ucrt\x64\ucrt.lib'),
        (Join-Path $SdkRoot 'Lib\10.0.26100.0\um\x64\kernel32.lib'))) { $null=Metadata $path $true }
    foreach($name in @('MSVCP140.dll','VCRUNTIME140.dll','VCRUNTIME140_1.dll','ucrtbase.dll','kernel32.dll')) {
        $null=Metadata (Join-Path $windows ('System32\'+$name)) $true
    }
    foreach($name in @('c1xx.dll','c2.dll')) {
        $null=Metadata (Join-Path $MsvcRoot ('bin\Hostx64\x64\'+$name)) $true
    }
    $catalog=@(
        @{Name='workspace\scripts\rg05-supplementary.ps1';Donor=(Join-Path $DonorRoot 'scripts\rg05-supplementary.ps1');Hash='B1A15B3949B76D1AC7D9CDCBAE757F6ECC9DD9A76EB8859186A7C6EEA2614D5C'},
        @{Name='workspace\quality\api\scripts\rg05-v2-win32.cc';Donor=(Join-Path $DonorRoot 'quality\api\scripts\rg05-v2-win32.cc');Hash='9308AD1EB738BAE7B71D5E9A8A4C0916F5302429771B5D0B7BDE4934045274D6'},
        @{Name='workspace\quality\api\tests\rg05-v2-win32-negative.test.ts';Donor=(Join-Path $DonorRoot 'quality\api\tests\rg05-v2-win32-negative.test.ts');Hash='82F2001E118482CFDD0800E116D7CC317D57F36FFA084FD146B5D4BB6C1E4A6C'},
        @{Name='node\node.lib';Donor=$NodeLibrary;Hash='2DAD98CD40967A4FD4A97195979E0E237E09EC292483700A51D2C20FE5A97C87'}
    )
    $headers=@{
        'node_api.h'='2D4560831E525B47B060EC8A0864AB73993DF9E20215CE9F0FE7B24CD31AF32A'
        'node_api_types.h'='A25356630D3058F0A0C8937D9F297E9471E037FDA58C2696D8A505C2BD99CB00'
        'js_native_api.h'='EB03B6C850A1CFB593FD03E9E4251DB8C82E9A6D9705BCA91AC8D1A01FD7037C'
        'js_native_api_types.h'='7DD3663630849ADA3A30D39ABF42A192C9B6E7DE63017CD32C41F5371A475B34'
        'node_version.h'='F956E28E9D4F73F60E5A3E7B65AE199D49728DFDEC19E5A2CB31D7A79DB3DE1E'
    }
    foreach ($name in $headers.Keys) {
        $catalog+=@{Name=('node\include\node\'+$name);Donor=(Join-Path $NodeHeaders $name);Hash=$headers[$name]}
    }
    # Do not traverse weak donor directories with managed pathname APIs in
    # Inspect. Existence, no-follow metadata and hashes are deferred to native
    # component handles after bootstrap, before boundary creation.
    foreach ($entry in $catalog) {
        $entry.Donor=Canonical $entry.Donor
        NoSync $entry.Donor
    }
    if ($catalog.Count -ne 9) { throw 'CATALOG' }
    if ($null -ne ('RG05.Preparation.Native' -as [type])) { throw 'FRESH_HOST' }
    # Explicit pre-mutation barrier. Inspect returns BEFORE compilation, GUID
    # allocation of a boundary, directory/file creation, and manifest writing.
    $gate=$true
    if ($Mode -eq 'Inspect') {
        $result=[pscustomobject]@{
            Status='INSPECTED_NO_MUTATIONS';BootstrapMetadataGate=$true
            DonorCount=9;DonorMetadataAndHashes='PENDING_HANDLE_VERIFICATION_IN_PREPARE'
            PreparationCompleted=$false;ExecutionAuthorized=$false
        }
    } else {
        if ($Mode -ne 'Prepare' -or -not $gate) { throw 'PRE_MUTATION_GATE' }
        Microsoft.PowerShell.Utility\Add-Type -Language CSharp -ErrorAction Stop -WarningAction Stop -Verbose:$false -Debug:$false -TypeDefinition @'
using System;
using System.IO;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using Microsoft.Win32.SafeHandles;
namespace RG05.Preparation {
 public sealed class Item : IDisposable {
  public SafeFileHandle Handle; public FileStream Stream; public string FinalPath;
  public string Identity; public uint Attributes; public byte[] Security;
  public string Hash() {
   if(Stream==null) throw new InvalidOperationException("NO_DATA_STREAM");
   Stream.Position=0; string hash=Convert.ToHexString(SHA256.HashData(Stream));
   Stream.Position=0; return hash;
  }
  public void Dispose() { if(Stream!=null) Stream.Dispose(); if(Handle!=null) Handle.Dispose(); }
 }
 public static class Native {
  [StructLayout(LayoutKind.Sequential)] struct SA {public int Length;public IntPtr SD;public int Inherit;}
  [StructLayout(LayoutKind.Sequential)] struct Basic {
   public long Creation,Access,Write,Change;public uint Attributes;
  }
  [StructLayout(LayoutKind.Sequential)] struct ID {
   public ulong Volume;[MarshalAs(UnmanagedType.ByValArray,SizeConst=16)] public byte[] FileId;
  }
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
  static extern SafeFileHandle CreateFileW(string path,uint access,uint share,IntPtr sa,uint creation,uint flags,IntPtr template);
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
  static extern bool CreateDirectoryW(string path,ref SA attributes);
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
  static extern uint GetFinalPathNameByHandleW(SafeFileHandle handle,StringBuilder path,uint size,uint flags);
  [DllImport("kernel32.dll",SetLastError=true)]
  static extern bool GetFileInformationByHandleEx(SafeFileHandle h,int kind,out Basic data,uint size);
  [DllImport("kernel32.dll",SetLastError=true)]
  static extern bool GetFileInformationByHandleEx(SafeFileHandle h,int kind,out ID data,uint size);
  [DllImport("advapi32.dll",SetLastError=true)]
  static extern bool GetKernelObjectSecurity(SafeFileHandle h,uint info,[Out] byte[] sd,uint size,out uint needed);
  [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
  static extern bool ConvertStringSecurityDescriptorToSecurityDescriptorW(string text,uint revision,out IntPtr sd,out uint size);
  [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr memory);
  static Item Describe(SafeFileHandle h,string expected,bool? data,bool writable) {
   var item=new Item {Handle=h};
   try {
    if(h.IsInvalid) throw new IOException("OPEN");
    Basic basic; ID id;
    if(!GetFileInformationByHandleEx(h,0,out basic,(uint)Marshal.SizeOf<Basic>()) ||
       !GetFileInformationByHandleEx(h,18,out id,(uint)Marshal.SizeOf<ID>())) throw new IOException("IDENTITY");
    if((basic.Attributes & 0x00441400)!=0) throw new IOException("REPARSE_OFFLINE_OR_RECALL");
    if(data.HasValue && data.Value==((basic.Attributes & 0x10)!=0)) throw new IOException("TYPE");
    var path=new StringBuilder(32768);
    uint n=GetFinalPathNameByHandleW(h,path,(uint)path.Capacity,1);
    if(n==0 || n>=path.Capacity || !String.Equals(path.ToString(),expected,StringComparison.OrdinalIgnoreCase))
     throw new IOException("NAMESPACE");
    uint needed;
    GetKernelObjectSecurity(h,5,null,0,out needed);
    if(needed==0 || needed>65536) throw new IOException("SECURITY_SIZE");
    var sd=new byte[needed];
    if(!GetKernelObjectSecurity(h,5,sd,needed,out needed)) throw new IOException("SECURITY");
    item.FinalPath=path.ToString();item.Attributes=basic.Attributes;item.Security=sd;
    item.Identity=id.Volume.ToString("X16")+":"+Convert.ToHexString(id.FileId);
    if(data==true) item.Stream=new FileStream(h,writable?FileAccess.ReadWrite:FileAccess.Read);
    return item;
   } catch {item.Dispose();throw;}
  }
  // No-follow EACH component. Retained ancestor handles prevent rename/delete
  // by unrelated writers during pathname use. System volume root is shared.
  public static Item Pin(string path,string volume,List<IDisposable> held) {
   string[] parts=path.Substring(3).Split('\\',StringSplitOptions.RemoveEmptyEntries);
   string current=path.Substring(0,3);Item last=null;
   for(int i=0;i<=parts.Length;i++) {
    uint access=0x20080u; // READ_CONTROL, FILE_READ_ATTRIBUTES
    var h=CreateFileW(current,access,i==0?7u:1u,IntPtr.Zero,3,0x02200000u,IntPtr.Zero);
    // OPEN_REPARSE_POINT | BACKUP_SEMANTICS; no file bytes read yet.
    last=Describe(h,volume+current.Substring(3),i<parts.Length?(bool?)false:null,false);
    held.Add(last);
    bool file=(last.Attributes & 0x10)==0;
    if(file) {
     // Directory chain remains pinned while the data handle is opened.
     var dataHandle=CreateFileW(current,0x80020080u,1,IntPtr.Zero,3,0x00200000u,IntPtr.Zero);
     var content=Describe(dataHandle,volume+current.Substring(3),true,false);
     if(content.Identity!=last.Identity) {content.Dispose();throw new IOException("SUBSTITUTION");}
     held.Add(content);last=content;
    }
    if(i<parts.Length) current=Path.Combine(current,parts[i]);
   }
   return last;
  }
  public static void Directory(string path,string sddl) {
   IntPtr sd=IntPtr.Zero;uint size;
   try {
    if(!ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl,1,out sd,out size)) throw new IOException("SDDL");
    var sa=new SA {Length=Marshal.SizeOf<SA>(),SD=sd,Inherit=0};
    if(!CreateDirectoryW(path,ref sa)) throw new IOException("DIRECTORY_COLLISION_OR_FAILURE");
   } finally {if(sd!=IntPtr.Zero) LocalFree(sd);}
  }
  public static Item FileNew(string path,string sddl,string volume) {
   IntPtr sd=IntPtr.Zero;IntPtr attributes=IntPtr.Zero;uint size;
   try {
    if(!ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl,1,out sd,out size)) throw new IOException("SDDL");
    var sa=new SA {Length=Marshal.SizeOf<SA>(),SD=sd,Inherit=0};
    attributes=Marshal.AllocHGlobal(Marshal.SizeOf<SA>());Marshal.StructureToPtr(sa,attributes,false);
    var h=CreateFileW(path,0xC0020080u,1,attributes,1,0x80u,IntPtr.Zero); // CREATE_NEW, never overwrite.
    return Describe(h,volume+path.Substring(3),true,true);
   } finally {if(attributes!=IntPtr.Zero) Marshal.FreeHGlobal(attributes);if(sd!=IntPtr.Zero) LocalFree(sd);}
  }
 }
}
'@
        function NativePin([string]$Path) {
            return [RG05.Preparation.Native]::Pin($Path,$volume,$owned)
        }
        function ExactSecurity($Item,[bool]$Directory) {
            $sd=[Security.AccessControl.RawSecurityDescriptor]::new($Item.Security,0)
            if ($sd.Owner.Value -ne $identity.User.Value -or
                -not ($sd.ControlFlags -band [Security.AccessControl.ControlFlags]::DiscretionaryAclProtected) -or
                $null -eq $sd.DiscretionaryAcl -or $sd.DiscretionaryAcl.Count -ne 3) { throw 'NEW_SECURITY' }
            $seen=[Collections.Generic.HashSet[string]]::new()
            $expected=@($identity.User.Value,$system.Value,$admins.Value)
            $flags=if($Directory){3}else{0}
            foreach($ace in $sd.DiscretionaryAcl) {
                if ($ace -isnot [Security.AccessControl.CommonAce] -or
                    $ace.AceQualifier -ne [Security.AccessControl.AceQualifier]::AccessAllowed -or
                    $ace.SecurityIdentifier.Value -notin $expected -or
                    -not $seen.Add($ace.SecurityIdentifier.Value) -or
                    $ace.AccessMask -ne 0x1F01FF -or [int]$ace.AceFlags -ne $flags) { throw 'NEW_ACE' }
            }
        }
        # Resolve native identities and pin ALL donors before creating a boundary.
        $parentPin=NativePin $parent
        foreach($entry in $catalog) {
            $entry['PinnedInput']=NativePin $entry.Donor
            if ($entry.PinnedInput.Hash() -cne $entry.Hash) { throw 'DONOR_HASH' }
        }
        foreach($tool in $tools) {
            $pin=NativePin $tool.Path
            if($pin.Hash() -cne $tool.Hash){throw 'TOOL_RECHECK'}
        }
        foreach($key in @('TEMP','TMP')) { $null=NativePin ([Environment]::GetEnvironmentVariable($key,'Process')) }
        $boundary=Join-Path $parent ('rg05-l1-boundary-'+[guid]::NewGuid().ToString('N'))
        if (Microsoft.PowerShell.Management\Test-Path -LiteralPath $boundary) { throw 'COLLISION' }
        # Private local attempt reference survives a later partial failure.
        # Never publish this record or infer success from it.
        Write-Output ([pscustomobject]@{Status='PRIVATE_PREPARATION_ATTEMPT';BoundaryDirectory=$boundary})
        $dirSd='O:'+$identity.User.Value+'D:P(A;OICI;FA;;;'+$identity.User.Value+
            ')(A;OICI;FA;;;'+$system.Value+')(A;OICI;FA;;;'+$admins.Value+')'
        $fileSd='O:'+$identity.User.Value+'D:P(A;;FA;;;'+$identity.User.Value+
            ')(A;;FA;;;'+$system.Value+')(A;;FA;;;'+$admins.Value+')'
        $directories=@('','workspace','workspace\scripts','workspace\quality','workspace\quality\api',
            'workspace\quality\api\scripts','workspace\quality\api\tests','node','node\include',
            'node\include\node','temp','scratch','evidence')
        $records=[Collections.Generic.List[object]]::new()
        foreach($relative in $directories) {
            $path=if($relative){Join-Path $boundary $relative}else{$boundary}
            [RG05.Preparation.Native]::Directory($path,$dirSd)
            $created=$true
            $pin=NativePin $path
            ExactSecurity $pin $true
            $records.Add([ordered]@{role=$relative;identity=$pin.Identity;kind='directory'})
        }
        foreach($entry in $catalog) {
            $destination=Join-Path $boundary $entry.Name
            $new=[RG05.Preparation.Native]::FileNew($destination,$fileSd,$volume)
            $owned.Add($new)
            ExactSecurity $new $false
            $entry.PinnedInput.Stream.Position=0
            $entry.PinnedInput.Stream.CopyTo($new.Stream)
            $new.Stream.Flush($true)
            if($new.Hash() -cne $entry.Hash){throw 'COPY_HASH'}
            $size=$new.Stream.Length
            # Close our writer before a read-only/no-write-share pin. The fresh
            # protected tree excludes unrelated writers during this interval.
            $new.Dispose()
            $again=NativePin $destination
            if($again.Identity -cne $new.Identity -or $again.Hash() -cne $entry.Hash){throw 'COPY_IDENTITY'}
            ExactSecurity $again $false
            $records.Add([ordered]@{role=$entry.Name;identity=$new.Identity;sha256=$entry.Hash;bytes=$size;kind='file'})
        }
        # Reopen all new objects, compare native IDs/security/hashes before commit.
        foreach($record in $records) {
            $path=if($record.role){Join-Path $boundary $record.role}else{$boundary}
            $again=NativePin $path
            if($again.Identity -cne $record.identity){throw 'FINAL_IDENTITY'}
            ExactSecurity $again ($record.kind -eq 'directory')
            if($record.kind -eq 'file' -and $again.Hash() -cne $record.sha256){throw 'FINAL_HASH'}
        }
        $newParent=NativePin $parent
        if($newParent.Identity -cne $parentPin.Identity){throw 'PARENT_CHANGED'}
        $manifest=[ordered]@{
            schema='RG05-BOUNDARY-PREPARATION-1';state='PREPARED_CANDIDATE'
            runner_sha256=$catalog[0].Hash;owner_matched=$true;sync_registry_resolved=$true
            volume=$volume;objects=$records.ToArray();tool_hashes=@($tools|ForEach-Object{@{role=$_.Role;sha256=$_.Hash}})
            l1_executed=$false;execution_authorized=$false;protected_build_claim=$false;operational_security_claim=$false
        }
        $bytes=[Text.Encoding]::UTF8.GetBytes(
            (Microsoft.PowerShell.Utility\ConvertTo-Json -InputObject $manifest -Depth 8 -Compress))
        $manifestPath=Join-Path $boundary 'evidence\preparation.json'
        $new=[RG05.Preparation.Native]::FileNew($manifestPath,$fileSd,$volume)
        $owned.Add($new);ExactSecurity $new $false
        $new.Stream.Write($bytes);$new.Stream.Flush($true)
        $manifestHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes))
        $new.Dispose()
        $again=NativePin $manifestPath
        ExactSecurity $again $false
        if($again.Identity -cne $new.Identity -or $again.Hash() -cne $manifestHash){throw 'MANIFEST_READBACK'}
        $result=[pscustomobject]@{Status='PREPARED';BoundaryDirectory=$boundary;ManifestSha256=$manifestHash;L1Executed=$false}
    }
} catch {
    $result=$null
    Write-Output 'RG05_BOUNDARY_PREPARATION_BLOCKED'
} finally {
    if($null -ne $owned) {
        for($i=$owned.Count-1;$i -ge 0;$i--){
            try{$owned[$i].Dispose()}catch{$result=$null}
        }
    }
    if($null -ne $identity){try{$identity.Dispose()}catch{$result=$null}}
}
if($null -eq $result){Write-Output 'RG05_BOUNDARY_NOT_PREPARED';exit 1}
# The candidate manifest alone is not success: require this terminal status,
# successful handle disposal and a separate readback before L1 authorization.
Write-Output $result
