# RG-07D-D2-CI — Local CI integration evidence

Date: 2026-10-25 (Europe/Berlin).
Mode: LOCAL IMPLEMENTATION / NO COMMIT / NO PUSH.

RG-07D-D2-CI READY FOR INDEPENDENT REVIEW

Fresh local evidence: **101 collected, 101 passed, zero failures/errors/skips** on
Python 3.13.1 / Windows. The exact JUnit gate extracted from the workflow accepted
this fresh report, exit 0. This is mechanical fake execution verification, with
no semantic model quality verdict. Hosted GitHub Actions and Ubuntu execution
have not been performed.

## Baseline and scope

Repository: `C:/Users/katal/OneDrive/Рабочий стол/projects/reqguard-quality-platform`.
Initial/final branch: `main`.
Initial/final HEAD: `24dddc9b6c4107e398f14da292dee8267f8fd0fe`.

Exactly two authorized paths differ from the initial state:

- Modified: `.github/workflows/rg07c-evaluator.yml`, 124 added lines.
- Added, untracked: `docs/ai-quality/RG-07D-D2_CI_IMPLEMENTATION_EVIDENCE.md`.

No D2 source/test/contract edits. No changes to D1, RG-07A, datasets, dependencies,
Docker, product API, RG-06D, or the two existing jobs. No staging or Git writes.
Initial tracked/index status was clean, with 77 unrelated untracked files.
The 61 tracked-file byte-size/SHA-256 baseline and the 77 unrelated-file
path/size/SHA-256 baseline were captured before editing.

The original workflow is an unchanged **8577-byte prefix**, SHA-256
`9190e1891e3c1c781944d94eff003432144aad591812e80b2286a95324a56e76`.
This protects the existing job text, gates and triggers byte for byte.
Parsed top-level configuration (including push/PR main triggers) and parsed
`evaluator` / `evidence-integrity` equality were additionally verified.
The original 297-pass/zero-skip evaluator gate and 173-collected/171-pass/exactly
two NTFS-skip evidence gate retain their original code and expected identities.
Those suites were not rerun for this change; their gates were preserved rather
than replaced with local Windows counts.

## New job and dependencies

Independent `fake-execution` job; no needs/services/container; Ubuntu 24.04;
15-minute timeout for this new job only; contents:read permissions.
Checkout credentials are not persisted. Existing action pins are reused exactly:

- `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1`.
- `astral-sh/setup-uv@07a047e608db84b3d8c06cd9a7c7dcc9c355c18e`.
- uv 0.11.22, Python 3.13.1, setup cache disabled.

An explicit pre-test guard requires Python 3.13.1 and Linux. Environment,
fixtures, working directory, requirements and JUnit report are under
RUNNER_TEMP; cwd and basetemp are siblings, outside the checkout.
Bytecode/plugin autoload/pytest cache are disabled, PYTEST_ADDOPTS is cleared,
and `-o addopts=` prevents configured selectors. Only the two accepted D2 test
paths are passed to pytest, with strict config and markers.

Dependencies use the existing frozen dev-only export with httpx pruned and
no emitted project, then `uv pip sync --require-hashes --only-binary :all:`.
The product is not installed: its Python 3.12 metadata/lock is unchanged.
The offline frozen export succeeds with the existing uv 0.11.22.
The existing isolated Python 3.13.1 venv contains exactly the locked six Windows
distributions: pytest 9.1.1, iniconfig 2.3.0, packaging 26.3, pluggy 1.6.0,
Pygments 2.21.0, colorama 0.4.6. Colorama has a win32 marker and is excluded on
Linux. No new dependencies were installed or added. Recreating the environment
and hash-locked sync locally were not performed; the existing isolated venv was
reused. No dependency incompatibility was observed.

CI bootstrap needs action/Python/package downloads. Offline test execution means
no external AI provider, network model call, database, Docker or paid service;
it is not a claim of air-gapped bootstrap.

## Fail-closed JUnit gate

The gate uses `if: ${{ !cancelled() }}`, so it also checks a report after a
nonzero pytest result. No continue-on-error, retries, selector, fallback report or
ignored exit code is used. A failed test step remains a failed job.

The gate requires:

1. Exactly one flat testsuite; explicit integer suite counters 101/0/0/0.
2. Exactly 101 direct, distinct testcase identities with nonempty names and exact
   classnames `tests.test_evaluation_fake_provider` /
   `tests.test_evaluation_execution`.
3. Zero failure/error/skipped elements anywhere in the XML; unexpected suite or
   testcase result elements and unexpected statuses also fail.
