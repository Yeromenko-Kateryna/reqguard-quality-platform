# RG-07D-D1 — Evidence Package Schema & Integrity

Date: 2026-10-24 (Europe/Berlin). Mode: local implementation and offline testing.

**RG-07D-D1 REVIEW FIX READY**

Fresh review-fix results: accepted regression **297 passed**; D1 **170 passed, 3 skipped**
on both CPython 3.13.1 and 3.12.10. The three real symlink creation tests could
not execute under the Windows user's token (WinError 1314). Two actual NTFS
junction escape tests and three simulated symlink detection tests passed.
This is an explicit platform coverage limitation, not a claim that real symlink
tests passed. An independent run with symlink privileges remains desirable.

## Repository and exact changed paths

Repository: `Yeromenko-Kateryna/reqguard-quality-platform`.
Directory: `C:\Users\katal\OneDrive\Рабочий стол\projects\reqguard-quality-platform`.
Branch: `main`. Starting and final HEAD:
`3eb1a65ccca94628cf14d8b28add24d1582e932d` (matches requested baseline).

Exactly three new, unstaged files comprise this implementation:

- `reqguard/evaluation/evidence.py`
- `tests/test_evaluation_evidence.py`
- `docs/ai-quality/RG-07D-D1_IMPLEMENTATION_EVIDENCE.md`

No accepted RG-07A/B/C file, dataset, rubric, threshold, RG-06D file, workflow,
dependency or product API/UI file was edited. The root AGENTS.md was read.
There were 129 existing tracked/untracked files initially: 52 tracked and 77
untracked. Final inventory adds only these three paths (132 total, 80 untracked).
Pre-existing untracked work remains present. The initial fingerprint file was
written to an ephemeral sandbox temp directory and was unavailable to subsequent
processes; no before/after byte-hash proof is claimed for those untracked files.
All writes performed by this task targeted the three new files or external temp
test evidence. All 52 tracked files match HEAD under Git's clean filters.
Raw HEAD byte comparison encountered four existing CRLF/LF differences; Git's
filtered comparison and tracked diff are clean. No line ending repair was made.

## Implemented schema and public interfaces

Version: **`rg-evidence-package-v1`**. Metadata rejects unknown/missing fields,
unknown versions and inconsistent identities instead of migrating or repairing.
The current format accepts only the frozen dataset version/hash from `dataset.py`;
it also loads that fixture through the accepted loader. Input artifacts must
match UTF-8 bytes of the frozen example's requirement_text, including its hash
and length. Package JSON has its own canonical encoding; the frozen dataset's
serialization and the accepted evaluator manifest schema are unchanged.

Frozen dataclasses define the persisted structures:

| Structure | Fields |
|---|---|
| `PackageIdentity` | package_id, evaluation_run_id, dataset_version, dataset_sha256, version |
| `Artifact` | path, sha256, byte_length, evaluation_run_id, example_id, role, snapshot_id |
| `CaptureRecord` | capture_id, evaluation_run_id, example_id, input_reference, provenance_references, outcome, artifact_reference |
| `DerivedSnapshot` | snapshot_id, replay_id, evaluation_run_id, parent_snapshot_id, supersedes_snapshot_id, capture_ids, artifact_paths, finalized, seal |
| `PackageMetadata` | identity, inventory, captures, snapshots |

`EvidencePackage` interfaces:

```python
create(root, identity: PackageIdentity) -> EvidencePackage
EvidencePackage(root)  # attaches a reader/writer; does not create files
register_source(name, raw: bytes, *, role="source", example_id=None) -> Artifact
register_capture(capture_id, example_id, raw: bytes | None, *, outcome,
                 input_reference, provenance_references) -> CaptureRecord
create_snapshot(snapshot_id, replay_id, *, capture_ids,
                parent_snapshot_id=None, supersedes_snapshot_id=None) -> DerivedSnapshot
register_derived(snapshot_id, name, raw: bytes, *, example_id=None) -> Artifact
read_artifact(path) -> bytes
verify() -> PackageMetadata
finalize_snapshot(snapshot_id) -> Artifact  # checksum manifest descriptor
```

