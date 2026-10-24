# RG-07D-D2 — offline execution contract v1

This slice executes the twelve frozen RG-07A examples mechanically through a
dedicated fake provider. It registers D1 source evidence and captures, with no
model, network, application, database, or third-party dependency. A completed
execution says nothing about semantic quality. No evaluator, annotation, score,
assessment, snapshot, seal, or semantic verdict is created.

## Public interfaces

```python
FakeRequest(evaluation_run_id: str, request_id: str, example_id: str,
            requirement_text: str, input_sha256: str, fixture_sha256: str,
            trusted_task_policy: str = TRUSTED_POLICY, version: str = REQUEST_VERSION)
FakeResponse(request_id: str, example_id: str, correlation_id: str, raw: bytes,
             version: str = RESPONSE_VERSION)
Fixture(example_id: str, outcome: str, raw: bytes | None)
FixtureSet(revision: str, scenario: str, entries: tuple[Fixture, ...])
ExecutionConfig(root: Path, package_id: str, evaluation_run_id: str,
                dataset_path: Path = DATASET_PATH, fixture_set: FixtureSet = fixtures(),
                deadline_ms: int = DEADLINE_MS, baseline_commit: str = "unavailable",
                evaluated_commit: str = "unavailable", dirty_state: str = "unavailable")
ExecutionResult(root: Path, state: str, termination: str,
                captures: tuple[CaptureRecord, ...], dispatched: tuple[str, ...],
                unresolved: tuple[str, ...], verified: bool, failure: str | None = None)
AttemptContext(runtime: ExecutionRuntime, deadline_ms: int)
fixtures(scenario: str = "nominal") -> FixtureSet
validate_fixtures(value: FixtureSet) -> None
validate_request(request: FakeRequest, fixture_set: FixtureSet) -> None
correlation_id(request: FakeRequest) -> str
validate_response(response: FakeResponse, request: FakeRequest) -> None
DeterministicFakeProvider(fixture_set: FixtureSet)
DeterministicFakeProvider.invoke(request: FakeRequest, context: ProviderContext) -> FakeResponse
execute(config: ExecutionConfig, *, provider: FakeProvider | None = None,
        runtime: ExecutionRuntime | None = None) -> ExecutionResult
```

All request, response, fixture, configuration, context and result dataclasses are
frozen. The runtime is intentionally mutable to support cooperative cancellation
and virtual clocks. `FakeProvider` and `ProviderContext` are structural protocols:
`invoke(request, context)` and `checkpoint()`, respectively. The injected provider
is an offline testing seam; the caller must not inject a network implementation.

`FakeRequest` fields: `evaluation_run_id`, `request_id` (`request-<example_id>`),
`example_id`, exact `requirement_text`, lowercase hex `input_sha256`, lowercase hex
`fixture_sha256`, exact `trusted_task_policy`, and
`version=rg07d-fake-request-v1`. Identities use portable ASCII tokens of at most
64 characters. A request contains no expectations, rationale, authorized facts,
forbidden literals, category, rubric, assessment or previous output. The payload
is the frozen product requirement, separate from the trusted task policy;
remaining fields are routing/integrity metadata. Policy bytes reproduce RG-07A
section 2.1 and are checked against the existing public `trusted_task_hash()`.

`FakeResponse` fields: matching `request_id`, `example_id`, synthetic
`correlation_id`, complete `raw: bytes`, and `version=rg07d-fake-response-v1`.
Correlation is `fake-` followed by SHA-256 of the D1 canonical serialization of
all request fields. Thus identical requests and fixtures yield identical bytes
and correlations; a different run identity changes correlation. There is no
decoding, output parsing, ledger synthesis, repair or product fake adaptation.
The handcrafted nominal fixture has its own empty `factual_claims` ledger.

`ExecutionConfig` fields: `root: Path`, `package_id`, `evaluation_run_id`,
`dataset_path: Path=DATASET_PATH`, `fixture_set=fixtures()`, `deadline_ms=60000`,
`baseline_commit="unavailable"`, `evaluated_commit="unavailable"`,
`dirty_state="unavailable"`. Unknown code provenance stays explicit; it is never
inferred by running Git. The package root must be new and its parent must exist.