4. The entire accepted identity set, not only a count. Canonical identity bytes
   are ASCII JSON of sorted (classname,name) pairs, compact comma/colon separators.
   SHA-256 is `043f6dc73a4f66eb7680f053fa3999ed9bbe64c556e746264fb5f2537a73d4c5`.
   Thus a noncritical rename or balanced omission/replacement also fails.
5. Fifteen explicit critical identities, printed individually on success.
   They cover deterministic fixtures, full twelve-example nominal byte roundtrip,
   mixed missing/empty/malformed packages, before/exactly-at/after deadline,
   single-attempt unresolved contract errors, partial storage failure/cancellation,
   simulated timeout, observed checkpoint expiry, late returned correlation,
   transport error and nominal returned correlation. Their literal names appear
   in the exact workflow diff below; the full identity hash includes all eight
   accepted RF-01/RF-02 cases.

Missing/malformed XML and missing/noninteger counters fail with nonzero status.
The XML gate establishes exact mechanical test execution, not semantic quality.

## Local commands and results

External evidence root:
`C:/Users/katal/.codex/visualizations/2026/10/24/01a17025-59ea-7113-a0dc-b0958832e685/rg07d-d2-ci`.

PowerShell variables used below:

```powershell
$R = 'C:/Users/katal/OneDrive/Рабочий стол/projects/reqguard-quality-platform'
$P = 'C:/Users/katal/AppData/Local/Temp/reqguard-rg07c-validation/managed-venv/Scripts/python.exe'
$S = 'C:/Users/katal/.codex/visualizations/2026/10/24/01a17025-59ea-7113-a0dc-b0958832e685/rg07d-d2-ci'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTEST_ADDOPTS = ''
```

Collection and execution used external cwd `$S/work`; both directories were
created before launching the final commands:

```powershell
Set-Location "$S/work"
& $P -m pytest --collect-only -q --strict-config --strict-markers -c "$R/pyproject.toml" -o addopts= -p no:cacheprovider "$R/tests/test_evaluation_fake_provider.py" "$R/tests/test_evaluation_execution.py"
# 101 collected in 0.29s; exit 0
& $P -m pytest -q -ra --tb=short --strict-config --strict-markers -c "$R/pyproject.toml" -o addopts= -p no:cacheprovider --basetemp="$S/pytest-tmp" --junitxml="$S/d2.xml" "$R/tests/test_evaluation_fake_provider.py" "$R/tests/test_evaluation_execution.py"
# 101 passed in 335.60s; exit 0; zero skips/errors/failures
Set-Location $R
& $P "$S/junit_gate.py" "$S/d2.xml"
# exit 0: collected=101 passed=101; counters 101/0/0/0; all 15 anchors PASS
& $P "$S/validate_workflow.py"
# exit 0: preserved prefix/jobs/triggers; 5 bash syntax checks; 2 Python AST checks;
# 28 synthetic gate probes: 1 valid accepted, 27 invalid rejected
$env:UV_CACHE_DIR = "$S/uv-cache"
uv export --offline --frozen --only-group dev --prune httpx --no-emit-project --no-header --output-file "$S/requirements.txt"
# exit 0
git diff --exit-code -- pyproject.toml uv.lock
# exit 0
git diff --check
git diff --cached --exit-code
# both exit 0
```

The test process ran outside the Windows sandbox because pytest temporary-folder
creation was previously blocked there. Syntax/probe validation also ran outside
the sandbox because MSYS bash previously encountered sandbox IPC restrictions.
The actual gate requires only Python's standard library.

A local invocation of the extracted Linux/Python guard deliberately rejected
win32, exit 1; it was not counted as a D2 test failure or Linux execution.
Two preliminary local command issues were corrected: cwd was initially supplied
before creating it, and a quoted PowerShell pipeline executable needed the call
operator. These were setup commands, not successful test evidence.

Validation uses already-cached PyYAML 6.0.3 BaseLoader (no installation). It
checks top-level/job equality, action pins, runner/env/isolation, absence of
services/needs/continue-on-error, shell/Python syntax, then extracts the actual
gate for probes. Five `bash -n` commands and both `ast.parse` checks passed.
Synthetic negative cases include aggregate mismatches, absent/noninteger
counters, hidden failure/error/skip nodes, suite-level/nested errors, duplicate
or foreign identities, missing/empty names, omitted/extra cases, critical and
noncritical renames, nested/extra suites, non-direct cases, invalid status, and
missing/malformed XML. Every negative invocation returned exit 1. These probes
test gate behavior only; the fresh d2.xml separately passed the same final gate.

