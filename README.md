# ReqGuard Quality Platform

FastAPI with a deterministic fake provider and PostgreSQL persistence. Requires
Python 3.12, uv, and a running Docker Desktop Linux engine.

## Local PostgreSQL and installation

Run from the repository root in PowerShell. Before creating resources, inspect:

```powershell
docker version
docker volume inspect reqguard_rg04_v11_pgdata_20261008
docker ps -a --filter label=com.docker.compose.project=reqguard_rg04_v11
docker ps -a --filter name=reqguard_rg04_v11
docker ps -a --filter publish=55432
docker network ls --filter label=com.docker.compose.project=reqguard_rg04_v11
```

A first-run volume inspection must report `no such volume`. Stop if an
unidentified existing resource conflicts. Historical resources must not be reused
or deleted. Also confirm that host port 55432 is available. This task's project is
`reqguard_rg04_v11`, with volume `reqguard_rg04_v11_pgdata_20261008`.

```powershell
$rg04Venv = Join-Path $env:TEMP ('reqguard-rg04-v11-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $rg04Venv) { throw 'Environment already exists' }
$env:UV_PROJECT_ENVIRONMENT = $rg04Venv
uv lock --check
uv sync --locked --python 3.12
uv run --locked python -c "import sys, psycopg; print(sys.executable); print(psycopg.__version__)"
docker compose config -q
docker compose up --wait --wait-timeout 90 db
docker compose exec -T db pg_isready -U reqguard -d reqguard
docker compose exec -T db psql -X -v ON_ERROR_STOP=1 -U reqguard -d reqguard -f /schema/001_init.sql
docker compose exec -T db psql -X -v ON_ERROR_STOP=1 -U reqguard -d reqguard -f /schema/001_init.sql
$env:DATABASE_URL = 'postgresql://reqguard:local_only_reqguard@127.0.0.1:55432/reqguard'
```

These are synthetic local credentials. The schema is explicitly mounted read-only
at `/schema/001_init.sql`; it is bootstrapped manually. `CREATE TABLE IF NOT EXISTS`
is idempotent but does not repair schema drift. Integration metadata assertions
check the exact schema and constraints. PostgreSQL image is `postgres:17.11-bookworm`.

Keep `UV_PROJECT_ENVIRONMENT` and `DATABASE_URL` set for subsequent commands. In a
new shell, set the environment path to the same dedicated environment. The
existing project `.venv` is not required.

## API

```powershell
uv run --locked uvicorn reqguard.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
Invoke-WebRequest -Method Post -Uri http://127.0.0.1:8000/analyses -ContentType 'application/json' -Body '{"requirement_text":"The user can quickly reset their password"}'
```

Stop the server with Ctrl+C. OpenAPI is at http://127.0.0.1:8000/openapi.json.

`POST /analyses` requires a strict string `requirement_text` of 1–2000 characters
containing a non-whitespace character. Original text is preserved without trimming.
Invalid requests return HTTP 422 before provider or persistence execution.

Only the exact example has an authored fixture. Its response has a new UUID
`run_id`, `provider: "fake"`, `status: "completed"`, and an `analysis` object.
Other valid text returns `status: "unsupported_fixture"` and `analysis: null`.

Both results require an acknowledged PostgreSQL COMMIT before HTTP 200. The six
columns in `public.analyses` store the response UUID, provider, status, original
validated input, analysis only, and a PostgreSQL `CURRENT_TIMESTAMP` timestamp.
The timestamp is the transaction start time. Unsupported analysis is **SQL NULL**,
not JSON literal `null`. CHECK constraints enforce status/payload consistency.

Connection, INSERT, or COMMIT errors return HTTP 503 with
`{"detail":"Persistence unavailable"}`. Missing `DATABASE_URL` has the same
response. There are no automatic retries. A failed COMMIT acknowledgement may
leave an uncertain outcome; HTTP 503 does not prove row absence. Unexpected
application errors retain HTTP 500 semantics.

## Minimal product UI

With PostgreSQL/schema and DATABASE_URL configured as above, start the same
Uvicorn command and open http://127.0.0.1:8000/. No frontend build, CDN or runtime
JavaScript packages are required. JavaScript must be enabled in the browser.

Submit the prefilled exact fixture to see run_id, provider, completed status,
ambiguities, missing measurable criteria and candidate tests. Other valid text
shows unsupported_fixture with no analysis. Blank/invalid input displays the
API's HTTP 422 details. Loading prevents duplicate submissions and clears old
results; HTTP/network failures never display success or automatically retry.
A network failure may occur after the server committed: check before resubmitting.
API-provided text is rendered as text nodes, never interpreted as HTML.

The page makes a same-origin JSON POST to the existing /analyses endpoint.
Database transactions, schema, response contracts and fake-provider behavior are
unchanged. The UI demonstrates authored fixture behavior, not live AI quality.

## Verification

```powershell
uv run --locked pytest -q tests/test_analyses.py
uv run --locked pytest -q tests/test_persistence_unit.py
uv run --locked pytest -q tests/test_ui.py
uv run --locked pytest -q tests/test_postgres_integration.py
uv run --locked pytest -q tests/test_postgres_integration.py
uv run --locked pytest -q
uv run --locked python scripts/rg04_network_sql_smoke.py
```