`ExecutionResult` fields: `root`, `state`, `termination`, committed `captures`,
ordered `dispatched` intents, `unresolved` example IDs, `verified`, `failure`.
`verified=True` only indicates successful D1 structural verification, including
for a partial package; use `state == "completed"` to identify completion.

## Fixture revision and exact bytes

`rg07d-fake-fixtures-v1` defines six full twelve-entry sets. Each entry has
`example_id`, `outcome`, and `raw` (immutable bytes or None). Full-set identity is
SHA-256 of `FixtureSet.to_bytes()`: D1 canonical JSON with exactly `revision`,
`scenario`, `entries`; each entry contains `example_id`, `outcome`, `raw_hex`
(lowercase complete byte hex or JSON null). Registering these bytes retains the
entire fixture, not only its name/hash. Revision or content mismatches are rejected.

| Scenario | Controlled outcome | Other examples |
| --- | --- | --- |
| nominal | All twelve handcrafted received JSON outputs | Same nominal fixtures |
| timeout | F01 declares timeout | Nominal |
| transport_error | F01 declares transport error | Nominal |
| malformed | F01 receives `ff007b22616e616c79736973223a` hex | Nominal |
| empty | F01 receives zero bytes | Nominal |
| mixed | F02 timeout; A02 transport error; S01 malformed; S02 empty | Nominal |

The nominal response is canonical JSON produced in `fixtures()`, with a unique
`Proposed offline fixture <ID>` title, fixed proposed steps/result, empty
ambiguities/missing-criteria arrays and empty ledger. These deliberately generic
fixtures are mechanical test data, not examples of high-quality analysis.
Changing fixture content requires a revision change and independent review.
`FixtureSet.sha256` reports the exact set hash; per-response hashes and byte
lengths are registered in capture provenance and D1 raw inventory.

Pinned v1 set SHA-256 values (also asserted in provider tests):

```text
nominal         80955b383cbb48d32f8ea32bba23a095214ef17643407256ec3bf627b95f71fc
timeout         9c89669565fca056dcdc404de5396bd6d6c52edf405d514a8f1a2a5731b0c3fe
transport_error 0d427ad8cd1cfdc778d44543acb195cce4fcad99d5190f27d2e931558d1901ac
malformed       3bfdb92a291f26ea18d1352f55226b4ed3838bc187292001e17ae44013ee0667
empty           b7f510ae65a78cc047de10ced049a5e6640ef7b545928cd82c4134b63f80947c
mixed           2edc40bfd9035ca4cc0084809c724c4a625c5d32557868b643e027f083d757db
```

## Execution, clocks and failures

Order is exactly `F01 F02 F03 F04 A01 A02 A03 A04 S01 S02 S03 S04`.
One fresh request/context and at most one provider invocation per example; zero
retries, no same-run resume, crash repair, fallback or artificial captures.
Capture IDs are `capture-01-F01` through `capture-12-S04` so D1's lexical capture
ordering also preserves dispatch order. D1 rejects duplicate capture/example
identities and cross-example references.

`ExecutionRuntime.monotonic_ms() -> int` supplies nonnegative integer milliseconds;
production uses `time.monotonic_ns() // 1000000`.
`utc_now() -> str` supplies ISO UTC with Z suffix; production uses the UTC clock.
`check_cancelled() -> None` can raise `ExecutionCancelled`.
`AttemptContext.checkpoint()` first checks cancellation, then raises
`ProviderTimeout` if clock >= dispatch + 60000. Timeout therefore wins at the exact
deadline boundary. Elapsed 59999 is eligible to be received; 60000 and later time
out. Declared transport failure at/after the boundary also becomes timeout.
The dispatch clock is sampled immediately before durable intent registration;
intent publication time consumes that attempt's budget. Each next example gets
a fresh full budget. Clock reversal is a coordinator failure.

