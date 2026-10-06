# ReqGuard Quality Platform

Minimal FastAPI API with a deterministic fake provider. Requires Python 3.12
and [uv](https://docs.astral.sh/uv/getting-started/installation/).

## Install, run, and test

Run from the repository root:

```sh
uv lock --check --python 3.12 --no-cache
uv sync --locked --group dev --python 3.12 --no-cache
uv run --locked --no-cache uvicorn reqguard.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
uv run --locked --no-cache pytest -q
```

`uv.lock` pins transitive dependencies and should be version-controlled together
with `pyproject.toml`. The check and locked commands fail if the lockfile is
outdated instead of rewriting it. Installation requires access to the package
index; `--no-cache` avoids reusing the uv package cache.

The RG-02 local check used uv 0.11.22 and CPython 3.12.10 on Windows, with a
temporary copy of only the baseline files (no existing `.venv`, caches, or Git
metadata). Locked installation created a new `.venv`; the full suite returned
12 passed and 1 Starlette/httpx deprecation warning. A real localhost request to
Uvicorn returned HTTP 200 with the fixture response described below. This is a
local implementation check, pending independent review. The warning remains
visible; dependencies have not been changed to silence it.

Interactive API documentation
is at http://127.0.0.1:8000/docs; OpenAPI is at http://127.0.0.1:8000/openapi.json.

Example request (PowerShell):

```powershell
$response = Invoke-WebRequest -Method Post -Uri http://127.0.0.1:8000/analyses -ContentType 'application/json' -Body '{"requirement_text":"The user can quickly reset their password"}'
$response.StatusCode
$response.Content
```

Stop the server with Ctrl+C in its terminal after the request.

## Contract and limitations

`POST /analyses` requires a string `requirement_text` containing at least one
non-whitespace character, with a maximum of 2000 characters. Invalid input returns
HTTP 422. Length is checked on the original text; text is not trimmed or normalized.

Only the exact example above has a fixture. It returns HTTP 200 with
`provider: "fake"`, `status: "completed"`, a UUID `run_id`, and a structured
`analysis` containing the ambiguity of "quickly", a missing measurable criterion,
and a candidate test scenario. Repeated requests return identical analysis and
new run IDs. Other valid strings return HTTP 200 with
`status: "unsupported_fixture"` and `analysis: null`; no analysis is invented.

This is authored synthetic fixture data, not semantic evaluation or evidence of
live model quality. The candidate's time limit remains unspecified. There are no
AI calls, persistence, authentication, UI, database, Docker, or CI. These Python
API tests verify this minimal behavior; an independent TypeScript/Playwright
quality layer remains future work.
