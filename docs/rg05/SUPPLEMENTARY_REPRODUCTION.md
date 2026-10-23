# RG-05 supplementary L1–L3 reproduction

Status: proposed procedure, static review only; NOT RUN. Adding this patch does
not authorize execution. Authorize preparation/compiler work and native loading
separately. Never dot-source the runner.

## Current execution readiness

**ENVIRONMENT BLOCKED / FRESH REPRODUCIBILITY NOT VERIFIED**

The accepted static runner and boundary-preparation reviews establish reviewed
procedure text, not execution results. Neither preparation mode nor the staged
supplementary L1-L3 procedure has been executed. The accepted historical results
below remain separate and do not establish fresh-checkout reproducibility.

The bootstrap preflight found no admissible local preparation-script/runner
bundle outside sync storage. The Codex context did not satisfy authentication,
interactive-stdin or bootstrap TEMP/TMP admission; these observations do not
identify or validate a future authenticated interactive PowerShell session.
Local source, test, five Node headers and node.lib matched the approved hashes,
but their availability alone does not establish a trusted execution boundary.
Sync registration inspection found an unsupported provider registration and a
registered root with reparse ancestry. Both require STOP under current gates.

The read-only alternative-host inventory found no suitable existing candidate
in the inspected registrations and standard locations. Hyper-V inventory was
unavailable; uninspected portable, nonstandard or remote environments remain
unknown. No VM was created or started and no remote system was accessed.

Before any execution, separately establish an admissible Windows environment,
trusted local exact-byte inputs, bootstrap working directory and TEMP/TMP,
inspectable sync metadata and the authenticated interactive host prerequisites.
Do not relax gates, clear sync variables, reuse historical evidence or infer
authorization from this source patch. Inspect, Prepare and each L1-L3 stage
still require their own authorization. Protected-build and operational Win32
security remain **OPEN**; the RG-05 lifecycle is not complete.

[Historical closure](RG-05-V2.1_B01-B10_CLOSURE_MATRIX.md) records accepted
interactive L1 exit 0 (no preserved log), L2 compilation/linking and L3 18/18 PASS.
Future runs create new evidence. The historical binary hash is
A84A54BFE058CC7EC2DC3417CB9B507FC1E65F88A15A8DE50A835C85CA567E44.
MSVC binaries need not be byte-deterministic: approve the new binary hash, not a
forced match with that historical value. Do not substitute a historical binary.

## Prerequisites and trust boundary

[Runner](../../scripts/rg05-supplementary.ps1) contains its own directory-creation
interop, snapshots, child lifecycle and evidence checks. No old helper type or
retained PowerShell state is needed. It does not invoke the unmodified
[protected build reference](../../quality/api/scripts/build-rg05-v2-win32.ps1).
That script's mandatory security gates remain unchanged and OPEN.

| Prerequisite | Required reference |
|---|---|
| Windows | Trusted x64, local fixed NTFS; historical host build 10.0.26300.0 |
| MSVC | Toolset 14.44.35207; cl 19.44.35229.0; linker 14.44.35229.0 |
| SDK | 10.0.26100.0 include ucrt/shared/um, lib ucrt/x64 and um/x64 |
| Node | 24.15.0 x64; matching five development headers and x64 node.lib |
| PowerShell | 7.6.5 Core x64, FullLanguage, dedicated -NoProfile -NoExit -File process |
| Compile | C++17, Node-API 8, synthetic-only define, dynamic MSVC CRT |
| Load | Trusted x64 MSVCP140, VCRUNTIME140/VCRUNTIME140_1, UCRT and Windows DLLs |

Use a separately approved trusted environment. An offline Windows VM is a
candidate, not a preverified prerequisite. Require trusted offline installation
provenance, no unrelated writers to checkout/toolchain/kit/loader directories,
and immutable MSVC/SDK trees throughout execution. Executable hashes alone do
not authenticate transitive headers, libraries, DLLs or compiler subprocesses.
The runner checks paths/ACLs but does not recursively attest the whole toolchain.
If installation trust cannot be independently established, STOP.