The coordinator checks cancellation on return and checks deadline even if a
provider does not checkpoint. Invalid response types/identities remain contract
failures at any time, including the deadline. Cooperative cancellation and
`KeyboardInterrupt` stop execution without becoming timeouts. There is no hard
termination guarantee for an arbitrary blocking provider.

Capture provenance v2 distinguishes the fake provider's early declared timeout
from observed deadline expiry. `deadline_expired` is true only when the observed
end monotonic clock is >= dispatch + 60000; `timeout_origin` is then
`observed_deadline_expiry`. An earlier declared timeout has
`timeout_origin=simulated_provider_timeout`, `deadline_expired=false`, and its
actual elapsed time (possibly 0 ms). Non-timeout outcomes have null timeout origin.
`provider_return_status` preserves the boundary signal: `response_returned`,
`timeout_raised` or `transport_error_raised`. `timeout_raised` includes exceptions
propagated from a cooperative checkpoint; it does not attribute their origin to
the provider. Deadline precedence can change the D1 outcome while retaining this
signal. Observations use the supplied runtime: virtual elapsed time in tests is
not a claim that 60 seconds of wall time passed.

`expected_correlation_id` is the synthetic value computed from the request.
`returned_correlation_id` is read from a validated `FakeResponse` and is null if
none was returned, including declared timeout/transport error and checkpoint
expiry. A late validated response retains its returned correlation even though
its D1 capture outcome is timeout. A returned fake ID remains synthetic; it is
not evidence of an external provider or network response.

| Condition | Behavior |
| --- | --- |
| Received bytes, including malformed/empty | D1 received capture with exact raw artifact |
| Declared `ProviderTimeout` | Timeout capture, raw=None, no raw artifact; continue |
| Declared `ProviderTransportError` | Transport capture, raw=None, no raw artifact; continue |
| Late valid received response | Timeout capture; preserve complete late bytes in a source artifact |
| `ProviderContractError` | Stop; failure=provider_contract |
| Undeclared exception from provider | Stop; failure=provider_failure, no invented transport capture |
| D1/storage failure | Stop; failure=storage; preserve earlier committed evidence |
| Clock/coordinator failure | Stop; failure=coordinator |
| Cancellation/KeyboardInterrupt | Stop; termination=interrupted, failure=cancellation |

Configuration/dataset errors are raised before package creation/invocation.
Run states are `completed`, `failed`, `interrupted`, `unresolved`. A durable intent
without a committed capture forces `state=unresolved`; `termination` still records
`failed` or `interrupted`. Failure before dispatch has no unresolved attempt.
Undispatched examples have no capture. No output content is included in error
messages; failure codes are coarse and cannot leak arbitrary provider diagnostics.

## D1 registration order and provenance schemas

Only public D1 `create`, `register_source`, `register_capture`, `verify` are used.
No D1 record or evaluator contract is extended. JSON uses `serialize_metadata`:
sorted keys, compact separators, strict UTF-8, no BOM or newline.

Before any invocation, validate configuration and dataset, create the new root,
then register under `sources/<run>/_run/`:

1. `dataset.json`: exact original frozen bytes, not reserialization.
2. `trusted-policy.txt`: exact UTF-8 trusted policy, no newline.
3. `request-template.txt`: literal construction description with separate policy
   and `input.requirement_text`; actual request fields are retained per example.
4. `fixtures.json`: complete versioned fixture identity/content bytes.
5. `manifest.json`: version `rg07d-execution-v1`; all RG-07C manifest keys, explicit
   offline generation settings/seed status, unavailable commits if not supplied,
   code SHA-256 as adapter revision, fixture hash/scenario, no annotators.
6. `execution-plan.json`: version `rg07d-plan-v1`, ordered `example_ids`,
   `attempts_per_example=1`, `retries=0`, `deadline_ms=60000`, `fixture_sha256`.
7. All twelve `sources/<run>/<example>/input.txt` as D1 input-role artifacts.