PyYAML parsing plus the targeted checks is not a full GitHub Actions schema
validator. actionlint was not found; schema/actionlint validation is NOT RUN.
No replacement validator was installed. No Ubuntu runner was available for
this local execution; its exact-platform guard is retained for CI. Existing
test identities are pinned using pytest 9.1.1; the fresh Windows JUnit confirms
the expected classnames and identity digest. Hosted Linux behavior still needs
independent execution after a separate publication decision.

Artifacts outside the repository:

- [Actual JUnit](C:/Users/katal/.codex/visualizations/2026/10/24/01a17025-59ea-7113-a0dc-b0958832e685/rg07d-d2-ci/d2.xml)
- [Extracted gate](C:/Users/katal/.codex/visualizations/2026/10/24/01a17025-59ea-7113-a0dc-b0958832e685/rg07d-d2-ci/junit_gate.py)
- [Validation/probe outcomes](C:/Users/katal/.codex/visualizations/2026/10/24/01a17025-59ea-7113-a0dc-b0958832e685/rg07d-d2-ci/validation-results.json)
- [Run and actual-gate result](C:/Users/katal/.codex/visualizations/2026/10/24/01a17025-59ea-7113-a0dc-b0958832e685/rg07d-d2-ci/d2-run-result.json)
- [Full accepted identities](C:/Users/katal/.codex/visualizations/2026/10/24/01a17025-59ea-7113-a0dc-b0958832e685/rg07d-d2-ci/accepted-identities.json)
- [Unrelated before manifest](C:/Users/katal/.codex/visualizations/2026/10/24/01a17025-59ea-7113-a0dc-b0958832e685/rg07d-d2-ci/unrelated-before.json)
- [Unrelated after manifest](C:/Users/katal/.codex/visualizations/2026/10/24/01a17025-59ea-7113-a0dc-b0958832e685/rg07d-d2-ci/unrelated-after.json)
- [Protected tracked hashes](C:/Users/katal/.codex/visualizations/2026/10/24/01a17025-59ea-7113-a0dc-b0958832e685/rg07d-d2-ci/preservation-results.json)

## Preservation hashes

All original tracked files except the authorized workflow retain their byte
sizes and SHA-256; all 77 unrelated untracked files retain paths, sizes and SHA-256.
The new evidence document is the only added repository file. The index is clean.
The accepted D2 files, lock/config and separate E2E workflow remain:

| Path | Bytes | Unchanged SHA-256 |
| --- | ---: | --- |
| `reqguard/evaluation/fake_provider.py` | 7331 | `78e1d4e5226cbe8bfa7d5cd4a4ccc026393c870788e95530b0b9dcfb8a7d79d1` |
| `reqguard/evaluation/execution.py` | 14573 | `7d358644e5e3440b9fbb468ab0fda4a70a4ac6b1a577ede9335af6a74f12806a` |
| `tests/test_evaluation_fake_provider.py` | 5062 | `a643785d2d8e8f1ed0db822c7b495295042719735025f1541c934de26a325bb4` |
| `tests/test_evaluation_execution.py` | 20038 | `a3633e5c84c5f16ba5b38d20aba5f5e3b156f90fe3e212916bad0fa5d49dfcc3` |
| `docs/ai-quality/RG-07D-D2_EXECUTION_CONTRACT.md` | 28504 | `f2ebbb2f95b53e17658541a9faf932560a31d7ff7abcc50ac1fc6255009b3313` |
| `pyproject.toml` | 327 | `708ab1cadfdf63389ea20bf135bdbf617ebdee21934666405fbae9d9d8b0ae61` |
| `uv.lock` | 29306 | `beb73ced74468486e72eb4f9ca5cb8d5172d965ad1c96e7340c6dc4b6dbda494` |
| `.github/workflows/rg06d-e2e.yml` | 4079 | `3f97d7215aa92d06045a163910253e1631692c5828e6f0f37c88e737e90b2bd9` |

## Exact workflow diff

