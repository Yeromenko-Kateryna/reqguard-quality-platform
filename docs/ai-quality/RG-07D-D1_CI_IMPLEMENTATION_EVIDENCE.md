# RG-07D-D1-CI — Evidence Package CI Integration

Date: 2026-10-25 (Europe/Berlin).
Mode: LOCAL IMPLEMENTATION + VALIDATION / NO COMMIT / NO PUSH.

**RG-07D-D1-CI READY FOR INDEPENDENT REVIEW**

Implementation and available local checks are complete. This is readiness for
review, not a claim of Linux test execution or GitHub Actions success. Fresh
Windows results: D1 **173 collected, 170 passed, 3 skipped, 0 failures/errors**;
accepted evaluator regression **297 passed, 0 failures/errors/skips**. The strict
Linux gate remains **173 collected / 171 passed / 2 NTFS skips**. It rejects the
actual Windows report. Fresh Linux execution and actionlint/schema validation
are NOT RUN for the reasons below; the supplied prior independent Linux result
was not reproduced here and is not presented as fresh evidence.

## Repository, scope and preservation

Directory: `C:\Users\katal\OneDrive\Рабочий стол\projects\reqguard-quality-platform`.
Branch: `main`. Starting/final HEAD:
`a3465cfb5cebe91e313cf6c1a7c748e26c6788d9` (matches requested baseline).

Exactly two task paths:

- Modified: `.github/workflows/rg07c-evaluator.yml` (+100 lines).
- New: `docs/ai-quality/RG-07D-D1_CI_IMPLEMENTATION_EVIDENCE.md` (this report).

The entire original workflow is an unchanged byte prefix of the result. Parsed
`evaluator` equality and unchanged top-level configuration were also checked.
Its Python 3.13.1 / Unicode 15.1.0 guard, three original modules and exact
297-test, zero-failure/error/skip gate are retained. No D1 source/tests,
RG-07A/B/C implementation, RG-06D, dataset, rubrics, thresholds, pyproject.toml
or uv.lock changes; no staging, commit, push or remote mutation.

A SHA-256 baseline of all 132 Git-listed tracked/untracked files was saved
outside the repository before implementation. All baseline paths remain;
only the authorized workflow differs in bytes. The 77 pre-existing untracked
files remain unchanged. Final Git status adds the modified workflow and this
new report to that original inventory. `git diff --check`,
`git diff --cached --exit-code`, and
`git diff --exit-code -- pyproject.toml uv.lock` exit 0. The report is untracked
and therefore absent from normal tracked diffstat. Git emits an LF-to-CRLF
advisory; no line-ending repair was applied to unrelated files.

## New job and isolation

Independent job ID `evidence-integrity`, no `needs`, runs on `ubuntu-24.04`;
10-minute timeout; job and workflow repository permissions `contents: read`.
Reuses the existing exact 40-character SHA pins for checkout and setup-uv;
checkout uses `persist-credentials: false`, setup-uv cache is disabled.

Python 3.13.1 is selected explicitly, with a separate venv under RUNNER_TEMP
and a pre-test Python-version/Linux guard. No product installation is attempted
(the product metadata targets Python 3.12). The existing approach is reused:
frozen dev-only export, prune httpx, no project emission; sync requires hashes
and binary distributions. No dependency or lock-file changes. The exported
requirements contain pytest 9.1.1, iniconfig 2.3.0, packaging 26.3, pluggy 1.6.0,
pygments 2.21.0 and Windows-only colorama 0.4.6. Existing local isolated venv
matches these versions. No new local install was needed or performed.

The job's cwd is `$RUNNER_TEMP/rg07d-d1-work`, fixtures use the sibling
`$RUNNER_TEMP/rg07d-d1-pytest-tmp`, JUnit is external, bytecode and pytest cache
writes are disabled, and pytest's absolute `-c` retains repository source
imports. The existing package fixture explicitly rejects fixture directories
inside cwd. Packages are generated in external tmp_path fixtures. No Docker,
database, browser, network model provider or paid service is used. CI bootstrap
still needs GitHub Actions/Python/package downloads; offline refers to test
execution without a model/provider, not an air-gapped first installation.

## Independent JUnit gate

The workflow's final step uses `if: ${{ !cancelled() }}` so validation also runs
after a nonzero pytest result; missing/malformed XML fails closed. It checks:

1. Suite totals exactly tests=173, failures=0, errors=0, skipped=2.
2. Exactly 173 distinct testcase identities, all from test_evaluation_evidence.
3. Testcase-level totals independently equal 171 passed, 2 skipped, no
   failure/error nodes (aggregate attributes alone cannot establish success).