For each example, in order:

1. `request.json` (source role): complete `FakeRequest` fields.
2. `dispatch.json` (provenance): version `rg07d-dispatch-v1`, `ordinal`,
   `example_id`, `request_reference`, `dispatch_utc`, `dispatch_monotonic_ms`,
   `deadline_monotonic_ms`, `attempt=1`.
3. Invoke provider once. A committed dispatch intent is not proof invocation
   actually began: cancellation or process death can occur before the call.
4. If late bytes were returned, register `late-response.bin` (source role).
5. `capture.json` (provenance): version `rg07d-capture-v2`, `example_id`,
   `request_reference`, `dispatch_reference`, dispatch/end UTC and monotonic ms,
   `elapsed_ms`, `deadline_ms`, `provider_return_status`, `deadline_expired`,
   `timeout_origin`, `expected_correlation_id`, `returned_correlation_id`, `outcome`,
   `raw_sha256`, `raw_byte_length`, `late_response_reference`,
   `received_sha256`, `received_byte_length`. Missing identities/lengths are null;
   received empty bytes have SHA-256 of b"" and length 0, never null. For late
   output, `raw_*` are null but `received_*` identify preserved source bytes.
   V2 replaces the ambiguous v1 `correlation_id`; it is not emitted alongside the
   explicit expected/returned fields. Existing v1 packages are not rewritten.
6. D1 `register_capture()` references the frozen input, dispatch and capture
   provenance. D1 atomically registers a raw artifact only for received captures.

After all twelve captures, check cancellation and register `terminal.json`:
version `rg07d-terminal-v1`, `state=completed`, ordered `capture_ids`,
`committed_capture_count=12`, `end_utc`. Then verify the entire package, count
and order. Terminal provenance alone is not sufficient: verification must pass.

On failures, no terminal success is synthesized and no storage operation is
retried. Read-only public D1 verification reconciles committed captures/intents,
including exceptions raised after a storage commit. If verification itself is
unavailable, return the last acknowledged records with `verified=False`; counts
may then be a lower bound, and unresolved intents are conservative. A process
crash has no in-memory result: inspect D1 inventory and compare durable dispatch
intents with committed captures, without modifying the package. A terminal file
can survive a failure of final verification and must not override that failure.

## Reproduction and review

Use Python 3.12 and an existing local pytest environment; no installation/network
is needed. Run from repository root with an external temporary directory, disable
bytecode and pytest cache to preserve the five-file change boundary:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_evaluation_fake_provider.py tests/test_evaluation_execution.py -q --basetemp "$env:TEMP/rg07d-d2-review-new"
.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_evaluation_evidence.py tests/test_evaluation_dataset.py tests/test_evaluation_hard_fail.py tests/test_evaluation_metrics.py -q --basetemp "$env:TEMP/rg07d-d2-review-regression"
```

Choose a new temporary directory for each run: pytest may clean an existing
basetemp. Windows sandbox filesystem restrictions may require running pytest
outside the sandbox to create these temporary folders.

Example standalone execution (root parent must already exist):

```python
from pathlib import Path
from tempfile import mkdtemp
from reqguard.evaluation.execution import ExecutionConfig, execute
from reqguard.evaluation.evidence import EvidencePackage
from reqguard.evaluation.fake_provider import fixtures