Frontend request/state/rendering checks use Node's built-in test runner (Node
24.15.0 reference; no npm install or RG-05 orchestration needed):

```powershell
node --test tests/ui.test.mjs
```

UI HTTP tests replace persistence with a test stub; frontend tests use a small
DOM adapter, not a browser engine. They do not establish PostgreSQL persistence
or browser end-to-end coverage. Browser and CI acceptance remain separate work.

Baseline tests use a repository stub. Unit tests verify mapping, validation,
parameter binding, transaction completion and sanitized failures. They do not
prove PostgreSQL persistence. Integration tests require real PostgreSQL and
`DATABASE_URL`; missing configuration fails rather than silently skipping.
They independently read committed rows using new connections, check metadata,
exercise negative constraints and rollback, and verify targeted cleanup preserves
a sentinel row. Each run uses new UUIDs and does not depend on an empty table.

The smoke starts its own Uvicorn subprocess, makes supported and unsupported
HTTP requests, and compares each actual response with a separate external `psql`
subprocess in the DB container. It prints SQL evidence, deletes only its own UUIDs,
and terminates its own server. Docker resources remain available for inspection.

The existing Starlette/httpx deprecation warning remains visible. This is authored
fake-provider behavior, with no live AI calls or semantic quality evidence.
Independent Playwright UI/API-to-SQL, CI, authentication and production deployment
are outside this slice.

## RG-06B browser to PostgreSQL checks

The independent package in `quality/browser/` contains exactly two Chromium
scenarios. This implementation has **NOT RUN** against a browser or PostgreSQL;
static validation does not establish E2E PASS. It uses no RG-05 orchestration,
retained session helpers, historical containers or application persistence stubs.

Prerequisites for a separately authorized first run:

- Windows x64, CPython 3.12 (including its base interpreter), uv, Git;
- Node.js **24.15.0**, npm **11.12.1**;
- the Python environment synchronized from the existing `uv.lock`;
- `@playwright/test` **1.64.0**, its matching Chromium installation and `pg`
  **8.23.1**, installed from the independent package lock;
- Docker Desktop with a local named-pipe context and Linux engine, Compose **2.***
  or exactly **5.5.1** (other v5 releases and all other majors are rejected),
  and the **already present** `postgres:17.11-bookworm` image;
- a trusted local checkout, trusted tools on PATH and a user-private artifacts
  parent. The launcher does not change ACLs or provide RG-05 security admission.

The Compose admission gate can be checked statically from the repository root.
This compiles the launcher and evaluates only its admission expression; it does
not import or run the launcher, invoke Docker, or establish runtime compatibility:

```powershell
@'
import ast
from pathlib import Path

source = Path('scripts/run_rg06b_e2e.py').read_text(encoding='utf-8')
compile(source, 'scripts/run_rg06b_e2e.py', 'exec')
tree = ast.parse(source)
gates = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
         and isinstance(n.func, ast.Name) and n.func.id == 'require'
         and len(n.args) == 2 and isinstance(n.args[1], ast.Constant)
         and n.args[1].value == 'COMPOSE_V2_OR_EXACT_5_5_1_REQUIRED']
assert len(gates) == 1
gate = compile(ast.Expression(gates[0].args[0]), '<compose-admission>', 'eval')
for version in ('2.0.0', '2.39.4', '2.999.0', '5.5.1', '5.5.0', '5.5.2',
                '5.6.0', '6.0.0', '1.29.2', '', '5.5.1-rc.1', '5.5.1+build'):
    expected = version in ('2.0.0', '2.39.4', '2.999.0', '5.5.1')
    actual = eval(gate, {'__builtins__': {}}, {'compose_version': version})
    assert actual is expected, (version, actual, expected)
    print(f'{version!r}: {"ACCEPT" if actual else "REJECT"} PASS')
print('Python syntax and Compose admission static checks PASS')
'@ | python -
git diff --check
```

The lock preserves exact registry integrity metadata from the locally available
dependency catalog. Installation/registry availability and Chromium availability
have not been established by this patch. Future setup commands below may download
dependencies and need separate authorization; they were not run for implementation:

```powershell
uv sync --locked --python 3.12
npm --prefix quality/browser ci --include=dev
node quality/browser/node_modules/playwright/cli.js install chromium
# Only if this image is not already installed, authorize provisioning separately:
docker pull postgres:17.11-bookworm
```

Run from the repository root only after independent review and execution approval:

```powershell
uv run --locked --no-sync python scripts/run_rg06b_e2e.py
```

Do not invoke `npm test` directly or substitute the root Compose file. The config
requires launcher state and accepts only one fresh local database boundary. No
downloads, dependency syncing, image pulls or builds occur inside the launcher.
Ambient `NODE_*`, `PW_TEST_*`, unexpected `PLAYWRIGHT_*`, Docker remote overrides
and Python project/path overrides cause STOP; `PLAYWRIGHT_BROWSERS_PATH` is allowed
so a previously installed browser cache can be selected. Environment changes are
limited to child processes. Inherited `PG*` connection settings are removed from
those children so only the generated DATABASE_URL selects the database.
No global variables or existing files are rewritten.
Child TEMP/TMP point at a newly created `temp/` inside the run artifacts. Browser
profiles and tool temporary files can be created there; failed runs retain them.

