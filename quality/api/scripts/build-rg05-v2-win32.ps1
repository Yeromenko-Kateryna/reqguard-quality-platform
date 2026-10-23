#requires -Version 7.0
#requires -PSEdition Core
# SOURCE ONLY. Do not run in the synthetic-source or static-fix tasks.
# Future offline build, after separate authorization. Never loads the addon.
# Supply an already configured x64 MSVC toolchain, Windows SDK and matching
# official Node 24.15.0 x64 headers/import library. No discovery or downloads.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$CompilerPath,
    [Parameter(Mandatory)][string]$MsvcIncludeDirectory,
    [Parameter(Mandatory)][string]$MsvcLibraryDirectory,
    [Parameter(Mandatory)][string]$SdkIncludeDirectory,
    [Parameter(Mandatory)][string]$SdkLibraryDirectory,
    [Parameter(Mandatory)][string]$NodeHeadersDirectory,
    [Parameter(Mandatory)][string]$NodeImportLibrary,
    [Parameter(Mandatory)][string]$OutputDirectory,
    # Explicitly approved account SID, independently matched to the process token.
    [Parameter(Mandatory)][string]$TrustedRunnerSid
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-LocalPath([string]$Path) {
    if ($Path -match '(?i)(^|\\)(reqguardlocal|\.runtime|reqguard_rg05_api_v[12]|rg05-v[12])(\\|$)') {
        throw 'Reserved ReqGuard runtime namespace refused.'
    }
    if ($Path -notmatch '^[A-Za-z]:\\' -or $Path.Contains('/') -or
        $Path.Substring(2).Contains(':') -or $Path -match '[\x00-\x1f*?"<>|~]' -or
        $Path -match '(?i)(^|\\)(\.\.?|[^\\]*[. ])(\\|$)') {
        throw 'Only canonical local absolute paths are supported.'
    }
    $full = [IO.Path]::GetFullPath($Path)
    if ($full.Length -gt 3) { $full = $full.TrimEnd('\') }
    $comparison = $Path
    if ($comparison.Length -gt 3) { $comparison = $comparison.TrimEnd('\') }
    if ($full -ine $comparison) { throw 'Path alias refused.' }
    return $full
}
function Assert-Existing([string]$Path, [bool]$Directory) {
    $full = Assert-LocalPath $Path
    $item = Get-Item -LiteralPath $full -Force
    if (($item -isnot [IO.FileInfo] -and $item -isnot [IO.DirectoryInfo]) -or
        (($item -is [IO.DirectoryInfo]) -ne $Directory)) { throw 'Prerequisite type mismatch.' }
    $walk = $item
    while ($null -ne $walk) {
        if (($walk.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'Reparse ancestry is unsupported.'
        }
        if ($walk -is [IO.DirectoryInfo]) { $walk = $walk.Parent }
        elseif ($walk -is [IO.FileInfo]) { $walk = $walk.Directory }
        else { throw 'Unsupported filesystem ancestry type.' }
    }
    $resolved = (Resolve-Path -LiteralPath $full).ProviderPath
    if ($resolved.Length -gt 3) { $resolved = $resolved.TrimEnd('\') }
    if ($resolved -ine $full) { throw 'Resolved alias refused.' }
    return $full
}
function Is-Within([string]$Candidate, [string]$Root) {
    return $Candidate -ieq $Root -or
        $Candidate.StartsWith($Root.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)
}

$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..')).TrimEnd('\')
$source = Assert-Existing (Join-Path $PSScriptRoot 'rg05-v2-win32.cc') $false
$compiler = Assert-Existing $CompilerPath $false
if ([IO.Path]::GetFileName($compiler) -ine 'cl.exe') { throw 'Explicit MSVC cl.exe required.' }
$msvcInclude = Assert-Existing $MsvcIncludeDirectory $true
$msvcLib = Assert-Existing $MsvcLibraryDirectory $true
$sdkInclude = Assert-Existing $SdkIncludeDirectory $true
$sdkLib = Assert-Existing $SdkLibraryDirectory $true
$nodeHeaders = Assert-Existing $NodeHeadersDirectory $true
$nodeLib = Assert-Existing $NodeImportLibrary $false
if ([IO.Path]::GetFileName($nodeLib) -ine 'node.lib') { throw 'Explicit Node import library required.' }
# Exact version metadata check; architecture/link compatibility remains a build gate.
$versionHeader = Assert-Existing (Join-Path $nodeHeaders 'node_version.h') $false
$versionText = Get-Content -LiteralPath $versionHeader -Raw
foreach ($part in @(@('MAJOR', '24'), @('MINOR', '15'), @('PATCH', '0'))) {
    if ($versionText -notmatch ('(?m)^\s*#define\s+NODE_' + $part[0] + '_VERSION\s+' + $part[1] + '\s*$')) {
        throw 'Official Node 24.15.0 headers required.'
    }
}
$includePaths = @($msvcInclude, $nodeHeaders)
foreach ($component in @('ucrt', 'shared', 'um')) {
    $includePaths += Assert-Existing (Join-Path $sdkInclude $component) $true
}
$libPaths = @($msvcLib)
foreach ($component in @('ucrt\x64', 'um\x64')) {
    $libPaths += Assert-Existing (Join-Path $sdkLib $component) $true
}
foreach ($file in @('node_api.h', 'js_native_api.h', 'js_native_api_types.h', 'node_api_types.h')) {
    $null = Assert-Existing (Join-Path $nodeHeaders $file) $false
}
foreach ($file in @('string', 'vector', 'regex', 'memory')) {
    $null = Assert-Existing (Join-Path $msvcInclude $file) $false
}
$null = Assert-Existing (Join-Path $msvcLib 'msvcprt.lib') $false
$null = Assert-Existing (Join-Path $msvcLib 'vcruntime.lib') $false
$null = Assert-Existing (Join-Path $sdkLib 'ucrt\x64\ucrt.lib') $false
$null = Assert-Existing (Join-Path $sdkLib 'um\x64\kernel32.lib') $false

$out = Assert-LocalPath $OutputDirectory
if (Test-Path -LiteralPath $out) { throw 'Output must be a new dedicated directory.' }
if ((Is-Within $out $repo) -or (Is-Within $repo $out) -or
    $out -match '(?i)(onedrive|dropbox|google drive|icloud|reqguardlocal|reqguard[_-]rg05|\.runtime|rg05-v[12])' -or
    [IO.Path]::GetFileName($out) -notmatch '^rg05-synthetic-build-[a-z0-9-]{1,48}$') {
    throw 'Repository, sync and reserved runtime output paths are refused.'
}
$parent = Assert-Existing ([IO.Path]::GetDirectoryName($out)) $true
$drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($out))
if ($drive.DriveType -ne [IO.DriveType]::Fixed -or $drive.DriveFormat -ne 'NTFS') {
    throw 'Output requires fixed local NTFS.'
}
# Reject redirected environment roots as well as common sync path names.
foreach ($syncRoot in @($env:OneDrive, $env:OneDriveConsumer, $env:OneDriveCommercial)) {
    if ($syncRoot -and (Is-Within $out $syncRoot.TrimEnd('\'))) { throw 'Sync output refused.' }
}

# R03: the lexical checks above are only filters. This embedded helper is
# compiled IN MEMORY by PowerShell 7 only during a separately authorized build.
# No OutputAssembly, new dependency, downloaded verifier or temporary source.
# Its directory handles read metadata/security only, not admission/lease handles.
# Never reuse an ambient type in place of this verifier's source.
if ($null -ne ('RG05.StaticFix01.OutputBoundary' -as [type])) {
    throw 'Output verifier type already exists; use a fresh PowerShell session.'
}
Add-Type -Language CSharp -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Win32.SafeHandles;

namespace RG05.StaticFix01 {
public sealed class OutputBoundary : IDisposable {
    [StructLayout(LayoutKind.Sequential)] struct Tag { public uint Attributes, ReparseTag; }
    [StructLayout(LayoutKind.Sequential)] struct Id { public ulong Volume, Low, High; }
    [StructLayout(LayoutKind.Sequential)] struct SecurityAttributes {
        public uint Length;
        public IntPtr Descriptor;
        public int InheritHandle; // Win32 BOOL, not a one-byte C# bool.
    }
    [StructLayout(LayoutKind.Sequential)] struct GenericMapping {
        public uint Read, Write, Execute, All;
    }
    sealed class DirectoryIdentity {
        public SafeFileHandle Handle;
        public Id FileId;
        public string Path;
    }
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, ExactSpelling=true, SetLastError=true)]
    static extern SafeFileHandle CreateFileW(string path, uint access, uint share,
        IntPtr security, uint disposition, uint flags, IntPtr template);
    [DllImport("kernel32.dll", EntryPoint="GetFileInformationByHandleEx", SetLastError=true)]
    static extern bool TagInfo(SafeFileHandle handle, int kind, out Tag info, uint size);
    [DllImport("kernel32.dll", EntryPoint="GetFileInformationByHandleEx", SetLastError=true)]
    static extern bool IdInfo(SafeFileHandle handle, int kind, out Id info, uint size);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, ExactSpelling=true, SetLastError=true)]
    static extern uint GetFinalPathNameByHandleW(SafeFileHandle handle, StringBuilder path, uint size, uint flags);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, ExactSpelling=true, SetLastError=true)]
    static extern bool GetVolumeInformationW(string root, StringBuilder name, uint nameSize,
        out uint serial, out uint component, out uint flags, StringBuilder fs, uint fsSize);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, ExactSpelling=true)]
    static extern uint GetDriveTypeW(string root);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, ExactSpelling=true, SetLastError=true)]
    static extern uint GetFileAttributesW(string path);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, ExactSpelling=true, SetLastError=true)]
    static extern bool CreateDirectoryW(string path, ref SecurityAttributes security);
    [DllImport("advapi32.dll", ExactSpelling=true)]
    static extern uint GetSecurityInfo(SafeFileHandle handle, int type, uint information,
        out IntPtr owner, out IntPtr group, out IntPtr dacl, out IntPtr sacl, out IntPtr descriptor);
    [DllImport("advapi32.dll", ExactSpelling=true)]
    static extern bool IsValidSecurityDescriptor(IntPtr descriptor);
    [DllImport("advapi32.dll", ExactSpelling=true)]
    static extern uint GetSecurityDescriptorLength(IntPtr descriptor);
    [DllImport("advapi32.dll", ExactSpelling=true, SetLastError=true)]
    static extern bool DuplicateToken(SafeAccessTokenHandle existing, int level,
        out SafeAccessTokenHandle duplicate);
    [DllImport("advapi32.dll", ExactSpelling=true, SetLastError=true)]
    static extern bool AccessCheck(IntPtr descriptor, SafeAccessTokenHandle token, uint desired,
        ref GenericMapping mapping, IntPtr privileges, ref uint privilegeSize,
        out uint granted, [MarshalAs(UnmanagedType.Bool)] out bool allowed);
    [DllImport("kernel32.dll", ExactSpelling=true)]
    static extern IntPtr LocalFree(IntPtr memory);

    readonly List<DirectoryIdentity> held = new List<DirectoryIdentity>();
    const int FullControl = 0x001f01ff; // FILE_ALL_ACCESS, including DELETE/WRITE_DAC/WRITE_OWNER.
    SecurityIdentifier runner;
    SafeAccessTokenHandle accessToken;
    byte[] creationDescriptor;
    DirectoryIdentity outputIdentity;
    string output;
    bool created, disposed;
    static void Require(bool ok) { if (!ok) throw new InvalidOperationException("Output identity refused."); }
    static void Win32Failure() {
        int code = Marshal.GetLastWin32Error();
        throw new InvalidOperationException("Output identity Win32 failure: " + code);
    }
    void CheckRunner() {
        // A thread impersonation token must never stand in for the compiler's process token.
        using (var impersonating = WindowsIdentity.GetCurrent(true)) Require(impersonating == null);
        using (var identity = WindowsIdentity.GetCurrent(TokenAccessLevels.Query))
            Require(identity.User != null && identity.User.Equals(runner));
    }
    void PrepareSecurity(string approvedSid) {
        runner = new SecurityIdentifier(approvedSid);
        Require(runner.IsAccountSid() && runner.Value == approvedSid);
        CheckRunner();
        using (var identity = WindowsIdentity.GetCurrent(TokenAccessLevels.Query | TokenAccessLevels.Duplicate)) {
            Require(identity.User != null && identity.User.Equals(runner));
            // SecurityImpersonation=2. Duplicate is used only for AccessCheck, never impersonation.
            if (!DuplicateToken(identity.AccessToken, 2, out accessToken)) Win32Failure();
            Require(accessToken != null && !accessToken.IsInvalid);
        }
        // Frozen TCB: the approved runner, LocalSystem and Builtin Administrators only.
        // P blocks inherited ACEs; OI/CI propagates these grants to compiler files/subdirectories.
        var descriptor = new RawSecurityDescriptor("O:" + runner.Value + "G:" + runner.Value +
            "D:P(A;OICI;FA;;;" + runner.Value + ")(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)");
        creationDescriptor = new byte[descriptor.BinaryLength];
        descriptor.GetBinaryForm(creationDescriptor, 0);
    }
    void VerifySecurity(SafeFileHandle handle) {
        IntPtr owner, group, dacl, sacl, descriptor = IntPtr.Zero;
        try {
            // SE_FILE_OBJECT=1; OWNER | GROUP | DACL_SECURITY_INFORMATION=7.
            // This function RETURNS its error code; GetLastError is not its status.
            uint error = GetSecurityInfo(handle, 1, 7, out owner, out group, out dacl, out sacl, out descriptor);
            if (error != 0) throw new InvalidOperationException("Output security query failed: " + error);
            Require(descriptor != IntPtr.Zero && owner != IntPtr.Zero && group != IntPtr.Zero &&
                dacl != IntPtr.Zero && IsValidSecurityDescriptor(descriptor));
            uint length = GetSecurityDescriptorLength(descriptor);
            Require(length > 0 && length <= 65536);
            var bytes = new byte[(int)length]; Marshal.Copy(descriptor, bytes, 0, bytes.Length);
            var sd = new RawSecurityDescriptor(bytes, 0);
            Require(sd.Owner != null && sd.Owner.Equals(runner) && sd.Group != null && sd.Group.Equals(runner));
            Require((sd.ControlFlags & (ControlFlags.DiscretionaryAclPresent | ControlFlags.DiscretionaryAclProtected)) ==
                (ControlFlags.DiscretionaryAclPresent | ControlFlags.DiscretionaryAclProtected));
            Require(sd.DiscretionaryAcl != null && sd.DiscretionaryAcl.Count == 3);
            var expected = new HashSet<string>(StringComparer.Ordinal) { runner.Value, "S-1-5-18", "S-1-5-32-544" };
            foreach (GenericAce entry in sd.DiscretionaryAcl) {
                // No inherited, deny, object, callback/conditional, inherit-only or unknown ACEs.
                var ace = entry as CommonAce;
                Require(ace != null && ace.AceType == AceType.AccessAllowed && !ace.IsCallback &&
                    ace.AceFlags == (AceFlags.ObjectInherit | AceFlags.ContainerInherit) &&
                    ace.AccessMask == FullControl && expected.Remove(ace.SecurityIdentifier.Value));
            }
            Require(expected.Count == 0);
            var mapping = new GenericMapping { Read=0x120089, Write=0x120116, Execute=0x1200a0, All=FullControl };
            // Bounded PRIVILEGE_SET buffer. Unsupported/insufficient results fail closed, no fallback.
            IntPtr privileges = Marshal.AllocHGlobal(1024);
            try {
                uint size = 1024, granted; bool allowed;
                if (!AccessCheck(descriptor, accessToken, FullControl, ref mapping, privileges,
                    ref size, out granted, out allowed)) Win32Failure();
                Require(allowed && (granted & FullControl) == FullControl);
            } finally { Marshal.FreeHGlobal(privileges); }
        } finally {
            if (descriptor != IntPtr.Zero) Require(LocalFree(descriptor) == IntPtr.Zero);
        }
    }
    static bool Within(string child, string parent) {
        return child.Equals(parent, StringComparison.OrdinalIgnoreCase) ||
            child.StartsWith(parent.TrimEnd('\\') + "\\", StringComparison.OrdinalIgnoreCase);
    }
    static string VolumeRoot(string path) {
        // Only a local volume GUID namespace returned by Windows is accepted.
        Guid guid;
        Require(path.StartsWith(@"\\?\Volume{", StringComparison.OrdinalIgnoreCase) &&
            path.Length >= 49 && path[47] == '}' && path[48] == '\\' &&
            Guid.TryParse(path.Substring(10, 38), out guid));
        return path.Substring(0, 49);
    }
    static string FinalPath(SafeFileHandle handle) {
        var buffer = new StringBuilder(32768);
        // FILE_NAME_NORMALIZED | VOLUME_NAME_GUID, never a caller's drive alias.
        uint length = GetFinalPathNameByHandleW(handle, buffer, (uint)buffer.Capacity, 1);
        if (length == 0) Win32Failure();
        Require(length < buffer.Capacity);
        string path = buffer.ToString(); VolumeRoot(path);
        return path.TrimEnd('\\');
    }
    static Id Inspect(SafeFileHandle handle) {
        Tag tag; Id id;
        if (!TagInfo(handle, 9, out tag, 8)) Win32Failure(); // FileAttributeTagInfo
        Require((tag.Attributes & 0x10) != 0 && (tag.Attributes & 0x400) == 0 && tag.ReparseTag == 0);
        if (!IdInfo(handle, 18, out id, 24)) Win32Failure(); // FileIdInfo
        Require(id.Low != 0 || id.High != 0);
        return id;
    }
    static bool Same(Id a, Id b) { return a.Volume == b.Volume && a.Low == b.Low && a.High == b.High; }
    DirectoryIdentity Open(string path, uint access = 0x80) {
        // OPEN_EXISTING, noninheritable, attributes (and output READ_CONTROL). Omitting SHARE_DELETE
        // pins each directory against ordinary rename/delete while retained.
        var handle = CreateFileW(path, access, 3, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero);
        if (handle.IsInvalid) { int code = Marshal.GetLastWin32Error(); handle.Dispose();
            throw new InvalidOperationException("Output directory open failed: " + code); }
        try {
            var identity = new DirectoryIdentity { Handle=handle, FileId=Inspect(handle), Path=FinalPath(handle) };
            held.Add(identity); return identity;
        } catch { handle.Dispose(); throw; }
    }
    DirectoryIdentity Pin(string path, bool readSecurity = false) {
        var leaf = Open(path, readSecurity ? 0x20080u : 0x80u);
        string canonical = leaf.Path;
        // FinalPath trims a volume root's slash; restore it for root parsing.
        string root = VolumeRoot(canonical + "\\");
        uint serial, component, flags;
        var fs = new StringBuilder(32);
        if (!GetVolumeInformationW(root, null, 0, out serial, out component, out flags, fs, 32)) Win32Failure();
        Require(GetDriveTypeW(root) == 3 && fs.ToString() == "NTFS");
        string current = root.TrimEnd('\\');
        Require(Open(root).Path.Equals(current, StringComparison.OrdinalIgnoreCase));
        string relative = canonical.Length > current.Length ? canonical.Substring(current.Length).TrimStart('\\') : "";
        foreach (string part in relative.Split(new[]{'\\'}, StringSplitOptions.RemoveEmptyEntries)) {
            Require(part != "." && part != ".." && part.IndexOf(':') < 0);
            current += "\\" + part;
            Require(Open(current).Path.Equals(current, StringComparison.OrdinalIgnoreCase));
        }
        return leaf;
    }
    public static OutputBoundary Validate(string repository, string parent, string name, string[] syncRoots,
        string trustedRunnerSid) {
        var boundary = new OutputBoundary();
        try {
            Require(Regex.IsMatch(name, @"\Arg05-synthetic-build-[a-z0-9-]{1,48}\z"));
            boundary.PrepareSecurity(trustedRunnerSid);
            var repo = boundary.Pin(repository);
            int firstParent = boundary.held.Count;
            var destination = boundary.Pin(parent);
            string candidate = destination.Path + "\\" + name;
            Require(!Within(candidate, repo.Path) && !Within(repo.Path, candidate));
            // Compare file identities along the independently opened ancestry too.
            for (int i = firstParent; i < boundary.held.Count; ++i)
                Require(!Same(repo.FileId, boundary.held[i].FileId));
            Require(!Regex.IsMatch(candidate,
                @"onedrive|dropbox|google drive|icloud|reqguardlocal|reqguard[_-]rg05|\.runtime|rg05-v[12]",
                RegexOptions.IgnoreCase));
            foreach (string sync in syncRoots) {
                if (!String.IsNullOrWhiteSpace(sync)) Require(!Within(candidate, boundary.Pin(sync).Path));
            }
            uint attributes = GetFileAttributesW(candidate);
            int error = Marshal.GetLastWin32Error();
            Require(attributes == UInt32.MaxValue && error == 2); // Only confirmed absent leaf.
            boundary.output = candidate;
            boundary.Recheck();
            return boundary;
        } catch { boundary.Dispose(); throw; }
    }
    public void Recheck() {
        Require(!disposed);
        CheckRunner();
        foreach (var directory in held)
            Require(Same(directory.FileId, Inspect(directory.Handle)) &&
                directory.Path.Equals(FinalPath(directory.Handle), StringComparison.OrdinalIgnoreCase));
        if (created) {
            Require(outputIdentity != null);
            VerifySecurity(outputIdentity.Handle);
        }
    }
    public string CreateOutput() {
        Require(!created && output != null);
        Recheck();
        // FIRST filesystem write. Apply the protected DACL AT CREATION: no inherited-writer window.
        // An existing leaf (including a race/collision) fails; no adoption or ACL repair.
        var pinned = GCHandle.Alloc(creationDescriptor, GCHandleType.Pinned);
        try {
            var security = new SecurityAttributes { Length=(uint)Marshal.SizeOf<SecurityAttributes>(),
                Descriptor=pinned.AddrOfPinnedObject(), InheritHandle=0 };
            if (!CreateDirectoryW(output, ref security)) Win32Failure();
        } finally { pinned.Free(); }
        created = true;
        outputIdentity = Pin(output, true);
        Require(outputIdentity.Path.Equals(output, StringComparison.OrdinalIgnoreCase));
        Recheck(); return output;
    }
    public void Dispose() {
        if (disposed) return;
        disposed = true;
        for (int i = held.Count - 1; i >= 0; --i) held[i].Handle.Dispose();
        held.Clear(); // No deletion or retry, including after a failed build.
        if (accessToken != null) accessToken.Dispose();
    }
}
}
'@
$boundary = [RG05.StaticFix01.OutputBoundary]::Validate($repo, $parent,
    [IO.Path]::GetFileName($out), [string[]]@($env:OneDrive, $env:OneDriveConsumer, $env:OneDriveCommercial),
    $TrustedRunnerSid)