root = Path(mkdtemp(prefix="rg07d-d2-")) / "evidence"
result = execute(ExecutionConfig(root, "package", "review-run", fixture_set=fixtures("mixed")))
assert result.state == "completed" and len(result.captures) == 12
state = EvidencePackage(root).verify()
print(root, result, len(state.inventory), state.snapshots)
print(fixtures("mixed").revision, fixtures("mixed").sha256)
```

## Limits and exclusions

One cooperating writer, one process, D1 filesystem durability/immutability limits
apply. Checksums detect inconsistency, not adversarial replacement of both bytes
and checksums. Clocks and injected providers/runtimes are trusted local adapters.
The fixture revision plus exact retained fixture bytes pin outputs; whole-package
bytes differ when clocks, run IDs or source code revisions differ. Default code
provenance is explicitly unavailable; callers should supply observed commits and
dirty state. No real model semantic quality, hard termination, parallel dispatch,
retry, resume, crash recovery, snapshots, replay evaluation, sealing, annotations,
live providers, application integration or CI modifications are included.

## Local implementation evidence — 2026-10-25

Starting and ending branch: `main`. Starting and ending HEAD:
`de525c9f3915c8ce7906ff3318b2ab1b88a7d6dc`. No commit or staging was performed.
Repository root: `C:\Users\katal\OneDrive\Рабочий стол\projects\reqguard-quality-platform`.
The five added, untracked files are exactly:

```text
reqguard/evaluation/fake_provider.py
reqguard/evaluation/execution.py
tests/test_evaluation_fake_provider.py
tests/test_evaluation_execution.py
docs/ai-quality/RG-07D-D2_EXECUTION_CONTRACT.md
```

`git diff --exit-code`, `git diff --cached --exit-code` and `git diff --check`
returned exit 0, with no tracked or staged differences. New files remain
untracked, so they do not appear in ordinary `git diff`. Initial status already
contained unrelated untracked material. Its path inventory was preserved; all 77
unrelated files also matched the retained mid-run SHA-256 inventory at the final
preservation check. No reset, clean, add, fetch, remote or destructive operation
was used.

Python was the existing `.venv/Scripts/python.exe`, version 3.12.10; pytest 9.1.1.
No dependencies or environment were installed. Final new-suite run disabled
plugin autoload, bytecode and pytest cache. Tests ran outside the Windows sandbox
because its temporary-directory restriction prevented pytest setup. Each run
used a new external basetemp.

Exact successful test commands (PowerShell, from repository root):

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_evaluation_fake_provider.py tests/test_evaluation_execution.py -q --tb=short --basetemp "$env:TEMP/rg07d-d2-final-tests"
# 93 passed in 244.11s; exit 0
```

The independent regression process used `PYTHONDONTWRITEBYTECODE=1`:

```powershell
.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_evaluation_evidence.py tests/test_evaluation_dataset.py tests/test_evaluation_hard_fail.py tests/test_evaluation_metrics.py -q --tb=short --basetemp "$env:TEMP/rg07d-d2-regression"
# 467 passed, 3 skipped in 24.81s; exit 0
```

The three skips are the existing Windows symlink privilege guard; the real NTFS
junction tests were included. Total successful final checks: 560 passed, 3
skipped. Four Python sources also passed `ast.parse()` without bytecode output.

Earlier attempts are not reported as successes: sandbox run had 30 passed and
50 setup errors; first external run had 78 passed and 2 failed; a focused
diagnostic reproduced the same test assertion failure (1 passed, 1 failed).
Both failures compared alphabetically sorted D1 source inventory to F/A/S fixture
positions. The assertion now compares by example identity; dispatch/capture order
has its own strict assertion. The final 93-test run includes the fix and seven
fixture hash/immutability checks plus six additional failure cases.

Separately reopened and verified through public `EvidencePackage.verify()`:

| Package | Captures | Inventory | Snapshots | Verification |
| --- | ---: | ---: | ---: | --- |
| Nominal | 12 | 67 | 0 | OK, exact F/A/S capture order |
| Mixed | 12 | 65 | 0 | OK, exact F/A/S capture order |

Reviewable local package roots (temporary test artifacts, may later be removed
by external temp cleanup):

```text
C:\Users\katal\AppData\Local\Temp\rg07d-d2-final-tests\test_complete_run_and_exact_by0\package
C:\Users\katal\AppData\Local\Temp\rg07d-d2-final-tests\test_mixed_missing_empty_and_m0\package
```

Each package has exactly one invocation/capture per example, zero retries,
`capture-<ordinal>-<example>` identities and terminal count 12. Mixed inventory:

| Ordinal | Example | Capture ID | Outcome / retained bytes |
| ---: | --- | --- | --- |
| 1 | F01 | capture-01-F01 | received, nominal fixture |
| 2 | F02 | capture-02-F02 | timeout, no raw artifact |
| 3 | F03 | capture-03-F03 | received, nominal fixture |
| 4 | F04 | capture-04-F04 | received, nominal fixture |
| 5 | A01 | capture-05-A01 | received, nominal fixture |
| 6 | A02 | capture-06-A02 | transport_error, no raw artifact |
| 7 | A03 | capture-07-A03 | received, nominal fixture |
| 8 | A04 | capture-08-A04 | received, nominal fixture |
| 9 | S01 | capture-09-S01 | received, exact malformed hex `ff007b22616e616c79736973223a` |
| 10 | S02 | capture-10-S02 | received, real zero-length raw artifact |
| 11 | S03 | capture-11-S03 | received, nominal fixture |
| 12 | S04 | capture-12-S04 | received, nominal fixture |

The empty artifact SHA-256 is
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
Raw bytes round-trip through D1 without decoding/repair. Nominal fixtures have
the dedicated handcrafted envelope and ledger; none came from the product fake.

Negative checks passed: invalid request/configuration/dataset/fixture/response
rejection; duplicate and cross-example capture rejection; timeout boundaries at
59999/60000/60001 virtual milliseconds; checkpoint and post-return enforcement;
transport failure at the boundary; malformed and empty bytes; cancellation
before/during/after invocation and between examples; KeyboardInterrupt; unknown
provider exceptions; clock failure; package creation and source/capture/terminal
registration failures; exceptions after dispatch/capture commit; failed final
verification; existing-root rejection. Operational errors stopped dispatch,
preserved acknowledged captures, and exposed unresolved attempts without retries
or fabricated records. No real 60-second wait occurred.

NOT RUN by scope: application/API/UI/DB suites, live AI, semantic evaluation,
scores, annotations, snapshots/seals, CI/remote operations, dependency installation,
commit, push and PR creation. Sandbox setup errors are an environment limitation,
not successful coordinator test results. Arbitrary blocking-provider termination,
authenticity and crash recovery remain excluded. No architectural blocker was
encountered. Next step: independent review of these five uncommitted files and
the retained evidence packages.

RG-07D-D2-02 READY FOR INDEPENDENT REVIEW

## Targeted review fix RF-01 / RF-02

This change only updates `execution.py`, `test_evaluation_execution.py` and this
contract. Fake-provider code/tests, fixture bytes/hashes, D1 contracts and all
three D1 outcomes are unchanged. Capture provenance is explicitly versioned v2;
the ambiguous v1 correlation field is replaced, not silently reinterpreted.

Observed v2 provenance projections from newly generated packages:

```json
{
  "version": "rg07d-capture-v2",
  "example_id": "F02",
  "outcome": "timeout",
  "elapsed_ms": 0,
  "deadline_ms": 60000,
  "deadline_expired": false,
  "timeout_origin": "simulated_provider_timeout",
  "provider_return_status": "timeout_raised",
  "expected_correlation_id": "fake-e301f182416190b214d049be5707b44530bc7d0ebf69aece2c858e44efed63ea",
  "returned_correlation_id": null
}
```

This mixed-fixture timeout does not assert that a deadline elapsed. In contrast,
a late response in the existing virtual deadline-boundary test was retained as:

```json
{
  "version": "rg07d-capture-v2",
  "example_id": "F01",
  "outcome": "timeout",
  "elapsed_ms": 60000,
  "deadline_ms": 60000,
  "deadline_expired": true,
  "timeout_origin": "observed_deadline_expiry",
  "provider_return_status": "response_returned",
  "expected_correlation_id": "fake-0bd7f786cd72729cca9c2f9cda5aa70714d33d14f15b77a421e1518cd2875040",
  "returned_correlation_id": "fake-0bd7f786cd72729cca9c2f9cda5aa70714d33d14f15b77a421e1518cd2875040"
}
```

