# RG-07C — Offline Evaluator CI Integration

Date: 2026-10-24 (Europe/Berlin).

**LOCAL VALIDATION PASS**

**GITHUB ACTIONS NOT YET EXECUTED**

**RG-07C READY FOR INDEPENDENT REVIEW**

## Repository and exact changed paths

Repository: `Yeromenko-Kateryna/reqguard-quality-platform`.
Working directory: `C:\Users\katal\OneDrive\Рабочий стол\projects\reqguard-quality-platform`.
Branch: `main`. Starting/final HEAD: `8c82fd6d26d0dea322beed180215871eef052be6`.

Only these two repository files were added; neither is staged:

- `.github/workflows/rg07c-evaluator.yml`
- `docs/ai-quality/RG-07C_IMPLEMENTATION_EVIDENCE.md`

RG-06D, RG-07A, accepted evaluator source/tests, `pyproject.toml` and `uv.lock`
remain unchanged. Pre-existing tracked/untracked work was preserved.

## Workflow and dependency decisions

Workflow `RG-07C Offline Evaluator`, job `evaluator`, display name
`Offline evaluator (297 tests, Unicode 15.1.0)`:

- `push` to `main`; `pull_request` targeting `main`; no path filters or dispatch.
- `permissions: contents: read`; checkout credentials are not persisted.
- `ubuntu-24.04`, 10-minute timeout, explicit Bash shell.
- Same full checkout/setup-uv action SHAs as RG-06D; uv `0.11.22`, cache disabled.
- Exact Python `3.13.1`; a separate temporary venv, with no product installation.
- Before tests, prints Python/Unicode versions and exits nonzero unless Python
  is exactly 3.13.1 and `unicodedata.unidata_version == "15.1.0"`.
- Exports only the existing dev group's pytest dependency tree, pruning httpx:
  `uv export --frozen --only-group dev --prune httpx --no-emit-project --no-header`.
  Installs via `uv pip sync --require-hashes --only-binary :all:` and lists packages.
  All versions/hashes come from existing `uv.lock`; no new dependency resolution.

The product declares Python `>=3.12,<3.13`; its lock declares `==3.12.*`.
Python 3.12 supplies Unicode 15.0.0. Frozen export deliberately reads the accepted
lock without resolving/installing the product under 3.13. The exported pytest
packages are compatible with 3.13, verified by installation and execution locally.
This does not establish Python 3.13 compatibility for the product.

Installed locally: pytest 9.1.1, iniconfig 2.3.0, packaging 26.3, pluggy 1.6.0,
pygments 2.21.0 and Windows-only colorama 0.4.6. Linux omits colorama via its marker.
No FastAPI, httpx, provider or database dependencies are installed in this venv.

Pytest receives all three explicit paths, verbose reporting, strict config/markers,
no inherited addopts, and disabled third-party plugin autoload. No selection filters,
skip rewriting, `continue-on-error` or error suppression are present. The JUnit gate
requires exactly 297 tests and zero failures/errors/skips; absent/malformed XML also
fails. Default success-only step execution and Bash fail-fast propagate failures.
Verbose test output and the final count dictionary are retained in Actions logs.
JUnit is temporary; no artifact upload or durable JUnit publication is configured.

## Local commands and results

PowerShell abbreviations used below (all files are outside the repository):

```powershell
$T = 'C:\Users\katal\AppData\Local\Temp\reqguard-rg07c-validation'
$P = "$T\managed-venv\Scripts\python.exe"
$V = 'C:\Users\katal\.codex\visualizations\2026\10\24\01a16f89-f0f9-7ed2-9860-fde40d43e761'
$N = 'C:\Users\katal\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
```

Successful setup commands, each exit **0**:

```powershell
uv python install 3.13.1 --install-dir "$T\managed-python" --no-bin --no-registry
uv venv --no-project --python "$T\managed-python\cpython-3.13.1-windows-x86_64-none\python.exe" "$T\managed-venv"
uv export --frozen --only-group dev --prune httpx --no-emit-project --no-header --offline --output-file "$T\requirements.txt"
uv pip sync --python $P --require-hashes --only-binary :all: --offline "$T\requirements.txt"
```