4. Exactly these skipped names, each with type `pytest.skip` and exact reason
   `NTFS junction test; POSIX runs actual symlinks`:
   `test_real_windows_junction_escape[directory]`,
   `test_real_windows_junction_escape[root]`.
5. Exactly one testcase for each `test_real_symlink_escape[file]`,
   `test_real_symlink_escape[directory]`, `test_real_symlink_escape[root]`,
   with no skipped/failure/error node. All three PASS identities are printed.

The actual script extracted from YAML was syntax-checked and exercised against
14 synthetic reports: one conforming report accepted (exit 0), and 13 mutations
rejected (each exit 1): incorrect suite count, incorrect passed count, testcase
failure, testcase error, unexpected skipped identity, wrong skip reason, wrong
skip type, a skipped real symlink with unchanged skip totals, missing real
symlink identity, duplicate testcase, foreign module, missing testcase, and
aggregate failure mismatch. Actual Windows XML is rejected, exit 1, because
its three skips differ from the required Linux outcomes. Synthetic probes
validate gate behavior only; they do not establish Linux symlink execution.

## Commands and fresh results

Reproduction variables (PowerShell; no secret values):

```powershell
$R = 'C:\Users\katal\OneDrive\Рабочий стол\projects\reqguard-quality-platform'
$P = 'C:\Users\katal\AppData\Local\Temp\reqguard-rg07c-validation\managed-venv\Scripts\python.exe'
$S = 'C:\Users\katal\.codex\visualizations\2026\10\24\01a16ff6-e5f2-71c1-ac47-5d114e13969f\rg07d-ci'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTEST_ADDOPTS = ''
```

Tests initially run from `$R`:

```powershell
& $P -m pytest -q -ra --strict-config --strict-markers -o addopts= -p no:cacheprovider --junitxml="$S\d1-windows.xml" tests/test_evaluation_evidence.py
& $P -m pytest -q -ra --strict-config --strict-markers -o addopts= -p no:cacheprovider --junitxml="$S\regression.xml" tests/test_evaluation_dataset.py tests/test_evaluation_hard_fail.py tests/test_evaluation_metrics.py
& $P -c 'import sys,unicodedata; print(sys.version); print(unicodedata.unidata_version); assert sys.version_info[:3]==(3,13,1) and unicodedata.unidata_version=="15.1.0"'
```

External cwd verification, using the same absolute config / sibling fixture
layout as CI (directory creation via `New-Item -ItemType Directory -Force`):

```powershell
Set-Location "$S\work"
& $P -m pytest -q -ra --tb=short --strict-config --strict-markers -c "$R\pyproject.toml" -o addopts= -p no:cacheprovider --basetemp="$S\pytest-sibling" --junitxml="$S\d1-external.xml" "$R\tests\test_evaluation_evidence.py"
Set-Location $R
```

| Fresh check | Actual result | Exit |
|---|---|---|
| D1 first attempt inside sandbox | 16 passed, 157 temporary-directory setup errors; 32.30s | 1 |
| D1 rerun outside sandbox | 170 passed, 3 skipped; 14.49s | 0 |
| Accepted three evaluator modules outside sandbox | 297 passed, no skips/errors/failures; 2.52s | 0 |
| Python/Unicode guard | CPython 3.13.1 / Unicode 15.1.0 | 0 |
| Initial external-cwd local probe | 21 passed, 152 fixture setup errors; 3.95s | 1 |
| Corrected external cwd, sibling basetemp | 170 passed, 3 skipped; 17.18s | 0 |

The first external-cwd probe mistakenly set cwd=`$S` and
`--basetemp="$S\pytest-external"` (JUnit=`$S\d1-external.xml`, otherwise the
same external command without `--tb=short`). The unchanged fixture rejected
basetemp beneath cwd. This was a local command error; the workflow already
uses sibling directories. The corrected probe above passed. Its final XML
replaced the diagnostic XML. No test edits were made.

JUnit XML was parsed independently with ElementTree, confirming the two D1
reports' 173/0/0/3 suite counts and regression's 297/0/0/0. Final external-cwd
classname is `tests.test_evaluation_evidence`, accepted by the module gate.
On both final Windows D1 runs:

| Test identity | Outcome |
|---|---|
| test_real_symlink_escape[file] | SKIP |
| test_real_symlink_escape[directory] | SKIP |
| test_real_symlink_escape[root] | SKIP |
| test_real_windows_junction_escape[directory] | PASS |
| test_real_windows_junction_escape[root] | PASS |

All three local symlink skips have the exact reason:
`Windows token lacks symlink privilege; real junction tests run separately`.
These Windows skips are not allowed by the Linux gate. No fresh claim of
171 Linux passes or three real POSIX symlink passes is made.