Require an authenticated non-elevated runner, no impersonation, empty session
PSDefaultParameterValues. CheckPath validates trusted ownership at every ancestor,
not just the leaf; unreadable/untrusted metadata fails closed. Same-user processes,
SYSTEM, Administrators and the trusted OS installer are trusted; compromise by
them is outside this model.

Independently inspect active/configured sync providers, Cloud Files/SyncEngines
registrations, all relevant roots, ancestry and effective access. No shared
folders, redirected drives, host mappings or sync-backed checkout, kit, toolchain,
scratch or bootstrap TEMP are permitted. Empty OneDrive variables do not prove
isolation. Runner lexical/environment filters are not full provider discovery.
Unknown root/registration/redirect or insecure permissions means STOP; never
clear environment variables to hide roots.

Supply a preexisting verified NTFS scratch parent and protected existing TEMP/TMP
before launch. Their preparation requires separate review/authorization; the
runner does not repair them. Bootstrap Add-Type compiles in-process without
OutputAssembly; implementation-dependent cache/temp effects remain possible.
Require protected bootstrap TEMP/TMP and trusted working directory before its use.
No universal zero-write claim is made.

Each per-stage leaf must be absent. CreateDirectoryW creates its protected DACL
at creation time (runner, SYSTEM, Administrators), refuses collisions and never
adopts/repairs/reuses existing output. Children inherit from this new root.
Post-creation checks require exact owner, protected/canonical DACL and exactly one
explicit Allow FullControl ACE per expected principal, with ObjectInherit and
ContainerInherit, no propagation flags and no inherited or additional ACEs.
No installations, downloads, npm packages, TypeScript compiler, Playwright,
database, Docker or Python product dependencies are required.

## Preparation-only boundary step

[Preparation script](../../scripts/prepare-rg05-boundary.ps1) is proposed review
material; neither mode was run during implementation. Inspect and Prepare need
separate authorization. Never run the supplementary runner to prepare its own
prerequisites. Do not use historical helper types or change existing resources.

Bootstrap requires a reviewed, already-local preparation-script copy in trusted
non-sync storage, a trusted working directory, authenticated non-elevated
PowerShell 7.6.5 x64 and existing admissible TEMP/TMP. The script requires fresh
-NoProfile -File invocation and interactive stdin. Verify its reviewed SHA-256
before loading it. NoProfile does not itself establish installation/module trust.
If no admissible bootstrap exists, STOP: this script cannot bootstrap one by
compiling first and repairing permissions later.

The implementation currently supports only C: fixed NTFS and C:\ as creation
parent. It permits root CreateDirectories for the authenticated runner but
rejects unrelated ancestor delete/DACL/owner-changing rights. New descendants
have explicit protected DACLs, preventing inherited root Modify permissions.
All ancestor owners must match the runner's trusted set. There is no elevation.

Inspect performs metadata/ACL/environment and tool-hash checks, reads local sync
registrations, and invokes installed Windows subst (no arguments), mountvol C:\
/L and local Win32_Volume queries for storage corroboration. Outputs from those
read-only queries stay in memory. It does not call Add-Type, allocate a boundary,
copy inputs or write a manifest. It checks donor path syntax and lexical sync
exclusions only: weakly writable donors are data inputs, not executable/include
trust boundaries. Donor existence, no-follow metadata and byte hashes remain
explicitly PENDING until Prepare pins native handles. It does not traverse weak
donor directories using managed pathname APIs.

Supported sync registration formats are HKCU SyncEngines/Providers MountPoint
and HKLM SyncRootManager/UserSyncRoots. Missing accessible keys are distinguished
from denied access. Unsupported/unresolved registrations, non-C: roots, reparse,
offline or recall indicators cause STOP, not a guessed exclusion. Empty
environment variables are never the only isolation evidence. Registered roots
must themselves have readable, trusted, non-reparse ancestry; stale, cloud-tagged
or aliased registrations are unsupported and STOP bootstrap conservatively.
Registry parsing
does not attest the absence of unregistered third-party synchronizers; the
independent environment inventory and trusted installation premise remain
prerequisites to authorizing Prepare.