```diff
diff --git a/.github/workflows/rg07c-evaluator.yml b/.github/workflows/rg07c-evaluator.yml
index 9f77e0f..8739d1f 100644
--- a/.github/workflows/rg07c-evaluator.yml
+++ b/.github/workflows/rg07c-evaluator.yml
@@ -173,3 +173,127 @@ jobs:
           print(f"RG-07D-D1 collected=173 passed={passed} counts={counts}")
           print(f"Platform skips: {sorted(skipped)}; reason: {reason}")
           PY
+
+  fake-execution:
+    name: Offline fake execution (101 cases, mechanical only)
+    runs-on: ubuntu-24.04
+    permissions:
+      contents: read
+    timeout-minutes: 15
+    defaults:
+      run:
+        shell: bash
+    env:
+      PYTHONDONTWRITEBYTECODE: '1'
+      PYTEST_DISABLE_PLUGIN_AUTOLOAD: '1'
+      PYTEST_ADDOPTS: ''
+    steps:
+      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
+        with:
+          persist-credentials: false
+      - uses: astral-sh/setup-uv@07a047e608db84b3d8c06cd9a7c7dcc9c355c18e # v10.3.2
+        with:
+          version: '0.11.22'
+          python-version: '3.13.1'
+          enable-cache: false
+      - name: Create isolated Python 3.13.1 fake execution environment
+        run: uv venv --no-project --python 3.13.1 "$RUNNER_TEMP/rg07d-d2-venv"
+      - name: Require Python 3.13.1 on Linux
+        run: |
+          "$RUNNER_TEMP/rg07d-d2-venv/bin/python" - <<'PY'
+          import sys
+          print(f"Python: {sys.version}; platform: {sys.platform}")
+          if sys.version_info[:3] != (3, 13, 1) or sys.platform != "linux":
+              sys.exit("RG-07D-D2 requires Python 3.13.1 on Linux")
+          PY
+      - name: Install only hash-locked pytest dependencies
+        run: |
+          set -euo pipefail
+          uv export --frozen --only-group dev --prune httpx --no-emit-project --no-header \
+            --output-file "$RUNNER_TEMP/rg07d-d2-requirements.txt"
+          uv pip sync --python "$RUNNER_TEMP/rg07d-d2-venv/bin/python" --require-hashes --only-binary :all: \
+            "$RUNNER_TEMP/rg07d-d2-requirements.txt"
+          uv pip list --python "$RUNNER_TEMP/rg07d-d2-venv/bin/python"
+          git diff --exit-code -- pyproject.toml uv.lock
+      - name: Run only the accepted D2 suites outside the repository (expected 101)
+        run: |
+          set -euo pipefail
+          mkdir -p "$RUNNER_TEMP/rg07d-d2-work"
+          cd "$RUNNER_TEMP/rg07d-d2-work"
+          "$RUNNER_TEMP/rg07d-d2-venv/bin/python" -m pytest -v -ra --strict-config --strict-markers \
+            -c "$GITHUB_WORKSPACE/pyproject.toml" -o addopts= -p no:cacheprovider \
+            --basetemp="$RUNNER_TEMP/rg07d-d2-pytest-tmp" \
+            --junitxml="$RUNNER_TEMP/rg07d-d2-pytest.xml" \
+            "$GITHUB_WORKSPACE/tests/test_evaluation_fake_provider.py" \
+            "$GITHUB_WORKSPACE/tests/test_evaluation_execution.py"
+      - name: Require 101 passes, exact suite identities and critical execution coverage
+        if: ${{ !cancelled() }}
+        run: |
+          "$RUNNER_TEMP/rg07d-d2-venv/bin/python" - "$RUNNER_TEMP/rg07d-d2-pytest.xml" <<'PY'
+          from hashlib import sha256
+          import json
+          import sys
+          import xml.etree.ElementTree as ET
+
+          def require(condition, message):
+              if not condition:
+                  sys.exit(message)
+
+          # Missing/malformed XML or missing/noninteger counters fail closed.
+          root = ET.parse(sys.argv[1]).getroot()
+          require(root.tag == "testsuites" and len(root) == 1
+                  and root[0].tag == "testsuite", "Expected one flat pytest suite")
+          suite = root[0]
+          require(len(list(root.iter("testsuite"))) == 1, "Nested suites are forbidden")
+          counts = {key: int(suite.attrib[key])
+                    for key in ("tests", "failures", "errors", "skipped")}
+          require(counts == {"tests": 101, "failures": 0, "errors": 0, "skipped": 0},
+                  f"D2 suite count/outcome mismatch: {counts}")
+          cases = list(root.iter("testcase"))
+          require(len(cases) == 101 and len(suite.findall("testcase")) == 101,
+                  "D2 requires 101 direct testcase records")
+          require(all(child.tag == "testcase" for child in suite), "Unexpected suite element")
+          identities = [(case.get("classname"), case.get("name")) for case in cases]
+          modules = {"tests.test_evaluation_fake_provider", "tests.test_evaluation_execution"}
+          require(all(cls in modules and name for cls, name in identities),
+                  "Unexpected D2 testcase module or empty name")
+          require(len(set(identities)) == 101, "Duplicate testcase identity")
+          outcomes = {key: len(list(root.iter(key)))
+                      for key in ("failure", "error", "skipped")}
+          require(outcomes == {"failure": 0, "error": 0, "skipped": 0},
+                  f"D2 testcase outcome mismatch: {outcomes}")
+          require(all(child.tag in {"properties", "system-out", "system-err"}
+                      for case in cases for child in case), "Unexpected testcase result element")
+          require(all(case.get("status") in (None, "run") for case in cases),
+                  "Unexpected testcase status")
+
+          # Frozen full identity set also detects balanced rename/replace/omission.
+          identity_bytes = json.dumps(sorted(identities), separators=(",", ":"),
+                                      ensure_ascii=True).encode("ascii")
+          identity_hash = sha256(identity_bytes).hexdigest()
+          require(identity_hash == "043f6dc73a4f66eb7680f053fa3999ed9bbe64c556e746264fb5f2537a73d4c5",
+                  f"D2 accepted identity set mismatch: {identity_hash}")
+          critical = {
+              ("tests.test_evaluation_fake_provider", "test_fixtures_complete_immutable_and_deterministic[nominal]"),
+              ("tests.test_evaluation_execution", "test_complete_run_and_exact_byte_roundtrip"),
+              ("tests.test_evaluation_execution", "test_mixed_missing_empty_and_malformed_outputs"),
+              ("tests.test_evaluation_execution", "test_deadline_boundary[False-59999-received]"),
+              ("tests.test_evaluation_execution", "test_deadline_boundary[False-60000-timeout]"),
+              ("tests.test_evaluation_execution", "test_deadline_boundary[False-60001-timeout]"),
+              ("tests.test_evaluation_execution", "test_invalid_provider_returns_are_unresolved_contract_errors[None]"),
+              ("tests.test_evaluation_execution", "test_capture_registration_failure_preserves_commits[False]"),
+              ("tests.test_evaluation_execution", "test_cancellation_partial_reporting[during]"),
+              ("tests.test_evaluation_execution", "test_timeout_and_correlation_provenance[timeout_raised-0-timeout-simulated_provider_timeout]"),
+              ("tests.test_evaluation_execution", "test_timeout_and_correlation_provenance[checkpoint-60000-timeout-observed_deadline_expiry]"),
+              ("tests.test_evaluation_execution", "test_timeout_and_correlation_provenance[response_returned-60000-timeout-observed_deadline_expiry]"),
+              ("tests.test_evaluation_execution", "test_timeout_and_correlation_provenance[transport_error_raised-0-transport_error-None]"),
+              ("tests.test_evaluation_execution", "test_timeout_and_correlation_provenance[transport_error_raised-60000-timeout-observed_deadline_expiry]"),
+              ("tests.test_evaluation_execution", "test_timeout_and_correlation_provenance[response_returned-0-received-None]"),
+          }
+          require(critical <= set(identities), "Critical D2 execution coverage missing")
+          for cls, name in sorted(critical):
+              print(f"PASS {cls}::{name}")
+          print(f"RG-07D-D2 collected=101 passed=101 counts={counts}")
+          print(f"Accepted identity SHA-256: {identity_hash}")
+          print("Mechanical fake execution only; no semantic quality verdict")
+          PY
```