Other commands:

```powershell
$env:UV_CACHE_DIR = "$S\uv-cache"
uv export --offline --frozen --only-group dev --prune httpx --no-emit-project --no-header --output-file "$S\requirements.txt"
uv pip list --python $P
python "$S\validate.py"
git diff --check
git diff --cached --exit-code
git diff --exit-code -- pyproject.toml uv.lock
git diff --stat
git diff -- .github/workflows/rg07c-evaluator.yml
git status --short
git status --porcelain=v1 -uall
git branch --show-current
git rev-parse HEAD
```

All above final commands exit 0. `validate.py` and JUnit/probe artifacts live
outside the repository under `$S`; they are local evidence, not dependencies
or files required by CI. Validation loads already-cached PyYAML 6.0.3 from
`C:/Users/katal/AppData/Local/uv/cache/archive-v0/AdtvyMNTOgrPCU3-/Lib/site-packages`
without installing it. It extracts all five new `run` blocks and executes
`C:/Program Files/Git/bin/bash.exe -n <external-step-file>`; all exit 0.
Both Python heredocs pass `ast.parse`. Parsed evaluator/top-level equality,
original workflow byte prefix, two job IDs, SHA pin formats, read-only job
permissions and no dependency/services/container configuration pass.
PyYAML uses YAML 1.1 boolean handling for `on`; this parser check alone is not
a full GitHub Actions schema validator. Byte-prefix and top-level equality
checks ensure the original event triggers remain untouched.

The initial bash check inside sandbox failed with MSYS
`NtCreateDirectoryObject ... 0xC0000022` (validation script exit 1).
Rerunning the same shell syntax checks outside sandbox succeeded (exit 0).
System/bundled/project Python imports initially showed PyYAML unavailable;
using the existing cached package resolved parsing without any installation.
`actionlint` was not found by Get-Command or in the inspected runtime paths.
No replacement validator dependency was downloaded.

`wsl --list --quiet` initially failed in sandbox with E_ACCESSDENIED;
outside sandbox it exited 0 and listed only `docker-desktop`.
`wsl -d docker-desktop -- sh -c 'uname -a; command -v python3; command -v uv; command -v bash'`
reported Linux but exited 1: no Python, uv or bash found. No new distro,
container or Linux interpreter was installed.

## Workflow diff