OneDrive/cloud-backed donors are deliberately rejected before content reads.
Use reviewed, already-local non-sync donor files; do not initiate hydration or
repair the original Node headers. Thus the current OneDrive checkout is not
automatically an admissible donor or bootstrap-script location.
The pinned supplementary runner is the reviewed LF blob with SHA-256
B1A15B3949B76D1AC7D9CDCBAE757F6ECC9DD9A76EB8859186A7C6EEA2614D5C.
Existing .gitattributes pins only the three original reference inputs, not that
runner or this preparation script. An autocrlf checkout can therefore differ.
Use a reviewed exact-byte local donor bundle and verify hashes; never normalize
or rewrite donors automatically to force admission. A future LF-policy change
would require separate review and is not part of this preparation patch.

After the explicit bootstrap gate, Prepare alone compiles its embedded helper
in the approved bootstrap TEMP. It pins every path component without following
reparse points, validates volume-GUID final paths and file IDs, then hashes all
nine donor streams before creating the boundary. Read-only donor handles deny
write/delete sharing; an existing conflicting writer causes STOP. The nine
inputs are the pinned supplementary runner, C++, test, five Node headers and
node.lib. It copies no donor ACLs, attributes, dependencies, logs or binaries.
MSVC/SDK/Node executables remain pinned/trusted in place.

CreateDirectoryW receives protected security descriptors at creation; file
creation uses CREATE_NEW with an explicit descriptor. Existing names are never
adopted or overwritten. All new directories/files are checked for exact owner,
three principals, masks and flags through their handles. Copies use retained
donor streams, then hashes and reopened identities/security are compared.
Closing an owned destination writer before reopening read-only is intentional;
the fresh protected tree excludes unrelated writers during that interval.

Only after final object checks is evidence/preparation.json created and read
back. It is PREPARED_CANDIDATE, not execution approval. Require the terminal
PREPARED status after successful disposal and independent manifest readback.
All local output is private: the attempt record identifies the fresh root even
if later preparation fails. Retain it and partial resources; do not retry, adopt,
delete, repair ACLs or act on historical evidence/handles. Bootstrap compilation
may leave implementation-dependent temporary artifacts in the approved TEMP.

Proposed separately authorized entrypoints, from the trusted local bootstrap
working directory (values are selected and verified locally, not inferred from
the original interactive session):