Module helpers: `serialize_metadata(value) -> bytes`, `parse_metadata(raw) -> object`.
Validation/storage operations fail with `EvidenceError`; no model outcome is
invented on operational failure. Storage references alone are validated here;
provider provenance contents, timings, evaluator assessments and human labels
are retained as caller-supplied opaque source/derived artifacts, not generated,
interpreted or certified by D1. No manifest completion defaults are supplied.

## Layout and invariants

```text
package/
  package.json
  sources/<evaluation_run_id>/<example_id or _run>/<name>
  sources/<evaluation_run_id>/<example_id>/<capture_id>.bin
  derived/<snapshot_id>/<evaluation_run_id>/<example_id or _run>/<name>
  seals/<snapshot_id>.json
  writer.lock                       # only during a cooperating writer operation
```

- `create` requires a new directory. Artifacts are exact bytes; no UTF-8 decode,
  JSON parsing, newline conversion or normalization touches their contents.
- Outcome vocabulary is the accepted `received`, `timeout`, `transport_error`.
  Received requires bytes, including `b""`; missing outcomes require `None`.
  Missing output persists a null artifact reference and no raw artifact.
  Empty received output persists a real zero-length file, length 0 and the
  SHA-256 of empty bytes. A reopened package preserves that distinction.
- An input and at least one provenance reference are required per capture.
  Each example may have at most one capture within the package's evaluation run,
  independent of capture ID or outcome (RG-07A section 2.1). Repeats require a
  separately identified run; this invariant applies to registration and loading.
  Provenance can be run-scoped or scoped to that same example. All inventory,
  capture and snapshot run IDs must equal the original evaluation run ID.
  Raw output paths retain their capture ID and have exactly one owning capture; derived inventory has exactly one
  owning snapshot. Duplicate inventory paths, capture references and derived
  references are rejected. Example IDs must exist in the frozen dataset.
- Package/capture/snapshot/replay IDs are ASCII tokens, length 1–64. Replay IDs
  cannot equal the original run ID or any capture ID; each replay and snapshot
  ID is unique case-insensitively. Original capture identity stays independent
  of later derived evaluation identity. Parent/superseded references must name
  earlier finalized snapshots, ruling out dangling links, forward links/cycles
  and cross-package lineage. Example-scoped derived artifacts require a capture
  for that example in their snapshot.
- Only portable ASCII package-relative paths are accepted. Absolute, drive,
  drive-relative, UNC, backslash, empty-component, dot/traversal, NUL, ADS and
  Windows device/trailing-dot paths are rejected. Inventory collisions are
  rejected case-insensitively. Every accessed ancestor and target is checked
  for symlinks/junctions; resolved paths must remain inside the package root.
- Metadata JSON is strict UTF-8, without BOM. It uses sorted object keys,
  compact separators, literal Unicode and no trailing newline. Duplicate keys
  at every depth, nonfinite/overflowed numbers and unpaired surrogates fail.
  Tuple/custom values and non-string dictionary keys are rejected by the public
  serializer. Persisted package.json must also match its canonical encoding.
  API inventory/capture ordering is deterministic; snapshot order records lineage.
- Every artifact descriptor contains a lowercase raw-byte SHA-256 and exact
  nonnegative integer byte length (booleans are rejected). Package dataset hash
  uses the accepted uppercase constant; it is not silently rewritten.
- A writer uses an exclusive create-if-absent lock. Same-directory temporary
  bytes are flushed/fsynced, then published with `os.link` for immutable files
  or `os.replace` for package.json. Immutable publication cannot replace an
  existing destination. Metadata is validated/serialized before publication.
  On caught publication failure, newly added artifacts are removed and the old
  package.json remains. Fault injection tests cover fsync, link and replace,
  including capture, derived registration and finalization rollback.
- First finalization freezes all source artifacts and captures for the package.
  Each finalized snapshot is closed to additional artifacts and re-finalization.
  New results need a new snapshot/replay identity. Even draft derived artifact
  paths are write-once; a second artifact needs a different path.
