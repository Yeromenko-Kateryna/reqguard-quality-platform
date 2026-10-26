# ReqGuard Quality Platform

**Portfolio v1.0 — QA Automation / SDET: browser → API → PostgreSQL → CI.**

ReqGuard demonstrates verification across system boundaries: submit a requirement
in a browser, receive an authored analysis, and trace the response to a committed
database row by `run_id`. The product uses a **deterministic fake provider** with
no live model calls. The separate offline AI Quality component verifies evaluation
mechanics; its passing tests do **not** prove live-model semantic quality.

This guide describes accepted baseline
[`3b04823484222c1063d3f58f428535198c8be10e`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/commit/3b04823484222c1063d3f58f428535198c8be10e)
(RG-STATE-01 / 2026-10-27 task baseline).
“Portfolio v1.0” labels the portfolio scope; application/package metadata remains
`0.1.0`. **Portfolio V1.0 is not yet declared released.** Runtime inputs below
are tracked in that baseline. This RG-README-02 correction is a local review draft;
the published README at the baseline is an earlier revision.

## Architecture and published behavior

```text
Browser: HTML / CSS / JavaScript modules
  │ same-origin POST /analyses {requirement_text}
  ▼
FastAPI / Pydantic (Python 3.12)
  │ validate → authored fake result → parameterized INSERT + acknowledged COMMIT
  ▼
PostgreSQL 17.11: public.analyses
  └─ run_id, provider, status, original_input, analysis_payload JSONB, created_at

GitHub Actions verifies the path:
  Chromium / Playwright (TypeScript) → real FastAPI → independent pg SQL connection

Separate offline path (Python 3.13.1):
  synthetic dataset → hard-fail rules / metrics / evidence integrity / fake execution
```