~~~powershell
$prep = Read-Host 'Reviewed local preparation-script path'
$donors = Read-Host 'Approved local non-sync donor workspace'
$headers = Read-Host 'Existing local Node development header directory'
$nodeLib = Read-Host 'Existing matching x64 node.lib'
$programs = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
$prepArgs = @('-NoProfile','-File',$prep,
    '-DonorRoot',$donors,'-NodeHeaders',$headers,'-NodeLibrary',$nodeLib,
    '-MsvcRoot',(Join-Path $programs 'Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\14.44.35207'),
    '-SdkRoot',(Join-Path $programs 'Windows Kits\10'),
    '-NodeExecutable',(Join-Path $env:ProgramFiles 'nodejs\node.exe'),
    '-ParentDirectory','C:\')
# INSPECT AUTHORIZATION ONLY. No mutation or preparation success is asserted.
& (Join-Path $PSHOME 'pwsh.exe') @prepArgs -Mode Inspect
if ($LASTEXITCODE -ne 0) { throw 'STOP_INSPECT' }
# STOP for independent inspection review and separate Prepare authorization.
# Only after that authorization, invoke the same arguments with -Mode Prepare.
~~~

Separately authorized Prepare entrypoint:

~~~powershell
& (Join-Path $PSHOME 'pwsh.exe') @prepArgs -Mode Prepare
if ($LASTEXITCODE -ne 0) { throw 'STOP_PREPARE_PRESERVE_PARTIALS' }
~~~

Inspect success means its bootstrap metadata checks completed, not that donor
existence/hashes, native path identities, all transitive provenance or preparation passed.
Before Prepare revalidate the actual session and arguments; it repeats preflight.
Do not treat an earlier Inspect result as a reusable admission token.

## Read-only identity preflight

From fresh checkout root, privately record the reviewed checkout commit and:

~~~powershell
git rev-parse HEAD
git status --short
git check-attr text eol -- quality/api/scripts/rg05-v2-win32.cc quality/api/scripts/build-rg05-v2-win32.ps1 quality/api/tests/rg05-v2-win32-negative.test.ts
Get-FileHash quality/api/scripts/rg05-v2-win32.cc,quality/api/scripts/build-rg05-v2-win32.ps1,quality/api/tests/rg05-v2-win32-negative.test.ts -Algorithm SHA256
$PSVersionTable.PSVersion
[Environment]::Is64BitProcess
$ExecutionContext.SessionState.LanguageMode
if ($null -ne [Environment]::GetEnvironmentVariable('NODE_REDIRECT_WARNINGS','Process')) {
    throw 'STOP_WARNING_REDIRECTION'
}
# Review parent startup configuration before starting a new PowerShell process.
# Report presence only; never print values.
foreach ($key in @('DOTNET_STARTUP_HOOKS','DOTNET_ADDITIONAL_DEPS',
    'DOTNET_SHARED_STORE','COR_ENABLE_PROFILING','CORECLR_ENABLE_PROFILING')) {
    if ([Environment]::GetEnvironmentVariable($key,'Process')) { throw 'STOP_STARTUP_CONFIGURATION' }
}
~~~

| File | Required SHA-256 |
|---|---|
| C++ source | 9308AD1EB738BAE7B71D5E9A8A4C0916F5302429771B5D0B7BDE4934045274D6 |
| Native test | 82F2001E118482CFDD0800E116D7CC317D57F36FFA084FD146B5D4BB6C1E4A6C |
| Protected build reference | D969E2A33A96D1514FD30C60140DC322F4C5AEFB516AF499EA46BF871F406AB4 |

The runner embeds source/test, cl/link/Node/node.lib and five Node header hashes.
It checks file version metadata and required SDK/CRT paths. Independently verify
the reference script hash above. Hash identity is not publisher authenticity.
The narrowly scoped .gitattributes preserves LF for all three reference inputs.
Do not publish raw preflight output or private installation paths.

## Exact separate entrypoints

These are future authorized commands, not executed patch-preparation steps.
Run from checkout root. The layout below matches reference public installation
locations; explicitly review alternate locations if needed. Read-Host values
are new explicit inputs, not missing helper implementations or old session state.
Use the trusted PowerShell installation and trusted built-in modules; -NoProfile
alone does not authenticate the executable, module search path or runtime startup.

~~~powershell
$pwsh = Join-Path $PSHOME 'pwsh.exe'
$boundary = Read-Host 'Independently verified private PREPARED boundary directory'
$runner = Join-Path $boundary 'workspace\scripts\rg05-supplementary.ps1'
$parent = Join-Path $boundary 'scratch'
$programs = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
$base = @{
    MsvcRoot = Join-Path $programs 'Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\14.44.35207'
    SdkRoot = Join-Path $programs 'Windows Kits\10'
    NodeHeaders = Join-Path $boundary 'node\include\node'
    NodeLibrary = Join-Path $boundary 'node\node.lib'
    NodeExecutable = Join-Path $env:ProgramFiles 'nodejs\node.exe'
}
$commonArgs = @('-NoProfile','-NoExit','-File',$runner,
    '-MsvcRoot',$base.MsvcRoot,'-SdkRoot',$base.SdkRoot,
    '-NodeHeaders',$base.NodeHeaders,'-NodeLibrary',$base.NodeLibrary,
    '-NodeExecutable',$base.NodeExecutable)
# Environment changes apply only to the dedicated child host. Retain its Process
# in this parent if start/completion is unknown; do not auto-kill or retry.
function Invoke-PreparedStage([string[]]$StageArguments) {
    $pending = Get-Variable RG05PreparedHost -Scope Script -ErrorAction SilentlyContinue
    if ($pending -and $null -ne $pending.Value) { throw 'STOP_HOST_RECOVERY_PENDING' }
    $script:RG05PreparedHost = [Diagnostics.Process]::new()
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $pwsh
    $info.UseShellExecute = $false
    $info.WorkingDirectory = Join-Path $boundary 'workspace'
    $info.Environment['TEMP'] = Join-Path $boundary 'temp'
    $info.Environment['TMP'] = Join-Path $boundary 'temp'
    foreach ($arg in ($commonArgs + $StageArguments)) { $info.ArgumentList.Add($arg) }
    $script:RG05PreparedHost.StartInfo = $info
    try {
        if (-not $script:RG05PreparedHost.Start()) { throw 'HOST_START' }
        $script:RG05PreparedHost.WaitForExit()
        $code = $script:RG05PreparedHost.ExitCode
    } catch { throw 'STOP_HOST_STATE_UNKNOWN_KEEP_PARENT_OPEN' }
    $script:RG05PreparedHost.Dispose()
    $script:RG05PreparedHost = $null
    return $code
}
~~~

L1, after its authorization:

~~~powershell
$l1 = Join-Path $parent 'rg05-synthetic-build-fresh-l1'
$code = Invoke-PreparedStage -StageArguments @('-Stage','L1','-WorkDirectory',$l1)
if ($code -ne 0) { throw 'STOP_L1' }
~~~

L1 uses /Zs /TP /std:c++17 /MD /EHsc /W4 /X with explicit includes and defines
NAPI_VERSION=8, RG05_SYNTHETIC_ONLY=1, WIN32_LEAN_AND_MEAN, NOMINMAX.
Exit 0, completed capture, no native binary/object artifacts and receipt readback
are required. Diagnostics/temp effects are possible.

L2, after L1 evidence review and separate L2 authorization:

~~~powershell
$l2 = Join-Path $parent 'rg05-synthetic-build-fresh-l2'
$code = Invoke-PreparedStage -StageArguments @('-Stage','L2','-WorkDirectory',$l2)
if ($code -ne 0) { throw 'STOP_L2' }
~~~

L2 adds /LD and explicit /Fo /Fd. Link flags are /MACHINE:X64 /INCREMENTAL:NO
/MANIFEST:NO, explicit /OUT /IMPLIB /PDB, node.lib, kernel32.lib and MSVC/SDK
library paths. Expected artifacts: .obj, .node, .lib, .exp; PDB/temp files possible.
Exit 0 plus PE32+ AMD64 DLL and both non-forwarded Node-API registration exports
are required. No loading occurs in L2. Review warnings from both streams before
acceptance; unexplained warnings STOP advancement. Record the new binary hash.

L3, only after independent approval of that exact new binary and L2 evidence:

~~~powershell
$l3 = Join-Path $parent 'rg05-synthetic-build-fresh-l3'
$approvedHash = Read-Host 'Independently approved fresh L2 binary SHA-256'
$l3Args = @('-Stage','L3','-WorkDirectory',$l3,
    '-Addon',(Join-Path $l2 'rg05-v2-win32.node'),'-ExpectedAddonSha256',$approvedHash)
$code = Invoke-PreparedStage -StageArguments $l3Args
if ($code -ne 0) { throw 'STOP_L3' }
~~~

L3 requires sibling fresh L2 result.json; historical manifests cannot substitute.
Node flags: --experimental-strip-types --test --test-isolation=none
--test-concurrency=1 --test-reporter=tap --test-timeout=30000, runtime guard
data-URL import and absolute test snapshot path. Test bytes are copied under
snapshot/quality/api/tests: calculated root is snapshot; explicit addon is external.
Only node:* imports and that addon are used. PASS requires exit 0, all 18 source
names in order, 18 pass and zero fail/cancelled/skipped/todo, no bailout/directives.
SKIP/TODO detection applies only to test-result lines; summary counters such as
the required "# todo 0" remain valid.

## Evidence, side effects and STOP

Each stage creates a private new root, source/five-header snapshots, stdout.bin,
stderr.bin and process.json (exit code, capture status, stream sizes/hashes, argv
hash). After verification and resource disposal, result.json records source,
tool/header/library/binary identities and false protected/operational claims.
These use a new schema, not the historical L2/L3 schema. Review streams and
receipt, retain receipt SHA-256 in private notes. Raw diagnostics can contain
private paths: never commit or publish them. Review unexpected L3 stderr too.
An append-only private launch.jsonl is created/flushed before Process.Start().
Events distinguish PREPARED, START_ATTEMPTED, START_REJECTED, START_CONFIRMED,
START_IDENTITY_CONFIRMED, EXIT_CONFIRMED and UNKNOWN_PROCESS_STATE (or confirmed
exit with capture still pending). Records contain launch ID, runner PID/start
time, resolved executable/arguments, available child PID/start time and exit code.
These recovery identifiers and private paths must never be published.
Ignore rules exclude exact root-level result.json/process.json/launch.jsonl
copies under quality/api and dedicated rg05-synthetic-build-* trees, without
globally hiding nested source fixtures with the same names.

Child-only PATH, TEMP/TMP and Node settings are controlled; parent/OneDrive
variables are unchanged. Ambient CL/_CL_/LINK/_LINK_/INCLUDE/LIB/LIBPATH and Node
preload/coverage/cache settings must be absent; child copies remove them too.
NODE_REDIRECT_WARNINGS is rejected even if present with an empty value and is
explicitly removed from the child environment, preserving stderr capture.
Pinned source/Node-header/addon handles disallow write/delete sharing while used.
MSVC/SDK remain trusted in place.

STOP on context/token/ACL/reparse/collision/hash/version/sync uncertainty,
missing dependencies, unexpected artifacts, child failure/timeout, incomplete
capture, malformed PE/exports, missing L2 receipt or any TAP discrepancy.
Exit 0 alone is insufficient. Publication/readback failure is not PASS.
process.json may survive later verification failure; capture failure can leave
partial streams without a completion receipt. Retain all partial artifacts:
no automatic cleanup, ACL repair, adoption or retry.

The wrapper waits for its child. Timeout or start/exit uncertainty never causes
automatic termination. It records the unknown state and retains the Process,
launch state/log, async capture tasks, pinned inputs/streams and runner identity
in the new dedicated host's global RG05SupplementaryRecovery object. It does not
dispose these resources as a substitute for confirmed exit. A private launch log
write failure does not discard that live recovery reference.

With recovery pending the script returns without ending its -NoExit host; the
invoking parent command remains waiting. The fixed RECOVERY_REQUIRED_NO_RETRY
marker is not PASS. Leave this host open; do not close it, rerun the runner,
choose a different output to retry, or manipulate historical snapshot handles.
Repeated invocation in that host refuses without replacing the recovery object.
Use a separately authorized manual recovery review of the original Process
reference and private launch identity; never act on a PID alone or auto-kill an
unknown child. If Start threw before child identity was available, the surviving
runner identity, attempted executable/arguments and original wrapper remain the
recovery evidence; they do not assert a confirmed child identity.

For known completion/failure the runner disposes only its own resources and
explicitly ends only this dedicated PowerShell process (code 0/1), overriding
-NoExit. Unknown process state or unfinished capture never reaches that exit.
Starting without the documented dedicated -NoExit -File host is rejected before
launch. Host termination/crash can still lose live handles; the already flushed
launch log remains evidence of an unresolved attempt, not permission to retry.

Inventory all files before/after review and explain unexpected artifacts.
L1 binary-extension detection is not an exhaustive filesystem monitor.
Pathname check/use intervals remain; trusted same-user/privileged actors can
interfere. Handles do not pin every ancestor/transitive input. Trust the approved
environment throughout; this does not replace protected namespace/identity checks.
Synthetic results prove no real HANDLE custody, operational ACL/process security,
lifecycle admission, semantic AI quality or current CI status.
Protected-build and operational RG-05 security remain OPEN.