The evidence document is new/untracked and absent from ordinary tracked Git
diff. A complete two-path patch, including this document, is retained outside
the repository for independent review. Git's LF-to-CRLF advisory did not change
the protected byte prefix or any unrelated source bytes.

## Limitations / operations NOT RUN

- Hosted GitHub Actions, Ubuntu 24.04 execution and CI bootstrap: NOT RUN.
  No hosted CI success is claimed.
- actionlint / full Actions schema validator: NOT RUN; unavailable locally.
- Fresh venv creation/hash-locked sync: NOT RUN locally; matching existing
  isolated locked-version venv reused; CI explicitly creates/syncs its own.
- Existing evaluator/D1 suites: NOT RUN for this task; original gates/jobs remain
  byte-for-byte unchanged. Local execution was limited to the two D2 suites.
- Application/UI/API/DB, Docker, external AI and paid calls: NOT RUN.
- Semantic evaluation, snapshots/seals/annotations/scores: NOT RUN.
- Commit, push, PR, fetch/pull, remote Git operations, Actions dispatch/rerun/
  cancellation, reset/rebase/destructive cleanup: NOT RUN.
- No source/test/dependency or RG-06D workflow change; no staging.

No observed blocker requires relaxing constraints. Next step: independent
review of the two-path change and its strict gate; publication and hosted CI
remain separate decisions.

RG-07D-D2-CI READY FOR INDEPENDENT REVIEW