- Verification checks all descriptors, bytes, identity relationships, seal
  contents and unexpected files. It does not write/repair anything. Read-only
  tests compare file bytes and modification timestamps before/after verification.
  Unreadable inventory traversal fails explicitly. Empty directories are allowed.

## Integrity seal and trust boundary

The final checksum manifest contains identity, sorted source plus selected
snapshot artifact inventory, all immutable captures and the finalized snapshot
record without its seal descriptor. Its bytes are canonical JSON. The descriptor
in package.json stores the manifest's byte length/SHA-256, so no manifest hashes
itself and there is no checksum cycle. Later snapshots are excluded from earlier
manifests, permitting append without changing an earlier seal. Verification
checks both the manifest checksum and its exact reconstructed content. Changing
source bytes and only updating their package inventory checksum still fails the
retained finalized seal.

These checks establish local consistency with the supplied manifests and pinned
dataset, not independent authenticity. Anyone able to replace evidence and all
associated checksums can construct another consistent package; removing an
entire history and replacing its manifests is not externally detectable here.
A separately trusted digest/signature over each final manifest and its expected
package/snapshot identity would anchor that content outside the writable package
and permit substitution/rollback detection relative to that trusted record.
No signing, external trust service or authenticity claim is implemented.

## Original D1 commands and historical results (before targeted review fix)

The previously available isolated evaluator environment was reused; no installs
or dependency updates were needed. Command abbreviations for reproducibility:

```powershell
$P = 'C:\Users\katal\AppData\Local\Temp\reqguard-rg07c-validation\managed-venv\Scripts\python.exe'
$Q = '.\.venv\Scripts\python.exe'
$T = 'C:\Users\katal\AppData\Local\Temp'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTEST_ADDOPTS = ''
```