| Boundary | Implementation and contract |
| --- | --- |
| UI | [Local page](reqguard/static/index.html), [request/rendering logic](reqguard/static/app.mjs). No frontend build or CDN; JavaScript required. Loading disables duplicate submission; API text uses text nodes. |
| API | [Routes and fixture](reqguard/main.py): `GET /`, static assets, `POST /analyses`; [OpenAPI](http://127.0.0.1:8000/openapi.json) when running. Strict string, 1–2000 characters, with non-whitespace content; original input is preserved. Invalid requests return 422 before provider/persistence. |
| Persistence | [Repository](reqguard/persistence.py), [schema](db/001_init.sql). HTTP 200 follows acknowledged COMMIT; each result has a new UUID. `created_at` is the database transaction-start timestamp. |
| Failures | Missing `DATABASE_URL` or connection/INSERT/COMMIT failure returns 503 with `Persistence unavailable`; no automatic retry. An uncertain COMMIT acknowledgement or network failure can leave a row despite no success response. Unexpected application errors retain HTTP 500 semantics. |

Only the exact text `The user can quickly reset their password` returns
`provider: fake`, `status: completed` and analysis identifying `quickly`, missing
measurable duration criteria, and a candidate password-reset test. Other valid
text returns `unsupported_fixture` and `analysis: null`. Both outcomes persist;
unsupported payloads use **SQL NULL**, not JSON literal `null`. Constraints enforce
status/payload consistency. A candidate test is authored output, not an executed
password-reset test.

## Reproduce the browser-to-database demo

Commands use **Windows PowerShell 5.1 or PowerShell 7**, on Windows x64, from the
repository root unless stated otherwise. Prerequisites: Git, uv, CPython 3.12,
Docker Desktop with a running local Linux engine and Compose, and a
JavaScript-enabled browser. Node is needed only for frontend tests or Playwright.
The Windows browser launcher enforces CPython 3.12 x64, Node **24.15.0**, npm
**11.12.1**, Compose **2.x or exactly 5.5.1**, and a local named-pipe Docker
context. It does not pin a Python patch, Git, uv or Docker Desktop version.
CI pins Python 3.12.10 and uv 0.11.22; those are CI references, not extra Windows
launcher gates. Offline evaluation requires separate Python **3.13.1**.
Setup can download locked packages and the PostgreSQL image. Credentials below
are synthetic local demo credentials.

**RG-README-02 execution status:** static source/command review only. Fresh Windows
setup, Docker/schema initialization, browser/HTTP/SQL verification, product tests,
smoke, E2E, shutdown and offline setup/execution were **NOT RUN in this task**.
Historical local tests, hosted Linux CI and accepted Codespace manual evidence
below do not establish execution of this corrected Windows procedure.

### 0. Use a new checkout and verify the reviewed guide

**Pre-publication review procedure:** the clone-and-replace README workflow below
requires the separately supplied reviewed README artifact and hash. It is not a
standalone public reproduction procedure. It cannot be presented as standalone
public reproduction until the corrected README is committed and published.

Do not run fresh-user setup in the protected dirty working tree. Use a new
PowerShell session, trusted tools on PATH, and an absent destination under a
trusted user-private parent. Execute each block as a unit. Any exception means
STOP: do not paste subsequent blocks. Windows PowerShell does not turn every
native failure into a terminating error with `$ErrorActionPreference` alone.
The immediate `$LASTEXITCODE` checks below provide fail-stop behavior
([Microsoft reference](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_automatic_variables?view=powershell-5.1#lastexitcode)).

```powershell
$ErrorActionPreference = 'Stop'
function Assert-Native {
    if ($LASTEXITCODE -ne 0) { throw "Native command failed (exit $LASTEXITCODE); STOP" }
}
$port01Target = Read-Host 'Absolute NEW checkout directory (must not exist)'
if (-not [IO.Path]::IsPathRooted($port01Target) -or (Test-Path -LiteralPath $port01Target)) {
    throw 'An absolute absent destination is required'
}
git clone --branch main --single-branch https://github.com/Yeromenko-Kateryna/reqguard-quality-platform.git $port01Target
Assert-Native
Set-Location -LiteralPath $port01Target
$port01Repo = (Get-Location).Path
$port01Head = git rev-parse HEAD
Assert-Native
if ($port01Head -ne '3b04823484222c1063d3f58f428535198c8be10e') {
    throw 'Remote main differs from reviewed baseline; obtain a reviewed procedure for that revision'
}
$port01InitialStatus = @(git status --porcelain=v1 -uall)
Assert-Native
if ($port01InitialStatus.Count) { throw 'New checkout is not clean' }
Get-FileHash -LiteralPath README.md -Algorithm SHA256
```

Before setup, obtain the **RG-00-reviewed RG-README-02 README artifact and its
SHA-256 from the review handoff**, place that README in this new checkout, then
compare below. The published baseline README is an earlier guide. There is no
self-referential expected hash here. Until that handoff exists, stop before setup;
recording a hash alone is not verification. Do not copy other protected/untracked
files from the original working tree.

```powershell
$port01ExpectedReadme = Read-Host 'Reviewed RG-README-02 README SHA-256 from handoff'
if ($port01ExpectedReadme -notmatch '^[a-fA-F0-9]{64}$' -or
    (Get-FileHash -LiteralPath README.md -Algorithm SHA256).Hash -ne $port01ExpectedReadme) {
    throw 'Reviewed README hash mismatch'
}
$port01OtherChanges = @(git status --porcelain=v1 -uall -- . ':!README.md')
Assert-Native
if ($port01OtherChanges.Count) { throw 'Unexpected checkout changes' }
```

### 1. Preflight environment/resources, then install the product

The root [Compose file](compose.yaml) retains historical names: project
`reqguard_rg04_v11`, volume `reqguard_rg04_v11_pgdata_20261008`, host port 55432.
It does not create a random isolated database. Admit only an initially absent
project/network/volume. A matching name or label does not prove ownership or make
data disposable. On collision or inspection failure STOP without adoption, restart,
schema writes or deletion; ownership resolution is separate. Do not run concurrent
creators against these fixed names. Explicit project/file/context arguments follow
[Docker's project-name precedence](https://docs.docker.com/compose/how-tos/project-name/).
The smoke uses bare Compose internally, so it also needs the same repository root,
selected context and no ambient Compose overrides.

```powershell
$port01Overrides = @(Get-ChildItem Env: | Where-Object {
    $_.Name -match '^(COMPOSE_|DOCKER_|PG|PYTHON|PYTEST_|UV_|NODE_|NPM_CONFIG_|PW_TEST_|RG06)' -or
    $_.Name -in @('DATABASE_URL', 'VIRTUAL_ENV') -or
    ($_.Name -like 'PLAYWRIGHT_*' -and $_.Name -ne 'PLAYWRIGHT_BROWSERS_PATH')
} | Select-Object -ExpandProperty Name)
if ($port01Overrides.Count) {
    throw ('Review unexpected environment variable NAMES only: ' + ($port01Overrides -join ', '))
}
foreach ($port01File in @('.env', 'compose.override.yaml', 'compose.override.yml',
    'docker-compose.override.yaml', 'docker-compose.override.yml', '.npmrc', 'quality/browser/.npmrc')) {
    if (Test-Path -LiteralPath $port01File) { throw "Unexpected local configuration: $port01File" }
}
# Review uv/npm user/global configuration locally; do not print tokens or values.
$port01Context = docker context show
Assert-Native
$port01Endpoint = docker context inspect $port01Context --format '{{.Endpoints.docker.Host}}'
Assert-Native
if ($port01Endpoint -notlike 'npipe://*') { throw 'Local named-pipe Docker context required' }
Write-Output "Selected Docker context: $port01Context"
if ((Read-Host 'Type selected context name to confirm intended local engine') -cne $port01Context) {
    throw 'Context unconfirmed'
}
$env:DOCKER_CONTEXT = $port01Context
$port01Engine = docker --context $port01Context info --format '{{.OSType}}'
Assert-Native
if ($port01Engine -ne 'linux') { throw 'Linux engine required' }
docker --context $port01Context version
Assert-Native
$port01ComposeVersion = docker --context $port01Context compose version --short
Assert-Native
$port01ComposeVersion = $port01ComposeVersion.TrimStart('v')
if (-not ($port01ComposeVersion.StartsWith('2.') -or $port01ComposeVersion -eq '5.5.1')) {
    throw 'Compose 2.x or exactly 5.5.1 required for Windows browser launcher'
}
$port01Project = 'reqguard_rg04_v11'
$port01Volume = 'reqguard_rg04_v11_pgdata_20261008'
$port01Compose = @('--context', $port01Context, 'compose', '--project-directory', $port01Repo,
    '-f', (Join-Path $port01Repo 'compose.yaml'), '-p', $port01Project)
$port01ConfigJson = docker @port01Compose config --format json
Assert-Native
$port01Config = $port01ConfigJson | ConvertFrom-Json
if ($port01Config.name -ne $port01Project -or
    $port01Config.volumes.rg04_pgdata.name -ne $port01Volume -or
    $port01Config.services.db.image -ne 'postgres:17.11-bookworm') { throw 'Compose identity mismatch' }
$port01Containers = @(docker --context $port01Context ps -a --format '{{.ID}}|{{.Names}}|{{.Labels}}|{{.Ports}}')
Assert-Native
$port01Networks = @(docker --context $port01Context network ls --format '{{.ID}}|{{.Name}}|{{.Labels}}')
Assert-Native
$port01Volumes = @(docker --context $port01Context volume ls --format '{{.Name}}|{{.Labels}}')
Assert-Native
$port01Conflicts = @($port01Containers + $port01Networks + $port01Volumes | Where-Object {
    $_ -match 'reqguard_rg04_v11|55432|8000'
})
if ($port01Conflicts.Count) {
    $port01Conflicts | Write-Output
    throw 'Existing potentially conflicting Docker resources; ownership review required'
}
foreach ($port01Port in @(55432, 8000)) {
    $port01Probe = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Any, $port01Port)
    $port01Probe.Server.ExclusiveAddressUse = $true
    try { $port01Probe.Start() } finally { $port01Probe.Stop() }
}
docker @port01Compose config -q
Assert-Native

$port01Venv = Join-Path $env:TEMP ('reqguard-port01-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $port01Venv) { throw 'Environment already exists' }
$env:UV_PROJECT_ENVIRONMENT = $port01Venv
uv lock --check
Assert-Native
uv sync --locked --python 3.12
Assert-Native
uv run --locked --no-sync python -c "import sys, struct, tomllib, importlib.metadata as m; assert sys.platform == 'win32' and sys.implementation.name == 'cpython' and sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8; lock=tomllib.load(open('uv.lock','rb')); pins={p['name']:p['version'] for p in lock['package']}; names=('fastapi','uvicorn','psycopg','psycopg-binary','pytest','httpx'); assert all(m.version(n)==pins[n] for n in names); print(sys.version); print({n:m.version(n) for n in names})"
Assert-Native
```

This conservative reproduction gate is not a claim that every rejected variable
is a launcher security gate. Do not silently unset unknown overrides. Review them
without exposing values, then start a clean session. Review trusted executable
paths and uv/npm user/global configuration locally; stop on unexplained package
sources or execution settings. Port checks are point-in-time probes, not reservations.
Repeat the resource/port checks immediately before startup after installation.
A race, failed or uncertain startup means STOP; never connect to a replacement
service. Keep `UV_PROJECT_ENVIRONMENT` set for product commands; no existing
project `.venv` is needed. Record its absolute path privately.

### 2. Start new PostgreSQL, initialize schema, start FastAPI

```powershell
docker @port01Compose up --wait --wait-timeout 90 db
Assert-Native
$port01DbId = docker @port01Compose ps -q db
Assert-Native
if (-not $port01DbId -or @($port01DbId).Count -ne 1) { throw 'Expected one new DB container' }
$port01DbLabelsJson = docker --context $port01Context inspect --format '{{json .Config.Labels}}' $port01DbId
Assert-Native
$port01DbLabels = $port01DbLabelsJson | ConvertFrom-Json
if ($port01DbLabels.'com.docker.compose.project' -ne $port01Project -or
    $port01DbLabels.'com.docker.compose.service' -ne 'db') { throw 'Resource identity mismatch' }
docker --context $port01Context inspect --format '{{json .Mounts}} {{json .NetworkSettings.Ports}} {{json .NetworkSettings.Networks}}' $port01DbId
Assert-Native
docker --context $port01Context volume inspect --format '{{.Name}} {{.CreatedAt}} {{json .Labels}}' $port01Volume
Assert-Native
docker --context $port01Context network inspect --format '{{.Id}} {{json .Labels}} {{json .Containers}}' reqguard_rg04_v11_default
Assert-Native
# Before writes, require exactly the recorded NEW container/volume/network, correct
# project/service labels, port 127.0.0.1:55432 -> 5432, and no other network members.
# Mounts must be this new volume at /var/lib/postgresql/data and the exact checkout
# db/001_init.sql at /schema/001_init.sql, read-only. No extra mounts are admitted.
# Volume labels: org.reqguard.scope=rg04-v1.1-local-test and
# org.reqguard.owner=reqguard-quality-platform. Save IDs/creation receipts privately.
if ((Read-Host 'Type OWNED after checking all resource fields above') -cne 'OWNED') { throw 'Ownership unconfirmed' }
docker @port01Compose exec -T db pg_isready -U reqguard -d reqguard
Assert-Native
docker @port01Compose exec -T db psql -X -v ON_ERROR_STOP=1 -U reqguard -d reqguard -c "SELECT current_database(), current_user, current_setting('server_version'), to_regclass('public.analyses');"
Assert-Native
# Require reqguard / reqguard / 17.11 and NULL table identity before schema writes.
if ((Read-Host 'Type NEW DB after verifying the four identity fields') -cne 'NEW DB') { throw 'DB identity unconfirmed' }
docker @port01Compose exec -T db psql -X -v ON_ERROR_STOP=1 -U reqguard -d reqguard -f /schema/001_init.sql
Assert-Native
docker @port01Compose exec -T db psql -X -v ON_ERROR_STOP=1 -U reqguard -d reqguard -c "SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_schema='public' AND table_name='analyses' ORDER BY ordinal_position; SELECT count(*) FROM public.analyses;"
Assert-Native
# Require all six columns to match db/001_init.sql (JSONB, TIMESTAMPTZ), count = 0.
if ((Read-Host 'Type SCHEMA after checking columns and empty table') -cne 'SCHEMA') { throw 'Schema unconfirmed' }
$env:DATABASE_URL = 'postgresql://reqguard:local_only_reqguard@127.0.0.1:55432/reqguard'
uv run --locked uvicorn reqguard.main:app --host 127.0.0.1 --port 8000
Assert-Native
```

Expected: healthy database, correct database/role/version/schema, Uvicorn listening
on loopback port 8000. The schema is mounted read-only; application is **manual**,
not an initialization hook. `CREATE TABLE IF NOT EXISTS` does not migrate/repair
schema drift. A failed/uncertain startup retains resources for ownership review.

### 3. Submit once and correlate UI, HTTP and read-only SQL

1. Open [the product page](http://127.0.0.1:8000/) and browser DevTools → Network.
2. Keep the exact fixture `The user can quickly reset their password`. Click
   **Submit requirement** once.
3. Expect one `POST /analyses`, HTTP **200**, UUID `run_id`, `fake`, `completed`,
   ambiguity `quickly`, duration criteria and a candidate test. Save actual request
   and complete response JSON privately. Compare response analysis with the UI.
4. In a second PowerShell terminal at the new repository root, query the **same**
   returned UUID below with an independent database connection.

In the second terminal recreate `$ErrorActionPreference = 'Stop'`, `Assert-Native`,
`$port01Repo` (absolute new checkout path), `$port01Context` (recorded context),
`$port01Project = 'reqguard_rg04_v11'` and `$port01Compose` exactly as in step 1.
Run `Set-Location -LiteralPath $port01Repo`. Verify
`docker @port01Compose ps -q db` plus `Assert-Native` returns the recorded
`$port01DbId` before querying. Shell variables/functions do not cross sessions.
Later product commands also need `$env:UV_PROJECT_ENVIRONMENT` set to the recorded
`$port01Venv`, `$env:DOCKER_CONTEXT = $port01Context` and the synthetic
`$env:DATABASE_URL` from step 2. Recheck unexpected overrides in each new session
before setting these known values. Do not create another environment or database.

```powershell
$port01RunId = ([guid](Read-Host 'Paste the actual Run ID from the browser response')).ToString()
@'
BEGIN READ ONLY;
SET LOCAL TIME ZONE 'UTC';
SELECT run_id, provider, status, original_input, analysis_payload, created_at,
       analysis_payload IS NULL AS analysis_is_sql_null
FROM public.analyses WHERE run_id = :'run_id'::uuid;
SELECT count(*) AS matching_rows
FROM public.analyses WHERE run_id = :'run_id'::uuid;
COMMIT;
'@ | docker @port01Compose exec -T db psql -X -v ON_ERROR_STOP=1 -v "run_id=$port01RunId" -U reqguard -d reqguard
Assert-Native
```

Expected field-by-field comparison: exactly one row (`matching_rows = 1`);
`run_id`, `provider`, `status` equal the actual HTTP response and displayed UI;
`original_input` equals the exact untrimmed fixture. JSONB `analysis_payload`
must structurally equal HTTP `analysis`: every ambiguity term/explanation,
criterion, scenario title, ordered step and expected result. Ignore JSON object
key order/formatting; do not ignore array order or text. `analysis_is_sql_null = f`.
`created_at` must be non-null TIMESTAMPTZ rendered with UTC offset `+00`;
it is the database transaction-start timestamp. HTTP has no timestamp field,
so there is no response timestamp equality check. Never use a fabricated UUID.

The default manual workflow includes the supported HTTP 200 scenario only.
Whitespace HTTP 422/no-delta verification is covered by the isolated browser
specs (complete before/after snapshots and sentinel) and dated PORT-01-R1 evidence.
Other valid text creates an `unsupported_fixture` row with SQL NULL payload.
**Retain all manually created rows by default**, including uncertain outcomes.
No manual SQL DELETE is part of this workflow. Deletion of previously existing
data requires separate authorization outside this task.

### 4. Keep PostgreSQL available through verification

Proceed to the product checks, then the separately isolated browser E2E below.
Do not stop PostgreSQL before DB-dependent integration/smoke checks finish.
If request/COMMIT outcome is uncertain or UUID is missing, inspect before retrying:
a failure does not prove row absence. Shutdown instructions follow the checks.

## Run the checks

### Product and frontend

Use the product shell/environment from setup. The first two commands need no
running database; integration and smoke require the still-running initialized root Compose database and
`DATABASE_URL`. Node 24.15.0 is the frontend reference runtime.
Use the second product terminal for these checks; the manual Uvicorn may remain
running until shutdown. These tests clean only their generated UUIDs and retain
the manual demo row; record and re-query its UUID after checks.

```powershell
uv run --locked pytest -q tests/test_analyses.py tests/test_persistence_unit.py tests/test_ui.py
Assert-Native
$port01Node = node --version
if ($LASTEXITCODE -ne 0) { throw 'Node version check failed' }
if ($port01Node -ne 'v24.15.0') { throw 'Node reference runtime mismatch' }
node --test tests/ui.test.mjs
Assert-Native
uv run --locked pytest -q tests/test_postgres_integration.py
Assert-Native
uv run --locked python scripts/rg04_network_sql_smoke.py
Assert-Native
```

Integration tests fail on missing `DATABASE_URL` rather than silently skipping.
They use new UUIDs, independent committed reads, metadata/constraint checks,
rollback and targeted cleanup. The smoke starts/stops its own Uvicorn subprocess,
compares real HTTP with external container `psql`, deletes its own UUIDs and retains
Docker resources. Frontend tests use a DOM adapter, not a browser engine.
Avoid an unqualified full pytest run: offline evidence tests require the separate
runtime and external directory layout below.

### Independent Chromium → API → SQL (Windows)

[Two Playwright specs](quality/browser/analyses.spec.ts) exercise a completed fixture
and whitespace rejection against real FastAPI/PostgreSQL. They compare HTTP/UI/SQL,
the full table delta, actual 422 and unchanged SQL snapshots, with a sentinel.

The [launcher](scripts/run_rg06b_e2e.py) requires Windows x64 CPython 3.12, Node
**24.15.0**, npm **11.12.1**, Compose **2.x or exactly 5.5.1**, a local named-pipe
Docker context/Linux engine, and a trusted checkout/private artifacts parent.
It rejects ambient `NODE_*`, `PW_TEST_*`, unexpected `PLAYWRIGHT_*`, Docker remote
overrides and Python project/path overrides. `PLAYWRIGHT_BROWSERS_PATH` is allowed.
The package lock pins Playwright **1.64.0** and pg **8.23.1**. Provision first:

```powershell
uv sync --locked --python 3.12
Assert-Native
$port01BrowserNode = node --version
if ($LASTEXITCODE -ne 0) { throw 'Node version check failed' }
if ($port01BrowserNode -ne 'v24.15.0') { throw 'Node version mismatch' }
$port01BrowserNpm = npm --version
if ($LASTEXITCODE -ne 0) { throw 'npm version check failed' }
if ($port01BrowserNpm -ne '11.12.1') { throw 'npm version mismatch' }
npm --prefix quality/browser ci --include=dev
Assert-Native
node quality/browser/node_modules/playwright/cli.js install chromium
Assert-Native
$port01PostgresImages = @(docker --context $port01Context image ls --quiet --no-trunc postgres:17.11-bookworm)
Assert-Native
if ($port01PostgresImages.Count -eq 0) {
    if ((Read-Host 'Image absent. Type DOWNLOAD to authorize downloading postgres:17.11-bookworm') -cne 'DOWNLOAD') {
        throw 'Image download not authorized; STOP'
    }
    docker --context $port01Context pull postgres:17.11-bookworm
    Assert-Native
}
uv run --locked --no-sync python scripts/run_rg06b_e2e.py
Assert-Native
```

Do not invoke `npm test` directly: config requires launcher metadata. The launcher
does no downloads/builds. It creates a fresh random Compose project/volume and
loopback ports with [its own Compose file](quality/browser/compose.rg06b.yaml),
independently of the root demo. It runs serially, without retries, and owns process
trees via Windows Job Objects. Exit zero requires exactly two passing results,
verified targeted SQL cleanup, process completion and checked Docker teardown.
Failures retain new resources/private artifacts; inspect before rerunning.
Receipts, results and failure traces/screenshots live in
`quality/browser/.artifacts/<uuid>/`; review/redact raw files before sharing.
RG-05 protected lifecycle admission remains a separate, incomplete scope.

### Shutdown only owned services; retain manual data

After product/integration/smoke and separate browser E2E finish, re-query the manual
UUID using step 3 to verify retention. Stop **only the foreground manual Uvicorn
started in step 2 with Ctrl+C in its original terminal**; verify its shutdown log
and port 8000 no longer listening. Do not kill a PID found by port lookup. If
another process owns the port, stop and investigate. The smoke owns its subprocess;
the browser launcher owns its Job Objects and random Docker resources.

In the original DB-owning session, compare the current resource IDs, labels,
mounts, ports, network membership and volume creation receipt with step 2. Never
infer ownership merely from matching names. If identity is unchanged and no
DB-dependent checks remain, stop the exact recorded container:

```powershell
$port01CurrentDbId = docker @port01Compose ps -q db
Assert-Native
if ($port01CurrentDbId -ne $port01DbId) { throw 'Container changed; do not stop' }
if ((Read-Host 'Type SAME after rechecking all recorded resource identities') -cne 'SAME') {
    throw 'Ownership unconfirmed; preserve state'
}
docker --context $port01Context stop $port01DbId
Assert-Native
$port01Stopped = docker --context $port01Context inspect --format '{{.State.Status}}' $port01DbId
Assert-Native
if ($port01Stopped -ne 'exited') { throw 'DB shutdown unconfirmed' }
```

Retain the volume, network, manual rows and private receipts. No broad Docker
cleanup, volume removal, pruning or manual data deletion is needed. Failed or
uncertain browser runs retain their new resources for separate ownership review;
do not manually clean them through the root demo procedure.

### Offline evaluator: separate Python 3.13.1

The product declares `>=3.12,<3.13` in [pyproject.toml](pyproject.toml).
Offline CI uses **CPython 3.13.1 / Unicode 15.1.0**; Python 3.12 supplies Unicode
15.0.0. This pins evaluator Unicode behavior, not product compatibility with 3.13.
The workflow exports pytest dependencies from the frozen lock, prunes httpx and
does not install the product under 3.13.

PowerShell reproduction of accepted modules (**fresh Windows setup/execution
unverified**), in a separate fresh terminal after the environment/configuration
review from step 1 (do not start Docker or run its resource section). Recreate
`Assert-Native` and `$ErrorActionPreference = 'Stop'`, enter the reviewed checkout,
and verify the baseline/README hash. Do not inherit product `UV_PROJECT_ENVIRONMENT`,
`DATABASE_URL` or a virtualenv activation. All directories below are generated:

```powershell
$port01Repo = (Get-Location).Path
$port01Eval = Join-Path $env:TEMP ('reqguard-offline-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $port01Eval) { throw 'Evaluation directory already exists' }
New-Item -ItemType Directory -Path "$port01Eval/work" | Out-Null
uv venv --no-project --python 3.13.1 "$port01Eval/venv"
Assert-Native
$port01Python = Join-Path $port01Eval 'venv/Scripts/python.exe'
& $port01Python -c "import sys, unicodedata; print(sys.version, unicodedata.unidata_version); assert sys.version_info[:3] == (3,13,1) and unicodedata.unidata_version == '15.1.0'"
Assert-Native
uv export --frozen --only-group dev --prune httpx --no-emit-project --no-header --output-file "$port01Eval/requirements.txt"
Assert-Native
uv pip sync --python $port01Python --require-hashes --only-binary :all: "$port01Eval/requirements.txt"
Assert-Native
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTEST_ADDOPTS = ''
Set-Location "$port01Eval/work"
& $port01Python -m pytest -v -ra --strict-config --strict-markers -c "$port01Repo/pyproject.toml" -o addopts= -p no:cacheprovider --basetemp="$port01Eval/pytest-tmp" --junitxml="$port01Eval/results.xml" "$port01Repo/tests/test_evaluation_dataset.py" "$port01Repo/tests/test_evaluation_hard_fail.py" "$port01Repo/tests/test_evaluation_metrics.py" "$port01Repo/tests/test_evaluation_evidence.py" "$port01Repo/tests/test_evaluation_fake_provider.py" "$port01Repo/tests/test_evaluation_execution.py"
Assert-Native
Set-Location $port01Repo
```

External cwd and sibling `basetemp` are required by evidence fixtures.
Symlink/junction outcomes depend on OS and Windows privileges; a Windows skip
profile is not Linux acceptance. D2 deadline cases include simulated time, not
measured live-provider latency. Authoritative per-job selectors and strict JUnit
gates are in the workflow below. Offline tests need no AI API, DB or Docker;
environment bootstrap may need downloads.

## Coverage and GitHub Actions evidence

PORT-01 local validation on 2026-10-25: the three product modules listed above
returned **28 passed, 1 Starlette/httpx deprecation warning** under the existing
Python 3.12.10 environment, using `python -u -m pytest -q -p no:cacheprovider`
with those explicit paths, bytecode disabled and plugin autoload disabled.
The sandbox attempt produced no result and was interrupted; the repeat outside
the sandbox exited 0. `node --test tests/ui.test.mjs` returned **11 passed**.
This reused environment is validation evidence, not a clean-checkout prerequisite;
the documented `uv sync` / `uv run` setup path remains unverified for PORT-01.
Historical PORT-01 static checks: eight then-current PowerShell blocks parsed,
local links/inputs matched tracked files, `docker compose config -q` and
`git diff --check` exited 0. That count/config execution does not describe this
RG-README-02 revision; no Docker command was executed for the correction.

| Layer | Sources / checks | Evidence boundary |
| --- | --- | --- |
| API contract | [test_analyses.py](tests/test_analyses.py) | Fixture, distinct UUIDs, validation, unsupported input, OpenAPI; persistence stub. |
| Persistence unit | [test_persistence_unit.py](tests/test_persistence_unit.py) | Mapping, binding, COMMIT boundary, sanitized failures/no retries; no real DB. |
| UI HTTP / frontend | [test_ui.py](tests/test_ui.py), [ui.test.mjs](tests/ui.test.mjs) | Routes/assets, API mapping, request/state/errors, text rendering; stubs/DOM adapter. Not standalone suites in current workflows. |
| Real DB / smoke | [test_postgres_integration.py](tests/test_postgres_integration.py), [smoke](scripts/rg04_network_sql_smoke.py) | Committed reads, exact schema, constraints, rollback, SQL NULL and targeted cleanup. Not standalone Actions jobs. |
| Browser E2E | [analyses.spec.ts](quality/browser/analyses.spec.ts), [CI harness](scripts/run_rg06d_ci.py), [workflow](.github/workflows/rg06d-e2e.yml) | Two Chromium scenarios; real UI/HTTP/SQL, sentinel and cleanup receipts. |
| Offline rules / metrics | [dataset](tests/test_evaluation_dataset.py), [hard-fail](tests/test_evaluation_hard_fail.py), [metrics](tests/test_evaluation_metrics.py) | 297 expected cases; synthetic data, mechanical rules, aggregation and incomplete-evidence gates. |
| Evidence integrity | [evidence tests](tests/test_evaluation_evidence.py) | 173 expected cases; Linux gate requires 171 passes and exactly two NTFS-only skips, plus real POSIX symlink passes. |
| Fake execution | [provider](tests/test_evaluation_fake_provider.py), [execution](tests/test_evaluation_execution.py) | 101 expected passes; deterministic outputs, provenance, deadlines, cancellation, partial failure; exact identity gate. |

Current run metadata and job/step conclusions were verified read-only through the
GitHub API on **2026-10-27**. Both runs are completed/success, push to `main`,
attempt 1, at **`3b04823484222c1063d3f58f428535198c8be10e`**, completed on
2026-10-26. This is Linux hosted evidence, not literal Windows execution or a run
of this uncommitted README revision. Logs/artifact bytes were not re-audited here.

| Current workflow run | Verified job conclusions |
| --- | --- |
| [RG-06D — 40362887104](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/40362887104) | [e2e](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/40362887104/job/121712748700): success; harness, privacy publication, upload/final gate and Stop containers steps success. |
| [RG-07C — 40362887081](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/40362887081) | [evaluator](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/40362887081/job/121712748210), [evidence integrity](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/40362887081/job/121712747471), [fake execution](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/40362887081/job/121712748116): success, including strict count/identity gates. |

[Accepted PORT-01-R1 documentation commit](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/commit/3b04823484222c1063d3f58f428535198c8be10e)
and [manual runtime evidence index](docs/evidence/PORT-01-R1_MANUAL_RUNTIME_CLOSURE_2026-10-26.md)
record RG-00's supplied Phase A/Phase B acceptance and independent seven-file
verification for the Codespace manual UI → HTTP → SQL path at `ce72c5b`.
Positive response/full JSONB equality and whitespace 422 with identical complete
exported snapshots are dated primary-file findings. Runtime baseline/capture
provenance and shutdown remain **OPERATOR RECEIPT SUPPORTED** where specified.
The manual row and volume were retained; SQL DELETE was not authorized.
Private originals are not public download links and are not reproduced here.
This acceptance does not release Portfolio V1.0 or establish Windows reproduction.

Historical verification through GitHub API on **2026-10-25**: remote `main` then and both following
completed **successful** runs use baseline
`ce72c5bb6f35b1935bb0c3dee1fa15b1b1aef40a`. This is dated evidence, not a promise
that a later commit or local environment passes.

| Workflow / baseline run | Jobs and reviewable evidence |
| --- | --- |
| [RG-06D — run 40175289284](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/40175289284) | [e2e](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/40175289284/job/121114515959): success. Ubuntu 24.04, Python 3.12.10, uv 0.11.22, Node 24.15.0/npm 11.12.1, Chromium 1248, digest-pinned PostgreSQL 17.11. |
| [RG-07C — run 40175289231](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/40175289231) | [evaluator](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/40175289231/job/121114515460), [evidence-integrity](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/40175289231/job/121114515647), [fake-execution](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/40175289231/job/121114515635): all success. [Selectors/gates](.github/workflows/rg07c-evaluator.yml) require counts/outcomes above under isolated Python 3.13.1. |

RG-06D runs on PRs, pushes to `main` and manual dispatch; RG-07C runs on pushes to
`main` and PRs targeting `main`. These are independent workflows, not an aggregate
unit/integration/browser job. Action revisions are pinned by full SHA.

For E2E review, inspect job logs and the run's **Artifacts** section. The API listed
`rg06d-40175289284-1` (ID `12591414068`, 12,200 bytes, not expired at verification;
expiry `2026-11-01T09:07:00Z`). Artifact bytes and individual logs were **not
downloaded/re-audited for PORT-01**. Harness gates require two passing results,
zero failures/skips/flaky/retries, `CLEANED` SQL evidence and verified process
shutdown. Publication/upload success and an artifact ID are additional final gates.
The safe artifact contains named JSON receipts/reports, redacted text logs and
a hash manifest with seven-day retention; binary traces/screenshots are excluded.
The offline workflow has job logs but no artifact upload step. Expiration limits
later inspection, without changing the dated run conclusion. GitHub service
disposal is outside harness attestation; inspect job cleanup logs separately.
Hard cancellation/runner loss can interrupt receipts and publication.

## AI Quality: what is established

The [evaluation specification](docs/ai-quality/RG-07A_EVALUATION_SPEC_v1.md) and
[synthetic dataset](reqguard/evaluation/datasets/rg07a-synthetic-v1.json) define an
offline evaluation contract. Implemented components cover strict dataset loading,
hard-fail rules, metric/gate aggregation, immutable evidence and fake execution.
See [evaluator evidence](docs/ai-quality/RG-07B-02_IMPLEMENTATION_EVIDENCE.md),
[metrics evidence](docs/ai-quality/RG-07B-03_IMPLEMENTATION_EVIDENCE.md),
[evidence integrity](docs/ai-quality/RG-07D-D1_IMPLEMENTATION_EVIDENCE.md), and
[fake execution contract](docs/ai-quality/RG-07D-D2_EXECUTION_CONTRACT.md).

Passing tests establish deterministic mechanical verification of supplied synthetic
inputs/evidence. They do not establish live-model reasoning, semantic correctness
or completeness, authentic human annotations, comprehensive Unicode conformance or
production AI safety. Missing assessment/provenance must not become a passing
quality verdict. The offline fake provider is distinct from the product's single
authored fixture. No model key or paid call is needed.

## Published scope, local RG-05 work and historical evidence

The demo uses tracked product, schema, browser package and evaluator files only.
Local/untracked `quality/api/` orchestration, shim, package/config/specs,
`ChatGPT file/` handoffs and RG-04 evidence reports are **not clean-checkout
requirements or published functionality**. Their results cannot substitute for
published browser/CI evidence. A small tracked RG-05 native source/test/build subset
exists; it does not make local orchestration complete or runnable from a clone.

Preserved historical references:

- [RG-05 closure matrix](docs/rg05/RG-05-V2.1_B01-B10_CLOSURE_MATRIX.md): accepted
  supplementary L1 syntax/type exit 0 (no preserved log), L2 compilation/linking,
  L3 18/18 synthetic tests. Protected-build acceptance and operational Win32
  security remain OPEN; the RG-05 lifecycle is incomplete.
- [Supplementary runbook](docs/rg05/SUPPLEMENTARY_REPRODUCTION.md): environment
  blocked / fresh reproduction unverified. Native procedures remain separate
  from this demo and retain their own execution requirements.
- [RG-07C implementation evidence](docs/ai-quality/RG-07C_IMPLEMENTATION_EVIDENCE.md),
  [D1 CI evidence](docs/ai-quality/RG-07D-D1_CI_IMPLEMENTATION_EVIDENCE.md), and
  [D2 CI evidence](docs/ai-quality/RG-07D-D2_CI_IMPLEMENTATION_EVIDENCE.md) retain
  implementation-time local results and limitations. Historical “CI NOT RUN”
  statements describe that time; dated hosted baseline runs above supersede
  them for current portfolio CI evidence.
- [RG-04 capture commit](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/commit/433a4194a36325f017d877d8d5a812ce4396fd5f)
  preserves accepted persistence history; its historical 43-pass result is not a
  current all-suite selector or a fresh reproduction result.
- RG-06B implementation at
  [`9bf28ec`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/commit/9bf28ecba68be0e4b40b298a6bab24b6297f6f6a)
  and RG-06D implementation at
  [`1ff5b19`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/commit/1ff5b19ccf7f112931b69386f1543a8eeb829d33)
  retain their historical implementation/NOT RUN boundaries. The dated hosted
  RG-06D results above are distinct; no Windows RG-06B runtime PASS is newly claimed.
- [Baseline README](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/ce72c5bb6f35b1935bb0c3dee1fa15b1b1aef40a/README.md)
  preserves the detailed earlier RG-06B/RG-06D implementation narrative in Git history.

Authentication, production deployment, live-model semantic evaluation and a complete
RG-05 lifecycle are not demonstrated. k6, axe-core and ZAP belong to a separate
future project. Old AI QA Assistant results are not ReqGuard evidence.
