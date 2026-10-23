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

## Verification

```powershell
uv run --locked pytest -q tests/test_analyses.py
uv run --locked pytest -q tests/test_persistence_unit.py
uv run --locked pytest -q tests/test_postgres_integration.py
uv run --locked pytest -q tests/test_postgres_integration.py
uv run --locked pytest -q
uv run --locked python scripts/rg04_network_sql_smoke.py
```

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
fake-provider behavior, with no live AI calls or semantic quality evidence. UI,
Playwright, CI, authentication and production deployment are outside this slice.

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