Final test commands (executed outside sandbox because its temp permissions
prevent pytest's temporary-directory fixture):

```powershell
& $P -c 'import sys,unicodedata; print(sys.version); print(unicodedata.unidata_version); assert sys.version_info[:3] == (3,13,1) and unicodedata.unidata_version == "15.1.0"'
& $P -m pytest -q -ra --strict-config --strict-markers -o addopts= -p no:cacheprovider --junitxml="$T\rg07d-d1-regression.xml" tests/test_evaluation_dataset.py tests/test_evaluation_hard_fail.py tests/test_evaluation_metrics.py
& $P -m pytest -q -ra --strict-config --strict-markers -o addopts= -p no:cacheprovider --junitxml="$T\rg07d-d1-new.xml" tests/test_evaluation_evidence.py
& $Q -c 'import sys; print(sys.version); assert sys.version_info[:2] == (3,12)'
& $Q -m pytest -q -ra --strict-config --strict-markers -o addopts= -p no:cacheprovider --junitxml="$T\rg07d-d1-py312.xml" tests/test_evaluation_evidence.py
```

| Final check | Outcome | Exit | Pytest runtime |
|---|---|---|---|
| CPython/Unicode guard | 3.13.1 / Unicode 15.1.0 | 0 | n/a |
| Accepted dataset/hard_fail/metrics regression | 297 passed; 0 failures/errors/skips | 0 | 2.36s |
| D1 under CPython 3.13.1 | 155 collected; 152 passed; 3 skipped; 0 failures/errors | 0 | 12.58s |
| Product Python guard | CPython 3.12.10 | 0 | n/a |
| D1 under CPython 3.12.10 | 155 collected; 152 passed; 3 skipped; 0 failures/errors | 0 | 12.84s |

Distinct coverage is **8 positive cases + 144 negative/mixed cases passed + 3
real symlink cases skipped**. Both interpreter runs execute the same cases;
they are not 304 distinct tests. JUnit XML counts were independently parsed
using `xml.etree.ElementTree` and agree. JUnit suite durations (excluding pytest
startup/summary overhead) are respectively 2.245s, 12.177s and 12.786s.

The positive group is binary round-trip (4 parameter cases), missing/empty,
deterministic package encoding, appended snapshot lifecycle and empty snapshot
finalization. Other tests include rejection/mutation checks, hence are classified
as negative/mixed rather than inflating the positive count.

Adversarial coverage includes invalid binary metadata, BOM, duplicate nested JSON
keys, invalid Unicode/numbers, unsupported versions, missing/truncated/tampered
files, bad checksum/length types, raw bytes plus rewritten inventory checksum,
unsafe paths on registration/read/persisted metadata, Windows path aliases,
actual junction escapes, simulated symlink detection, duplicate inventories and
owners, mixed run/example references, wrong frozen inputs/provenance roles,
missing/received contradictions, broken lineage, duplicate replay IDs, source
freeze, finalized snapshot mutation, unexpected files, stale writer locks,
noncanonical metadata and publication-failure rollback.

Earlier diagnostic runs are retained here rather than represented as passes:

| Attempt | Result | Exit | Runtime |
|---|---|---|---|
| Initial D1 command inside sandbox, no JUnit | 16 passed, 122 temp-fixture errors | 1 | 25.94s |
| Diagnostic `& $P -m pytest -xq -p no:cacheprovider tests/test_evaluation_evidence.py` inside sandbox | 1 temp-fixture error, stopped at first error | 1 | 0.36s |
| First D1 outside sandbox, no JUnit | 135 passed, 3 symlink-creation failures (WinError 1314) | 1 | 10.68s |
| Interim D1 with explicit skips, junction and detection tests | 140 passed, 3 skipped | 0 | 12.86s |
| Regression attempted inside sandbox, no JUnit | 279 passed, 18 temp-fixture errors | 1 | 5.62s |
| D1 before final capture-ID binding, Python 3.13.1 | 151 passed, 3 skipped | 0 | 12.30s |
| D1 before final capture-ID binding, Python 3.12.10 | 151 passed, 3 skipped | 0 | 13.32s |

The initial/outside and sandbox commands used the same final pytest options
shown above, omitting only `--junitxml` where noted. Interim D1 used the final
new-suite JUnit path. No passing result depends on suppressing validation errors;
skips apply only to fixture creation when Windows reports symlink privilege 1314.
`uv python find --offline 3.12` initially hit sandbox cache-write errors; rerun
outside sandbox returned the existing `.venv\Scripts\python.exe`, exit 0.

Other executed inspections: `Get-Location`, `git branch --show-current`,
`git rev-parse HEAD`, `git status --short`, `git status --porcelain=v1 -uall`,
`rg --files`, `Get-Content` for AGENTS/spec/evaluator/CI/evidence files,
`Get-Command uv`, interpreter existence checks, and offline Python inventory,
hash and JUnit-count inspections. Relevant official Python documentation was
consulted for [publication primitives](https://docs.python.org/3.12/library/os.html#os.replace),
[junction detection](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path.is_junction)
and [duplicate JSON keys](https://docs.python.org/3.12/library/json.html#repeated-names-within-an-object).

Git verification commands: `git diff --check`, `git diff --exit-code HEAD`,
`git diff --cached --exit-code`, and a per-tracked-file comparison of
`git hash-object --path <path> <path>` against `git rev-parse HEAD:<path>`:
all exit 0; 52 tracked paths, zero Git-filtered differences.
`git diff --stat` is empty because all three implementation files are untracked.
No files were staged. Per-new-file `git diff --no-index --stat -- /dev/null
<path>` (on Windows, `NUL`) reports additions and returns the expected exit 1;
the final line counts/diffstat are recorded below after the scope audit.

Original D1 scope audit (before targeted review fix; no staging required):

```text
reqguard/evaluation/evidence.py                           534 insertions(+)
tests/test_evaluation_evidence.py                         557 insertions(+)
docs/ai-quality/RG-07D-D1_IMPLEMENTATION_EVIDENCE.md        301 insertions(+)
3 new files; 1392 insertions(+); 0 deletions
```

Final Git status adds exactly `??` entries for the three implementation files
to the original untracked inventory. Original `ChatGPT file/`, RG-04 evidence
and quality/api untracked paths remain. Tracked/staged diffstat is empty;
HEAD and branch remain as recorded above. No-index `--stat` and `--check` commands
return 1 because they compare an empty file with additions, not because a check
failed. Git's LF-to-CRLF advisory was observed; no conversion was performed.

## Limitations and operations NOT RUN

- Immutability is enforced by this API and verified checksums, not filesystem
  ACLs or independent authenticity. It does not resist an actor replacing both
  data and manifests or racing path checks with hostile filesystem mutations.
- Designed for a local filesystem supporting hard links and atomic replacement,
  with one cooperating writer. Windows NTFS was exercised. Network shares,
  power-loss durability and concurrent hostile writers were NOT TESTED.
- Atomicity concerns complete per-file publication and rollback of caught errors,
  not an atomic whole-directory transaction. Process termination can leave a
  lock, staging file or unreferenced artifact; verification fails closed on
  unreferenced files. A stale lock blocks writers. No automatic recovery/repair
  dispatcher exists. Create failure can leave a newly created incomplete root;
  it cannot replace an existing package. Empty directories may remain on rollback.
- Whole artifacts/metadata are read into memory; resource quotas/streaming are
  outside D1. Opaque source/derived JSON-looking artifacts are not interpreted as
  package metadata or certified as valid evaluator manifests/results.
- Real file/directory/root symlink checks are **SKIPPED (3)** on this token.
  Actual NTFS junction checks and simulated symlink guards passed. POSIX and
  privileged Windows symlink execution were NOT RUN.
- Docker, PostgreSQL, browsers, FastAPI/UI suites, network/provider/model calls,
  semantic evaluation, annotation import/generation, replay runner, CLI, CI
  execution, signing and external trust services: NOT RUN / outside D1 scope.
- No claim of live-model semantic quality, authenticity, human annotation
  completeness or CI success follows from these storage tests.
- Commit, push, PR, publication, remote mutation and paid AI calls: NOT RUN /
  not performed, as instructed.

Next step: independent review of D1, including execution of the three real
symlink cases on a platform/token permitting symlink creation.

## Targeted review fix — one capture per example per run

**RG-07D-D1 REVIEW FIX READY**. Review-fix baseline: branch `main`, HEAD
`3eb1a65ccca94628cf14d8b28add24d1582e932d`, 132 tracked/untracked files including
the three existing untracked D1 implementation files. The previous sections'
test counts, timings and diffstat are historical; the fresh results below
supersede them for this review fix.

The reported defect was reproduced before changing production validation:
18 new cases failed with `DID NOT RAISE EvidenceError` (155 other cases
deselected), exit **1**, **3.52s**. Each outcome pairing across `received`,
`timeout`, `transport_error` reproduced acceptance of a duplicate F01, both
through the public API and otherwise consistent persisted metadata.

`EvidencePackage._validate` now maintains `captured_examples` and rejects a
second occurrence with `EvidenceError("Duplicate example capture")`. All capture
run IDs are already checked against the package's original evaluation run ID,
so example uniqueness enforces the per-run invariant. It is independent of
capture ID and outcome and also covers received empty bytes. `_commit` validates
before publishing files, so a rejected registration leaves the existing package
intact; `verify()` applies the same rule to packages loaded from disk. Schema
version, dataclass fields, outcome vocabulary and public interfaces are unchanged.
Previously valid packages with one capture per example remain readable. Duplicate
packages formerly accepted through the defect are now explicitly rejected, never
repaired or silently deduplicated.

Exact source/test changes (current one-based lines):

- `reqguard/evaluation/evidence.py`: line 292 adds the set; lines 299–300 reject
  duplicate example IDs and add each validated example. Three lines added.
- `tests/test_evaluation_evidence.py`: lines 79–92 change the missing/empty/error
  round-trip to F01/F02/F03 and assert all three example identities survive reload.
- Same test file, lines 534–553: capture publication-failure coverage now attempts
  F02 with its own input/provenance; it still reaches the injected `os.replace`
  failure instead of stopping at duplicate validation.
- New `test_register_capture_rejects_duplicate_example`, line 565: nine outcome
  pairs, different capture IDs, unchanged bytes/timestamps after rejection and
  successful reopening of the original one-capture package.
- New `test_verify_rejects_duplicate_example_captures`, line 580: nine outcome
  pairs. Starts with valid F01/F02 captures, then rewrites the second to F01 and
  updates input/raw inventory/path consistently. Read-only verification must
  reject the duplicate itself; no unrelated broken reference explains failure.
- This evidence file: lines 5/7 (verdict/results), 102–104 (invariant), 168/259
  (historical labels), 306 onward (review fix). No other repository file changed.

Fresh commands, using the existing `$P`, `$Q`, `$T` definitions above and
`PYTHONDONTWRITEBYTECODE=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, empty
`PYTEST_ADDOPTS`:

```powershell
# Before production fix: expected reproduction failure, exit 1.
& $P -m pytest -q -ra --tb=short --strict-config --strict-markers -o addopts= -p no:cacheprovider tests/test_evaluation_evidence.py -k 'rejects_duplicate_example'
# After fix: both interpreter guards exit 0.
& $P -c 'import sys,unicodedata; print(sys.version); print(unicodedata.unidata_version); assert sys.version_info[:3] == (3,13,1) and unicodedata.unidata_version == "15.1.0"'
& $Q -c 'import sys; print(sys.version); assert sys.version_info[:2] == (3,12)'
& $P -m pytest -q -ra --strict-config --strict-markers -o addopts= -p no:cacheprovider --junitxml="$T\rg07d-d1-review-fix.xml" tests/test_evaluation_evidence.py tests/test_evaluation_dataset.py tests/test_evaluation_hard_fail.py tests/test_evaluation_metrics.py
& $Q -m pytest -q -ra --strict-config --strict-markers -o addopts= -p no:cacheprovider --junitxml="$T\rg07d-d1-review-fix-py312.xml" tests/test_evaluation_evidence.py
```

| Fresh execution | Collected | Passed | Skipped | Failed/errors | Exit | Pytest runtime |
|---|---|---|---|---|---|---|
| CPython 3.13.1, Unicode 15.1.0: D1 plus accepted regression | 470 | 467 | 3 | 0/0 | 0 | 17.22s |
| CPython 3.12.10: full D1 | 173 | 170 | 3 | 0/0 | 0 | 16.70s |

JUnit XML was parsed independently with `xml.etree.ElementTree` and grouped by
test module: D1 **170 passed / 3 skipped**, dataset **59 passed**, hard_fail
**118 passed**, metrics **120 passed**. Thus all accepted **297** regression
tests passed without skips. Both new regression functions passed all **18**
parameter cases after failing all 18 before the fix. D1 coverage is now 8
positive and 162 negative/mixed passed cases plus 3 skips; interpreter runs
are repetitions of the same cases, not additional distinct coverage.

The actual skips are unchanged: real file, directory and root symlink tests
cannot create their fixtures because Windows reports **WinError 1314**. Two
actual NTFS junction cases and three simulated symlink guards passed in both
full D1 runs. Tests used external system temporary directories. Elevated tool
execution was used because sandbox temporary-directory permissions blocked
pytest during the original implementation; no new dependencies were installed.

Scope/preservation verification: all 132 baseline file paths remain present;
SHA-256 comparison against the review-fix start snapshot reports exactly the
three authorized files changed and zero unrelated byte changes. Branch/HEAD
remain unchanged. `git diff --exit-code HEAD`, `git diff --cached --exit-code`
and `git diff --check` return 0. `git status --short` retains the original
untracked entries, including these three D1 files; no new repository paths
were introduced. Since the D1 files remain untracked, tracked `git diff --stat`
is empty. Local `git diff --no-index` against before-fix copies records the
review delta: source +3/-0, tests +55/-7, evidence +103/-4 (expected exit 1 for differences).

Limitations are unchanged: local consistency checks do not establish external
authenticity or live-model quality. Real symlink creation remains untested on
this token. Docker, databases, browsers, CI, provider/model execution, annotation,
commit, push, PR and all remote operations were **NOT RUN**, outside the
authorized targeted fix. No accepted RG-07A/B/C, dataset, dependency or workflow
file was edited. Next step: independent review of the capture-uniqueness fix.
