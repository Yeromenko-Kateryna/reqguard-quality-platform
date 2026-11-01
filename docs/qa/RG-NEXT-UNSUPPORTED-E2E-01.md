# RG-NEXT-UNSUPPORTED-E2E-01 — Unsupported fixture persistence

## Purpose

Verify the existing unsupported-result branch through Chromium, the real FastAPI
HTTP endpoint and an independent PostgreSQL connection. This extends the existing
supported-result and HTTP 422 scenarios to exactly three serial scenarios.
Application behavior, schema, Compose and workflows are unchanged.

## Preconditions

Use an independently approved checkout and an isolated, launcher-owned database.
Never point this suite at historical root Compose resources or a shared database.
The existing launcher/configuration must admit the run ID, artifact directory,
ports, PostgreSQL identity and schema. The database starts empty; the suite creates
one owned sentinel and requires its exact preservation.

Existing pinned tools are CPython 3.12.10, uv 0.11.22, Node 24.15.0,
npm 11.12.1, Playwright 1.64.0, bundled Chromium revision 1248 and PostgreSQL 17.11.
Dependencies and browser binaries must already satisfy the applicable launcher
checks. Runtime execution and dependency setup require their own authorization.

## Scenario and assertions

After the supported and invalid scenarios settle, submit one valid unsupported
synthetic requirement containing the run ID and two spaces at each end.

- Observe exactly one actual POST to /analyses, without retry.
- Require HTTP 200 and exactly run_id, provider, status and analysis.
- Require a UUIDv4, provider fake, status unsupported_fixture and analysis null.
- Independently read exactly one committed row by the returned UUID.
- Match provider/status and preserve original_input, including surrounding spaces.
- Require analysis_payload IS NULL: SQL NULL, not JSON null.
- Require a parseable created_at with an explicit UTC offset.
- Require the only database delta to be this owned row; preserve the sentinel.
- Match visible UI metadata to the response, show the unsupported explanation,
  and require the analysis area to be empty.

## Ownership and cleanup

Reuse the established SQL wrapper, snapshots and removeOwned transaction.
Before DELETE, lock and compare the complete owned row; require one deleted row,
the exact baseline before COMMIT and the same baseline after COMMIT.
The sentinel is removed only under the existing settled-state/ownership checks.

Unknown request ownership, SQL errors or uncertain transaction outcomes fail closed.
Do not retry, broadly delete, or infer rollback after uncertain COMMIT.
Both harnesses require unsupportedCleaned=true in the final SQL cleanup receipt,
alongside the existing supported/invalid flags and uncertain=false.

## Existing entrypoints

These are future execution instructions, not a record of execution.

### GitHub Actions

Use the existing .github/workflows/rg06d-e2e.yml lifecycle on an approved change:
prepare evidence, provision its job-local PostgreSQL service, install locked
dependencies and Chromium, execute the harness once, then publish safe evidence.
The workflow's commands are:

```text
python3 -B scripts/run_rg06d_ci.py prepare
.venv/bin/python -B scripts/run_rg06d_ci.py run
python3 -B scripts/run_rg06d_ci.py publish
```

These commands require the workflow-provided environment, service port, runner
paths and setup steps. They are not standalone local commands. No workflow change
or CI dispatch is part of this implementation.

### Windows

Use the existing scripts/run_rg06b_e2e.py entrypoint through the admitted CPython
3.12.10 environment, with its existing Windows, tool, process and Docker preflight:

```text
python -B scripts/run_rg06b_e2e.py
```

The launcher owns run IDs, child environment, resource admission and teardown.
Do not invoke the spec directly, substitute a database URL, reuse a server or use
root Compose as a fallback. Any preflight failure is a stop.

## Required evidence

Both harnesses require exactly the three named Chromium scenarios, one passed
result per scenario, retry index zero, and no skipped, unexpected or flaky results.

The new scenario creates unsupported-response-id.json, unsupported-sql.json and
unsupported-cleanup.json. The SQL snapshot receipt is also a Playwright attachment.
The final sql-cleanup.json includes unsupportedCleaned.
The CI publisher explicitly allowlists all three new receipts; it retains existing
redaction, sensitive-content rejection and publication-manifest checks.

For review retain the commit and CI run/job URLs, results.json, all required SQL
receipts, process/run summaries, safe publication manifest and artifact identity.
Partial or failed evidence must not be described as PASS.
Do not publish DSNs, credentials, raw private evidence, traces or screenshots
outside the existing approved publication mechanism.

## Limitations

This verifies deterministic fake-provider mechanics, not semantic AI quality.
Python integration tests already cover unsupported persistence; this adds the
real browser/UI layer. It does not establish Windows reproduction, Docker lifecycle
or CI success until those paths are separately authorized and executed.
The PostgreSQL verifier uses UTC; baseline comparisons assume the isolated suite
has no concurrent writers. Existing process, timeout and resource-race limitations
remain. This task does not modify or resume PORT-02.