The frozen offline export was performed before creating the managed venv; the
requirements file was reused unchanged. Dependencies came from the uv cache;
only the isolated Python runtime required a download. No PATH/registry edits.

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTEST_ADDOPTS = ''
& $P -c "import sys,unicodedata;print(sys.version);print(unicodedata.unidata_version);sys.exit(0 if sys.version_info[:3] == (3,13,1) and unicodedata.unidata_version == '15.1.0' else 1)"
& $P -m pytest -v -ra --strict-config --strict-markers -o addopts= -p no:cacheprovider --junitxml="$T\pytest.xml" tests/test_evaluation_dataset.py tests/test_evaluation_hard_fail.py tests/test_evaluation_metrics.py
```

Both commands exit **0**. Runtime: CPython 3.13.1 (uv-managed Windows x86_64),
Unicode **15.1.0**. Pytest: **collected 297; 297 passed in 2.29s**.
Failed **0**, errors **0**, skipped **0**, deselected **0**, xfail/xpass **0**.
JUnit execution counts: dataset **59**, hard_fail **118**, metrics **120**.

```powershell
& $N "$V\validate-rg07c.cjs"
& $P "$V\validate-rg07c.py"
```

Both one-off validation harnesses exit **0**; harnesses and synthetic probes were
written outside the repository. JavaScript uses the already installed
Playwright-core bundled YAML parser only (no browser execution or new packages).
It parses YAML 1.2 with unique keys and checks triggers, permissions, job/runtime,
action SHAs, credentials, all three paths and absence of failure suppression.
Python reads the parsed run blocks, checks each with `bash -n`, and executes the
exact embedded Unicode/JUnit Python code, including controlled negative probes:

| Check | Actual exit | Expected |
|---|---:|---:|
| YAML parsing and workflow structure | 0 | 0 |
| Five Bash run blocks, syntax only | 0 each | 0 |
| Bash setup failure stops execution | 1 | 1 |
| Exact Unicode gate, real runtime | 0 | 0 |
| Unicode gate with probe-only 15.0.0 value | 1 | 1 |
| Exact JUnit gate, actual 297-test report | 0 | 0 |
| Bare managed runtime missing pytest | 1 | 1 |
| Synthetic failing assertion | 1 | 1 |
| Synthetic missing dependency during fixture setup | 1 | 1 |
| Synthetic missing dependency during collection | 2 | 2 |
| JUnit wrong count / skip / failure / error probes | 1 each | 1 |

No accepted source/test files were changed for these probes.

Initial attempts: sandbox uv operations could not persist interpreter-cache files
(access denied); approved local retries succeeded. The system Python 3.13.1 was
incomplete (`html/entities.py` absent): pytest exited **1**, both inside/outside
sandbox, before collection. It was replaced for validation by the isolated managed
runtime, without repairing/changing the system installation. Git Bash syntax checks
initially exited **3221225794** in sandbox (NtCreateDirectoryObject access denied);
the approved local retry passed. Preliminary yaml-module availability probes found
no standalone parser; the existing bundled parser above required no installation.

## Git checks and preserved state

`git diff --check`: exit **0**. Tracked `git diff --stat` is empty because both
task additions are untracked. `git diff --exit-code HEAD -- .github/workflows/rg06d-e2e.yml reqguard tests docs/ai-quality/RG-07A_EVALUATION_SPEC_v1.md pyproject.toml uv.lock`:
exit **0**, no output. HEAD and branch are unchanged.

New-file `git diff --no-index --stat -- NUL <path>`: exit **1** per file (expected
new-file difference). Whitespace checks with `--check`: exit **1** per file
(new-file difference); no whitespace diagnostics, only LF-to-CRLF notices.

```text
.github/workflows/rg07c-evaluator.yml                    | 75 +
docs/ai-quality/RG-07C_IMPLEMENTATION_EVIDENCE.md          | 203 +
2 files added; no tracked files modified
```

Final `git status --short`:

```text
?? .github/workflows/rg07c-evaluator.yml
?? "ChatGPT file/"
?? RG-04_EVIDENCE_COMPLETION.md
?? RG-04_IMPLEMENTATION_EVIDENCE.md
?? docs/ai-quality/RG-07C_IMPLEMENTATION_EVIDENCE.md
?? quality/api/EVIDENCE.md
?? quality/api/PF05_FIX_EVIDENCE.md
?? quality/api/README.md
?? quality/api/compose.rg05.yaml
?? quality/api/decisions.config.ts
?? quality/api/decisions/
?? quality/api/fixtures/
?? quality/api/helpers/
?? quality/api/orchestrator.ts
?? quality/api/package-lock.json
?? quality/api/package.json
?? quality/api/playwright.config.ts
?? quality/api/provenance.py
?? quality/api/scripts/diagnose-rg05-cloud7-metadata.ps1
?? quality/api/scripts/prepare-rg05-l1-workspace.ps1
?? quality/api/scripts/rg05-v2-api-shim.py
?? quality/api/scripts/rg05-v2.ts
?? quality/api/specs/
?? quality/api/tsconfig.json
```

Official references consulted: [Python 3.13 Unicode database](https://docs.python.org/3.13/library/unicodedata.html),
[uv command reference](https://docs.astral.sh/uv/reference/cli/),
[GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).

## Limitations and operations NOT RUN

**GITHUB ACTIONS NOT YET EXECUTED**: Windows local execution does not prove a
successful Ubuntu runner job, remote action download, or Linux package download.
Structural/YAML/Bash checks are local checks, not GitHub's server-side validation
or actionlint. Frozen export trusts the accepted lock; it does not re-resolve it.
GitHub-hosted runtime/dependency downloads still require public network access.

The 297 accepted tests are deterministic offline conformance fixtures. Their
limited normalization doubles remain unchanged; a real Unicode version gate
does not turn these fixtures into comprehensive Unicode or live-model evidence.
No semantic criteria/thresholds or annotation collection were introduced.

NOT RUN: GitHub Actions execution/dispatch, commit, staging, push, PR, publication,
remote mutation, paid AI/model/API calls, live-model evaluation, human annotation,
Docker, PostgreSQL, FastAPI/provider/UI/browser tests, RG-06D execution, and unrelated
test suites. These are outside RG-07C local scope or explicitly prohibited.

Next step: independent review of the two additions and local evidence; any later
commit/publication/remote CI execution requires a separate user instruction.