```diff
diff --git a/.github/workflows/rg07c-evaluator.yml b/.github/workflows/rg07c-evaluator.yml
index c66b33f..9f77e0f 100644
--- a/.github/workflows/rg07c-evaluator.yml
+++ b/.github/workflows/rg07c-evaluator.yml
@@ -73,3 +73,103 @@ jobs:
           if counts != {"tests": 297, "failures": 0, "errors": 0, "skipped": 0}:
               sys.exit("RG-07C test count/outcome mismatch")
           PY
+
+  evidence-integrity:
+    name: Offline evidence integrity (173 cases, 171 passed, 2 NTFS skips)
+    runs-on: ubuntu-24.04
+    permissions:
+      contents: read
+    timeout-minutes: 10
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
+      - name: Create isolated Python 3.13.1 evidence environment
+        run: uv venv --no-project --python 3.13.1 "$RUNNER_TEMP/rg07d-d1-venv"
+      - name: Require Python 3.13.1 on Linux
+        run: |
+          "$RUNNER_TEMP/rg07d-d1-venv/bin/python" - <<'PY'
+          import sys
+          print(f"Python: {sys.version}; platform: {sys.platform}")
+          if sys.version_info[:3] != (3, 13, 1) or sys.platform != "linux":
+              sys.exit("RG-07D-D1 requires Python 3.13.1 on Linux")
+          PY
+      - name: Install only hash-locked pytest dependencies
+        run: |
+          set -euo pipefail
+          uv export --frozen --only-group dev --prune httpx --no-emit-project --no-header \
+            --output-file "$RUNNER_TEMP/rg07d-d1-requirements.txt"
+          uv pip sync --python "$RUNNER_TEMP/rg07d-d1-venv/bin/python" --require-hashes --only-binary :all: \
+            "$RUNNER_TEMP/rg07d-d1-requirements.txt"
+          uv pip list --python "$RUNNER_TEMP/rg07d-d1-venv/bin/python"
+          git diff --exit-code -- pyproject.toml uv.lock
+      - name: Run all evidence cases outside the repository (expected 173)
+        run: |
+          set -euo pipefail
+          mkdir -p "$RUNNER_TEMP/rg07d-d1-work"
+          cd "$RUNNER_TEMP/rg07d-d1-work"
+          # Absolute config keeps source imports; cwd, fixtures and reports stay external.
+          "$RUNNER_TEMP/rg07d-d1-venv/bin/python" -m pytest -v -ra --strict-config --strict-markers \
+            -c "$GITHUB_WORKSPACE/pyproject.toml" -o addopts= -p no:cacheprovider \
+            --basetemp="$RUNNER_TEMP/rg07d-d1-pytest-tmp" \
+            --junitxml="$RUNNER_TEMP/rg07d-d1-pytest.xml" \
+            "$GITHUB_WORKSPACE/tests/test_evaluation_evidence.py"
+      - name: Require exact outcomes, NTFS skip identities and real POSIX symlink passes
+        if: ${{ !cancelled() }}
+        run: |
+          "$RUNNER_TEMP/rg07d-d1-venv/bin/python" - "$RUNNER_TEMP/rg07d-d1-pytest.xml" <<'PY'
+          import sys
+          import xml.etree.ElementTree as ET
+
+          def require(condition, message):
+              if not condition:
+                  sys.exit(message)
+
+          root = ET.parse(sys.argv[1]).getroot()
+          suites = list(root.iter("testsuite"))
+          counts = {key: sum(int(s.get(key, "0")) for s in suites)
+                    for key in ("tests", "failures", "errors", "skipped")}
+          require(counts == {"tests": 173, "failures": 0, "errors": 0, "skipped": 2},
+                  f"RG-07D-D1 suite count/outcome mismatch: {counts}")
+          cases = list(root.iter("testcase"))
+          identities = [(case.get("classname"), case.get("name")) for case in cases]
+          require(len(cases) == 173 and len(set(identities)) == 173,
+                  "RG-07D-D1 requires 173 distinct testcase records")
+          # pytest's classname prefix depends on rootdir; bind identity to the module.
+          require(all(cls and cls.split(".")[-1] == "test_evaluation_evidence"
+                      for cls, name in identities), "Unexpected test module")
+          outcomes = {key: sum(len(case.findall(key)) for case in cases)
+                      for key in ("failure", "error", "skipped")}
+          passed = sum(not any(case.find(key) is not None
+                               for key in ("failure", "error", "skipped")) for case in cases)
+          require(outcomes == {"failure": 0, "error": 0, "skipped": 2} and passed == 171,
+                  f"RG-07D-D1 testcase outcome mismatch: {outcomes}, passed={passed}")
+          skipped = {case.get("name"): case.find("skipped") for case in cases
+                     if case.find("skipped") is not None}
+          expected_skips = {f"test_real_windows_junction_escape[{kind}]"
+                            for kind in ("directory", "root")}
+          require(set(skipped) == expected_skips, f"Unexpected skips: {set(skipped)}")
+          reason = "NTFS junction test; POSIX runs actual symlinks"
+          require(all(node.get("type") == "pytest.skip" and node.get("message") == reason
+                      for node in skipped.values()), "Unexpected platform skip reason/type")
+          symlinks = {f"test_real_symlink_escape[{kind}]" for kind in ("file", "directory", "root")}
+          for name in sorted(symlinks):
+              matches = [case for case in cases if case.get("name") == name]
+              require(len(matches) == 1 and not any(matches[0].find(key) is not None
+                      for key in ("failure", "error", "skipped")), f"Real POSIX symlink did not pass: {name}")
+              print(f"PASS {name}")
+          print(f"RG-07D-D1 collected=173 passed={passed} counts={counts}")
+          print(f"Platform skips: {sorted(skipped)}; reason: {reason}")
+          PY
```

## Limitations and operations NOT RUN

- Fresh Ubuntu/Linux D1 execution: NOT RUN; no suitable local Linux Python
  environment. The 171/2 Linux gate and POSIX symlink coverage still require
  independent execution. Expected counts were not changed to fit Windows.
- Full GitHub Actions schema validation/actionlint: NOT RUN; tool unavailable.
  YAML parsing, shell/Python syntax and targeted structural checks passed.
- Recreating the CI venv and hash-locked install locally: NOT RUN; reused the
  existing isolated Python 3.13.1 venv. Frozen offline export and version
  inspection passed; the installation command is preserved in the workflow.
- Hosted Actions checkout/setup/install/run: NOT RUN. No workflow dispatch,
  rerun, cancellation or other remote test run was triggered.
- Docker containers, databases, browsers, live provider/model execution,
  paid calls, semantic-model evaluation: NOT RUN / not required.
- Commit, push, PR, publication and all remote mutations: NOT RUN / prohibited.

Next step: independent review of this exact diff and execution in an existing
Linux Python 3.13.1 environment, including the unchanged strict JUnit gate.
Any future remote CI operation requires separate explicit authorization.

**RG-07D-D1-CI READY FOR INDEPENDENT REVIEW**