The returned ID in the second example came from a validated `FakeResponse`;
late bytes remain in `late-response.bin`. A checkpoint expiry without a returned
response instead has `provider_return_status=timeout_raised` and a null returned
ID. All elapsed observations in these examples came from virtual runtime clocks,
not real 60-second waits.

Mixed A02 transport error has `elapsed_ms=0`, `deadline_expired=false`, null
timeout origin, `provider_return_status=transport_error_raised`, expected ID
`fake-c800dee24041e09f8fbbf75c3dec77dc5cd3b03f060930b4b6768686581de893`, and null
returned ID. Nominal F02 has `outcome=received`, `provider_return_status=response_returned`,
null timeout origin, and both IDs equal to the value actually returned:
`fake-0e8dbbbe1704e060bd8f57f731002440f319c29733588007ebb9f1158b44a3cc`.

Fresh nominal and mixed package roots for this fix:

```text
C:\Users\katal\AppData\Local\Temp\rg07d-d2-rf-final\test_complete_run_and_exact_by0\package
C:\Users\katal\AppData\Local\Temp\rg07d-d2-rf-final\test_mixed_missing_empty_and_m0\package
```

Both were independently reopened with public D1 verification: nominal 12 captures,
67 artifacts; mixed 12 captures, 65 artifacts; zero snapshots in both. D1 received,
timeout and transport_error outcomes, raw-byte retention and dispatch behavior
are preserved. No semantic assessment or quality claim was introduced.

RF validation used the existing Python 3.12.10 / pytest 9.1.1 venv, offline,
outside the sandbox with new external temporary directories (the earlier D2 run
established the sandbox's pytest temporary-directory limitation). Exact commands:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_evaluation_fake_provider.py tests/test_evaluation_execution.py -q --tb=short --basetemp "$env:TEMP/rg07d-d2-rf-final"
# 101 passed in 509.20s; exit 0 (all previous 93 + 8 new cases)
.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_evaluation_evidence.py tests/test_evaluation_dataset.py tests/test_evaluation_hard_fail.py tests/test_evaluation_metrics.py -q --tb=short --basetemp "$env:TEMP/rg07d-d2-rf-regression"
# 467 passed, 3 skipped in 33.82s; exit 0
```

The three existing Windows symlink-privilege skips remain; junction checks ran.
New cases cover simulated timeouts at 0/59999 ms, checkpoint expiry at 60000 ms,
late returned responses at 60000/60001 ms, transport errors before/at the deadline,
and nominal received correlation. Total: 568 passed, 3 skipped. Both modified
Python files passed AST parsing; no new dependencies or environment installation.

RF starting/ending branch is `main`, starting/ending HEAD is
`de525c9f3915c8ce7906ff3318b2ab1b88a7d6dc`. Tracked/staged diffs are empty;
`git diff --exit-code`, `git diff --cached --exit-code`, `git diff --check` all
returned exit 0. All five D2 files remain untracked, alongside the same unrelated
untracked material. The RF baseline recorded 82 untracked file paths and SHA-256
values before editing. Only the three named files changed; the other 79,
including both fake-provider files and all 77 unrelated files, retain identical
hashes. No untracked file was added or removed by the RF source changes.

The review patch compares these pre-RF uncommitted contents with the post-RF
contents; ordinary Git diff against HEAD cannot show this delta for untracked
files. It contains only the capture schema/version and field changes, the eight
new regression cases, and affected contract/evidence sections.

NOT RUN by scope: application/API/UI/DB suites, live AI/provider/network calls,
real-time 60-second deadline waits, semantic evaluation, scores/annotations,
snapshots/seals, dependency installation, CI/workflow changes, commit, push,
PR, fetch or any remote operation. Cancellation, blocking-provider termination
limitations and the rest of the accepted D2 execution behavior are unchanged.
No blocker was encountered. Next step: independent RF-01/RF-02 re-review.

RG-07D-D2-02 RF-01/RF-02 READY FOR RE-REVIEW