Each invocation uses a fresh random `rg06b_<uuid>` Compose project, loopback-only
database port, random in-memory credential, one newly named container, network
and volume, and `quality/browser/.artifacts/<uuid>/`. Existing resource names and
project labels are checked before creation; any collision or failed inspection
stops the run. Schema is mounted read-only from `db/001_init.sql` and applied
with `psql -X -v ON_ERROR_STOP=1`. The API is an actual single-worker Uvicorn
process started by Playwright on another loopback port, with server reuse disabled.
The image ID, resource IDs, source/lock hashes, Python package versions and Git
HEAD are recorded. A moving image tag is recorded by actual ID; identical future
binary/image bytes are not promised.

The tests run serially, once, without retries. An independent `pg` connection
checks PostgreSQL version, database/role, table columns and constraints, requires
an initially empty fresh table, and inserts a uniquely owned sentinel:

1. Submit the exact authored fixture through the page. Require one browser POST,
   HTTP 200, the full expected response and visible run_id/provider/status/analysis.
   Parameterized SQL using the returned UUID must find exactly one committed row
   matching the original input, response JSONB and valid database timestamp. The
   complete table delta must contain only that row and preserve the sentinel.
2. Submit whitespace through the page. The test requires an actual browser POST
   and FastAPI HTTP 422 with the expected
   validation location. The form uses `novalidate`; the request must reach FastAPI.
   Require the error UI, no result and identical full SQL
   snapshots before/after, including the sentinel. A blocked browser submission
   or unavailable API cannot satisfy this scenario.

Cleanup deletes only acknowledged, independently verified owned UUIDs. Each
delete locks and compares the full row in a transaction, checks one deleted row,
checks the expected remaining snapshot, commits and verifies again. The sentinel
is deleted last only when no request/SQL outcome or unexpected row is unresolved.
SQL failures, uncertain COMMIT acknowledgements and missing run IDs are not
treated as evidence that nothing was written. No broad DELETE, truncate, cleanup
retry or adoption of existing data is permitted.

Every subprocess tree is assigned to a Windows Job Object before its target
command is released. Normal completion requires both wrapper exit and an empty
job. Timeouts/exceptions terminate only that owned job and wait for confirmation;
any forced or unknown process state fails the run. Docker daemon operations can
outlive their CLI, so such failures retain resources and forbid automatic retry.
There is no PID-based kill of unrelated processes. Port selection has a bind race;
binding/startup failure must STOP rather than connect to or adopt another service.

On complete test and SQL-cleanup success, the launcher rechecks resource IDs,
labels, mounts, port and network members, then removes only this Compose project
and its volume, without `--remove-orphans`. Absence is independently checked.
All failure paths preserve newly created Docker resources and artifacts: do not
rerun or remove anything until the private receipts establish process completion,
resource ownership and database outcome. Unknown cleanup is not safe cleanup.
No automatic failure cleanup or generic recovery framework is provided.

Private artifacts include command launch/exit receipts, raw stdout/stderr and
their byte counts/SHA-256, `launch.json`, whitelisted `resources.json`, baseline
and SQL result/cleanup receipts, JSON Playwright results and `final.json` with
file hashes. Failure screenshots/traces are retained; video is disabled. Streams
can contain local paths: keep the ignored artifacts private, redact before sharing,
and never upload Docker inspection output or credentials. Full container environment
is deliberately excluded from captured inspection. The `.artifacts` parent uses
the user's existing permissions; do not run under a shared or untrusted parent.

Exit zero requires exactly two passing results, no skip/failure/flaky result,
confirmed SQL cleanup, completed process trees and verified Docker teardown.
Other outcomes exit nonzero and are STOP/FAIL evidence, not E2E PASS. The fake
provider demonstrates authored fixture behavior only; CI, operational security,
live AI quality and adversarial same-user/administrator interference remain outside
this milestone. No RG-04/RG-05 artifacts or resources are touched.

## RG-05 supplementary synthetic validation

The [RG-05 closure matrix](docs/rg05/RG-05-V2.1_B01-B10_CLOSURE_MATRIX.md)
records accepted L1–L3 supplementary synthetic evidence: an interactive MSVC
syntax/type check (exit `0`, no separately preserved log), native compilation and
linking, and 18/18 synthetic native tests. Evidence fingerprints and limitations
are recorded in the matrix. Protected-build acceptance and operational Win32
security remain **OPEN**; the RG-05 lifecycle is not complete. B-01–B-10
dispositions remain unchanged. These historical results do not establish current
CI status or semantic AI quality.

For a future, separately authorized fresh-checkout run, see the
[supplementary L1–L3 runbook](docs/rg05/SUPPLEMENTARY_REPRODUCTION.md).
The runner is review material; adding it does not authorize native execution.