try {
# Canonical volume-GUID path is used for ALL writes, TMP/TEMP and compiler
# arguments. Retargeting the input drive alias cannot redirect these writes.
# F01: fresh output has a protected, verified DACL before any compiler file exists.
# Unrelated principals cannot plant predictable filenames or hard links there.
# No exclusive precreation is needed within this model (MSVC must create its own files).
# Same-runner-SID processes, SYSTEM and Administrators are trusted: a compromised
# trusted writer can still interfere. Neither per-process nor privileged isolation is claimed.
$out = $boundary.CreateOutput()
$arguments = @('/nologo', '/LD', '/TP', '/std:c++17', '/MD', '/EHsc', '/W4', '/X',
    '/DNAPI_VERSION=8', '/DRG05_SYNTHETIC_ONLY=1', '/DWIN32_LEAN_AND_MEAN', '/DNOMINMAX',
    ('/Fo' + (Join-Path $out 'rg05-v2-win32.obj')),
    ('/Fd' + (Join-Path $out 'compile.pdb')))
foreach ($include in $includePaths) { $arguments += '/I' + $include }
$arguments += @($source, '/link', '/MACHINE:X64', '/INCREMENTAL:NO', '/MANIFEST:NO',
    ('/OUT:' + (Join-Path $out 'rg05-v2-win32.node')),
    ('/IMPLIB:' + (Join-Path $out 'rg05-v2-win32.lib')),
    ('/PDB:' + (Join-Path $out 'link.pdb')), $nodeLib, 'kernel32.lib')
foreach ($library in $libPaths) { $arguments += '/LIBPATH:' + $library }

$savedEnvironment = @{}
foreach ($key in @('CL', '_CL_', 'LINK', '_LINK_', 'INCLUDE', 'LIB', 'LIBPATH', 'TMP', 'TEMP')) {
    $savedEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
}
try {
    # Prevent ambient compiler flags and temporary files escaping the output.
    foreach ($key in @('CL', '_CL_', 'LINK', '_LINK_', 'INCLUDE', 'LIB', 'LIBPATH')) {
        [Environment]::SetEnvironmentVariable($key, $null, 'Process')
    }
    $env:TMP = $out
    $env:TEMP = $out
    Push-Location -LiteralPath $out
    try {
        $boundary.Recheck()
        & $compiler @arguments
        $compileExit = $LASTEXITCODE
    } finally { Pop-Location }
    if ($compileExit -ne 0) { throw "Synthetic compilation failed with exit $compileExit." }
    Write-Output (Join-Path $out 'rg05-v2-win32.node')
} finally {
    foreach ($key in $savedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($key, $savedEnvironment[$key], 'Process')
    }
}
} finally { $boundary.Dispose() }
# No addon loading, tests, cleanup, installs or runtime namespace operations.
