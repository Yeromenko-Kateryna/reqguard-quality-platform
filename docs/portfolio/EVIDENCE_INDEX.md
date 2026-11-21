# Portfolio execution evidence — accepted post-merge index

Documentation candidate prepared 21 November 2026; not published. Source reference
`4640729a9662ef76922f6b22243edb41db65d486`, tree `92b592c05753f839a390dd0bfeedbf6916a210a7`. The evidence is accepted historical execution,
not newly run tests or a statement about current remote main/resources. Follow the
[requirements/risk matrix](TRACEABILITY_MATRIX.md) for the tests behind each claim.

<a id="accepted-post-merge-evidence"></a>
## Accepted post-merge evidence

Quick inspection: choose B01 in the matrix, open its pinned test, follow P01 to the
Actions run, then inspect `supported-sql.json` and `sql-cleanup.json` in the retained
artifact. A GitHub green conclusion alone does not prove row correlation or cleanup.

All three runs below are Ubuntu `push(main)`, attempt 1, at the source commit above.
Workflows: [Chromium/API/PostgreSQL](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/.github/workflows/rg06d-e2e.yml),
[frontend contracts](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/.github/workflows/rg-ui-contracts.yml),
[offline evaluator](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/.github/workflows/rg07c-evaluator.yml).

<a id="p01"></a>
### P01 — Chromium → HTTP → PostgreSQL and owned cleanup

- [Accepted RG-06D run 44945635070](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/44945635070/attempts/1): three executed tests, 3 PASS, zero skipped/flaky/unexpected, no retries. Exact test titles are in the post-merge matrix and [bound browser source](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/quality/browser/analyses.spec.ts).
- [Artifact 14723516150](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/44945635070/artifacts/14723516150), `rg06d-44945635070-1`, original uploaded ZIP 26,915 bytes; SHA-256 `ece541bfc869d215dea3600341c892f45599376c63cc6c41de38d34f86e9ffe8`. Access can require authentication; current hosted retention/download availability was not rechecked. Owner-retained exact original is identified below.
- `launch.json` binds the source, run, attempt and 25 runtime inputs. `results.json` records the passing B01–B03 identities. Harness run: `a660ed685e954b4193662f8a6e122adb`.
- `supported-sql.json` contains response and independent committed-row correlation: `run_id=470d7a45-4d60-40bf-a94a-e3e75d273d4b`, input `The user can quickly reset their password`, provider `fake`, status `completed`, complete analysis-payload equality. HTTP 200 is asserted by the passing browser test; the SQL receipt is not assigned an invented HTTP-status field.
- `invalid-sql.json`: actual status 422, noDelta true and equal SQL snapshots. `unsupported-sql.json`: original input preserved, unsupported response, independent SQL NULL row. See B02/B03 for exact assertions.
- `supported-cleanup.json`, `unsupported-cleanup.json` and `sql-cleanup.json`: owned rows absent, sentinel preserved, CLEANED, uncertainty false. `run-summary.json`: assertions PASS, SQL cleanup VERIFIED and descendantsExited true. This is retained CI evidence, not a fresh SQL read or independent Docker inspect after job disposal. Service disposal is `GITHUB_MANAGED_NOT_ATTESTED_BY_HARNESS`.

Selected original artifact-member SHA-256 values (root names within the RG-06D ZIP):

| Receipt | SHA-256 |
|---|---|
| `launch.json` | `53dbaf776943b24374cdce1d6bc3893e38c2bfdc1347025b22d87e6f9d4f5b0d` |
| `results.json` | `567d837fccc8128883b507daa3461eb98279f9ecf5627482eef0f600281d57cd` |
| `supported-sql.json` | `1833d821ef5f9a17919a7d15e24850e0545a27bb2deea47430abe21c50a4067f` |
| `invalid-sql.json` | `d31c45bfdedb71ab4a0fc4f6a314d35cee5875981ffed329a0d4e1bf60851179` |
| `unsupported-sql.json` | `8771f2cb5f0f1acb74525374b5b13e624c593e9ae96f9aef338a8f4841ba16e4` |
| `supported-cleanup.json` | `2d4e71e21f3604589eb537263bc061c26f4eddd2963a4db369b46026c0b8d710` |
| `unsupported-cleanup.json` | `2d4e71e21f3604589eb537263bc061c26f4eddd2963a4db369b46026c0b8d710` |
| `sql-cleanup.json` | `f9a94a76c00123ee9bed40d53e3d1f1de3a699e4dcb1eb0157002a0e42b9405d` |
| `run-summary.json` | `da4349f268b5f7af4693b9915d59d5e7b9b53e5ee498ea53d284a1b8a3c97394` |
| `publication-context.json` | `87e2d1f08ca90c54c6bba23f952726763b9700998c1f6aaf13b7561ca0f854c1` |
| `publication-manifest.json` | `ba5ec35e0d9529b49925a4bce514206caf79a2c303d9588c3941cf77a1a57d33` |

### Publication privacy boundary

The [source-bound publisher and regression module](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/scripts/run_rg06d_ci.py) / [tests](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/scripts/test_rg06d_admission.py) and P01's `results.json`, `publication-context.json` and `publication-manifest.json` support the accepted scoped privacy result: known Git metadata structures and inspected uploaded member bytes. `config.metadata`, `config.projects[0].metadata` and `config.filteredProjects[0].metadata` exclude the identified personal Git metadata while safe commit hashes remain. Accepted component evidence also identifies `EvidenceTests.test_publication_revalidates_copied_bundle` and `NetworkV3Tests.test_M10_raw_safe_v3_publication` as executed PASS; see `RG06D-COMPONENT-RESULTS.md` in the retained handoff. This is not universal free-text PII detection or hostile-runtime containment. The raw pre-sanitization report was not retained; a producer-recorded raw digest does not substitute for those missing original bytes. The earlier workflow_dispatch AdmissionError's exact predicate remains UNKNOWN; later push success does not diagnose it.

<a id="p02"></a>
### P02 — Frontend contracts, separate from browser E2E

- [Accepted frontend run 44945635046](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/44945635046/attempts/1); [test module](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/tests/ui.test.mjs) and [identity-enforcing workflow](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/.github/workflows/rg-ui-contracts.yml). Eleven executed DOM-adapter tests PASS, zero failures/errors/skips; test exit 0.
- [Artifact 14723585786](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/44945635046/artifacts/14723585786), `rg-ui-contracts-44945635046-1`, 3,225 bytes; ZIP SHA-256 `402da9144c2d8b541a89d8828e641cac563cbbcc1e3da39ffc40551080743427`. Same hosted-access/retention qualification as P01.
- Root receipts: `ui-contracts.xml`, `ui-contracts.exit`, `ui-contracts-validation.json`, `ui-contracts-evidence.json`; logs and Node version accompany them. These are not Chromium cases or a live database-failure experiment.

Exact JUnit case names (not new tests):

- `POST uses the same-origin JSON API and preserves the original text`
- `unsupported_fixture remains a distinct valid result without analysis`
- `422 preserves readable validation details without emitting success`
- `HTTP 503 never produces a successful result or retries`
- `HTTP 500 never produces a successful result or retries`
- `network failure reports an uncertain outcome and performs no retry`
- `unreadable successful response is not misreported as a network error or success`
- `malformed analysis is rejected before DOM rendering`
- `rendered results use text nodes for every API field, including markup`
- `loading disables duplicate submission and hides the previous result; 422 clears success`
- `unsupported result replaces completed analysis instead of retaining stale content`

<a id="p03"></a>
### P03 — Deterministic offline AI Quality

[Accepted offline run 44945635146](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/44945635146/attempts/1) and [workflow](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/.github/workflows/rg07c-evaluator.yml) bind the following mechanical checks:

- Dataset, hard-fail and metrics: 297 PASS, no failures/errors/skips, under the workflow's Python 3.13.1 / Unicode 15.1.0 gate. Exact test identities are in the retained verbose suite log and the [dataset](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/tests/test_evaluation_dataset.py), [hard-fail](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/tests/test_evaluation_hard_fail.py) and [metrics](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/tests/test_evaluation_metrics.py) source suites.
- Separate [evidence-integrity suite](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/tests/test_evaluation_evidence.py): 173 collected, 171 PASS, two expected NTFS-only skips on Linux. No Windows coverage is inferred from those skips.
- Separate [fake-provider suite](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/tests/test_evaluation_fake_provider.py) and [execution suite](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/tests/test_evaluation_execution.py): 101 PASS combined. This tests execution/evidence mechanics, not model semantics.

The accepted offline workflow publishes no downloadable artifact. Evidence is its
retained suite/gate log excerpts in the owner-held merge handoff, with original
and review hashes/transformation notes in `primary/LOG-PROVENANCE.json`.
Do not invent an evaluator artifact URL or treat these checks as authentic live-model
outputs, human-labelled semantic quality or production AI safety.

### Retained evidence custody and access

The owner-held `RG_PORT_MVP_PR7_CONTROLLED_MERGE_01_REVIEW_HANDOFF.zip` has SHA-256
`22ac8c9c132151793e5310b3c4c3702979d283fa78c1c7646683b68f0d693c62`.
It is a private review handoff, not promised in a public repository clone. To inspect
the original published CI payloads after expiry, request this exact handoff from
the owner, verify its SHA-256/manifest, then use:

- `primary/artifact-14723516150.zip` and `primary/artifact-14723585786.zip`: byte-identical original uploaded ZIPs with the receipt roots listed above.
- `E2E-HTTP-SQL-CLEANUP.md`, `AUTOMATIC-POSTMERGE-CI.md` and `PLAYWRIGHT-PRIVACY-VERIFICATION.md`: accepted review interpretations, distinguishable from primary receipts.
- `primary/logs/44945635146/` and `primary/LOG-PROVENANCE.json`: retained evaluator log evidence; selected log derivatives have explicit original/review hashes and redaction notes. They are not asserted to be unmodified raw logs.

These paths are archive-relative locators, not public filesystem paths or links to
files claimed to be present in this candidate. No raw private evidence is embedded
in these documents. Checksums establish byte integrity, not independent capture
authenticity. Links below in the historical D1 material keep their historical
availability statements; none is a new assurance of current hosted retention.

<a id="current-limits"></a>
## Current platform, security and release limits

Windows README literal reproduction remains **BLOCKED**; accepted Ubuntu CI is not
Windows verification. The [accepted-source README](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/README.md) retains its
commands, public-review STOP and D–J restrictions. The private Docker-config proposal
is not adopted or implemented; no workaround, installation or execution is authorized.
Windows R2.3 is separate qualified manual evidence at
`59b465ee758b1a46495e1e098bc1182f209cc3f9` (historical E04 below). Its SQL is
conversation-captured, not independently captured SQL stdout; original API JSON is
missing. Do not relabel it automated E2E, CI or literal reproduction of accepted main.

RG05=BLOCKED; G05=DEFERRED BY OWNER / NOT SATISFIED;
PRELAUNCH_DECISION=REFUSE; STAGE_B=NOT_AUTHORIZED; RELEASE=NOT_AUTHORIZED.
Runtime safety D–J and public-review provenance remain open. No Portfolio V1 release,
production readiness, live-model semantic quality, universal privacy or new technical
acceptance is claimed. This is evidence navigation, not a replacement runbook.

## Historical D1 index — retained verbatim

The original 18 November candidate follows unchanged, including its old review
labels, executions, hashes and time-specific access observations. Its a4e74599…
source reference and Windows evidence are separate from P01–P03, not updated by
substituting newer commit IDs. Current candidate and limits are stated above.

# Portfolio MVP execution evidence index

Status: **IMPLEMENTED / PENDING RG-00 REVIEW**. Prepared 18 November 2026.

Documentation source reference: commit `a4e74599a047f2db251d8e951e0b53718be97b92`, tree `9048ba478194460d11b4f4456899357d713fc683`.
All source links below pin that commit. These new documents are local candidates,
not files claimed to exist in that historical commit. They were authored in a
separate local checkout at `834d9246c49b0730594602cb3241e599c42e5428`; its PORT-02 changes and untracked RG05/demo
work are not adopted as the documentation source.

The owner's documentation-reference instruction authorizes these two files only.
The A0 assessment is an evidence source, not a release approval or canonical-state
update. Requirement/risk IDs below are documentation aliases for existing behavior
and risks; they do not add or relax frozen acceptance criteria.

This index distinguishes source identity, execution evidence and review authority.
Source hashes prove bytes, not safety or approval. Review archive identifiers below
are owner-retained private evidence references, not files promised in a public clone.
A reviewer needs access to retained originals to repeat content checks. No user
paths, credentials or raw environment dumps are published here.

## Evidence summary

| ID | Evidence class | Execution revision | Scope |
|---|---|---|---|
| [E01](#e01) | Retained primary CI artifact, hashes/content rechecked | `a4e74599a047f2db251d8e951e0b53718be97b92` | Ubuntu Chromium → real HTTP → independent PostgreSQL; three cases |
| [E02](#e02) | Retained primary JUnit/receipts in portable archive | `a4e74599a047f2db251d8e951e0b53718be97b92` | Eleven Node DOM-adapter contracts; not browser E2E |
| [E03](#e03) | Historical successful CI metadata and pinned source; payload recount unavailable | `a4e74599a047f2db251d8e951e0b53718be97b92` | Deterministic offline AI Quality; product Python suites separately source-only |
| [E04](#e04) | Accepted qualified manual Windows evidence | `59b465ee758b1a46495e1e098bc1182f209cc3f9` | Separate R2.3 UI/SQL correlation; missing raw evidence remains explicit |
| [E05](#e05) | Historical accepted index / A0 and scope provenance | Multiple, identified below | Supporting history/governance; not a new execution |

<a id="e01"></a>
## E01 — Chromium, HTTP and PostgreSQL

- [Run 42512944333, attempt 2](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/42512944333/attempts/2),
  historical start **2026-11-16T10:04:36Z**. Current read-only metadata was observed
  on 18 November 2026: completed/success. This task did not trigger a run.
- Source commit `a4e74599a047f2db251d8e951e0b53718be97b92`; tree `9048ba478194460d11b4f4456899357d713fc683`.
- [Workflow](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/.github/workflows/rg06d-e2e.yml),
  [Browser cases](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/quality/browser/analyses.spec.ts), [Harness](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/scripts/run_rg06d_ci.py),
  [Owned-data cleanup](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/quality/browser/owned-cleanup.ts),
  [Schema](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/db/001_init.sql). Runtime is Linux hosted CI, pinned PostgreSQL
  image digest and locked dependencies; source platform checks are not new setup proof.
- Artifact **14214303888**, name `rg06d-42512944333-2`:
  [API metadata](https://api.github.com/repos/Yeromenko-Kateryna/reqguard-quality-platform/actions/artifacts/14214303888) and
  [run artifact page](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/42512944333#artifacts).
  GitHub metadata currently lists it as not expired, expiry **2026-11-23T10:05:52Z**.
  Availability may change; an Actions download can require authentication.
- Retained original: `RG00_MVP_RG06D_BASELINE_EXECUTION_01_20261116T100304323303Z_ARTIFACT_14214303888.zip`; 27,151 bytes; SHA-256
  `ce5e10c41ec41e469f5ce07a78065d5689632e1cdefd6d6d6902bdb2551623c8`. It is owner-held, not committed by this documentation task.
- Rechecked: ZIP CRC, 28 unique members and all 27 manifest payload sizes/hashes.
  `launch.json` (SHA-256 `124a06d51ed880147041f18cfc2af9208dae7cb95bd1d389bf9673bc6fbf0eb3`) binds commit/run/attempt and **25/25**
  runtime-input hashes to blob-verified bytes of the approved source tree.

| Case ID | Exact title | Pinned source |
|---|---|---|
| B01 | `supported fixture: browser HTTP 200, visible result, independent committed SQL row` | [`B01`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/quality/browser/analyses.spec.ts#L155) |
| B02 | `invalid whitespace: actual FastAPI HTTP 422 and unchanged SQL snapshot` | [`B02`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/quality/browser/analyses.spec.ts#L202) |
| B03 | `unsupported fixture: browser HTTP 200, visible unsupported result, independent SQL NULL row` | [`B03`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/quality/browser/analyses.spec.ts#L233) |

`results.json` and `run-summary.json` record three expected passes, zero
unexpected/skipped/flaky results. `supported-sql.json` correlates full response and
committed row by run_id; `unsupported-sql.json` preserves input padding and SQL
NULL; `invalid-sql.json` records HTTP 422 and identical before/after snapshots.
`supported-cleanup.json`, `unsupported-cleanup.json` and `sql-cleanup.json` record
owned cleanup and unchanged sentinel; cleanup state is CLEANED. Process summary
records descendantsExited=true. These are original saved execution receipts, not
fresh queries or an independent proof of every possible Windows/host effect.

`ownership-unit.json` and source admission/preload receipts provide additional
bounded harness evidence. They are not RG05 native/security acceptance. Service
disposal remains `GITHUB_MANAGED_NOT_ATTESTED_BY_HARNESS`; the harness cannot attest
the hosting platform's disposal. Binary screenshots/traces are excluded by the
publication policy. Failure-diagnostic absence on this successful run is not
fabricated as failure-path proof. Full source/member hashes accompany the local
review handoff; no execution data is regenerated.

<a id="e02"></a>
## E02 — Frontend contracts

- [Run 42512944346, attempt 1](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/42512944346/attempts/1),
  historical start **2026-11-08T19:02:06Z**, exact source commit/tree as E01.
  Current metadata reports completed/success; no new execution is claimed.
- [Standalone frontend workflow](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/.github/workflows/rg-ui-contracts.yml) runs [Node test source](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/ui.test.mjs)
  against [Product rendering/request module](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/reqguard/static/app.mjs).
- Original hosted artifact **13630311437** is retained inside
  `RG_UI_CONTRACT_CI_01_MERGE_20261108T185925725101Z_EVIDENCE.zip` (portable package SHA-256 `f83b2583e1667f435126129323c8ce58469b2b72adfba092f94e3f8a3f95a131`).
  Its nested `hosted-artifact-13630311437.zip` SHA-256 is `05e77f796b282eaef69c9757c0d7b01b030173da7417a49275177fd8fe646e05`.
  Current GitHub API artifact listing for the run is empty; no working public
  artifact download is promised. Use the owner-retained original for detailed review.
- Primary members: `hosted-artifact/ui-contracts.xml`, `ui-contracts.exit`,
  `ui-contracts-validation.json`, `ui-contracts-evidence.json` and version/log files.
  JUnit SHA-256: `8fd6c43e01f3f3db60999049d70399eaf7d2c6b99fefce05e0fc639968b682d5`. Original bytes yield **11 exact unique test identities**,
  zero failure/error/skip elements and test exit 0. The evidence receipt's three
  source hashes match the approved tree. No historical bytes were reconstructed.

The IDs N01–N11 are index aliases; titles below are exact execution identities.
Expected identity links point into the immutable workflow contract; the executable
test file includes generated HTTP 503/500 cases.

| Index ID | Exact JUnit identity | Pinned identity contract |
|---|---|---|
| N01 | `422 preserves readable validation details without emitting success` | [Expected identity](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/.github/workflows/rg-ui-contracts.yml#L67) |
| N02 | `HTTP 500 never produces a successful result or retries` | [Expected identity](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/.github/workflows/rg-ui-contracts.yml#L69) |
| N03 | `HTTP 503 never produces a successful result or retries` | [Expected identity](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/.github/workflows/rg-ui-contracts.yml#L68) |
| N04 | `POST uses the same-origin JSON API and preserves the original text` | [Expected identity](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/.github/workflows/rg-ui-contracts.yml#L65) |
| N05 | `loading disables duplicate submission and hides the previous result; 422 clears success` | [Expected identity](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/.github/workflows/rg-ui-contracts.yml#L74) |
| N06 | `malformed analysis is rejected before DOM rendering` | [Expected identity](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/.github/workflows/rg-ui-contracts.yml#L72) |
| N07 | `network failure reports an uncertain outcome and performs no retry` | [Expected identity](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/.github/workflows/rg-ui-contracts.yml#L70) |
| N08 | `rendered results use text nodes for every API field, including markup` | [Expected identity](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/.github/workflows/rg-ui-contracts.yml#L73) |
| N09 | `unreadable successful response is not misreported as a network error or success` | [Expected identity](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/.github/workflows/rg-ui-contracts.yml#L71) |
| N10 | `unsupported result replaces completed analysis instead of retaining stale content` | [Expected identity](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/.github/workflows/rg-ui-contracts.yml#L75) |
| N11 | `unsupported_fixture remains a distinct valid result without analysis` | [Expected identity](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/.github/workflows/rg-ui-contracts.yml#L66) |

These tests exercise a DOM adapter and response seams: safe text rendering,
request mapping, errors/no retry, loading, malformed success and stale state.
They do not launch Chromium or demonstrate a live database failure. The
approved README's statement that there is no standalone frontend workflow is
historically stale. PR #5 is a separate unmerged editorial candidate; this task
does not alter, accept, merge or inherit execution identity from that PR.

<a id="e03"></a>
## E03 — Offline evaluator and source-only Python coverage

[Run 42512944377, attempt 1](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/42512944377/attempts/1) is bound
to `a4e74599a047f2db251d8e951e0b53718be97b92` / `9048ba478194460d11b4f4456899357d713fc683` and began **2026-11-08T19:02:06Z**.
Fresh GET metadata reports completed/success. The [offline workflow](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/.github/workflows/rg07c-evaluator.yml)
defines the 297 evaluator cases, evidence-integrity 171 passes plus two specified
NTFS skips, and 101 fake-execution cases. Those counts describe the workflow and
historical accepted scope. **Original offline stdout/JUnit was not re-opened or
recounted for this index; no retained upload is listed.** Do not label these counts
new independently verified test executions.

Representative exact source cases:

- [`test_loader_rejects_any_unaccepted_bytes_before_parsing`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/test_evaluation_dataset.py#L65)
  — exact dataset identity; [`test_case_forbidden_literals_even_when_quoted`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/test_evaluation_hard_fail.py#L187)
  — mechanical adversarial-marker rule.
- [`test_safety_semantic_gate_independent_of_hard_rules`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/test_evaluation_metrics.py#L352)
  — semantic/rule gate separation; [`test_real_symlink_escape`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/test_evaluation_evidence.py#L156)
  — evidence-path behavior under its tested platform assumptions.
- [`test_fixtures_complete_immutable_and_deterministic`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/test_evaluation_fake_provider.py#L29)
  and [`test_complete_run_and_exact_byte_roundtrip`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/test_evaluation_execution.py#L62)
  — fake-provider/execution mechanics, not live inference quality.

Product Python suites [tests/test_analyses.py](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/test_analyses.py), [tests/test_persistence_unit.py](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/test_persistence_unit.py),
[tests/test_ui.py](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/test_ui.py) and [tests/test_postgres_integration.py](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/test_postgres_integration.py)
exist at the approved source. They are not standalone product-pytest selectors in
the three inspected workflows. TestClient/stub source is not actual network/SQL
execution. No fresh all-suite result or complete current Python coverage is claimed.
Do not run a broad suite from this index: DB/native/platform cases need separately
authorized contexts. This index supplies no runtime command authorization.

<a id="e04"></a>
## E04 — Separate qualified Windows R2.3 manual demo

Execution revision `59b465ee758b1a46495e1e098bc1182f209cc3f9`, tree
`128c1fc05e8fec9adb43a8548698a8c6b39aa8f3`; not hosted main and not a new merge.
Accepted manual scope: fake-provider UI submission and SQL correlation for run
`a148714c-0951-4a18-91f0-48af7ae48b47`, with recorded shutdown exited/exited.
Owner-retained `RG-DEMO-01-R2.3_CONSOLIDATED_FINAL_HANDOFF.zip` SHA-256:
`94b984267a3f132f58570d166e25068b9a4dcc17b9be8dc21b70de8c641b8184`.

Identifiable members include `supplement/ui/completed-result.png`,
`supplement/sql/owner-terminal-transcription.json`, `correlation/cross-check.json`,
`original/sql/verification-record.json`, `original/git/provenance.json`,
`original/docker/app.json`, `original/docker/db.json` and `LIMITATIONS.md`.
The archive integrity/checksums were rechecked. Acceptance is the recorded
qualified manual-review decision, not acceptance newly assigned by this index.

**Original API response JSON and independently captured SQL stdout are missing.**
SQL transcription is conversation-captured evidence. Recorded Docker states are
historical receipts, not current resource inspection. This is neither Playwright
E2E nor CI and does not verify the approved main's Windows reproduction guide.
No public artifact URL is fabricated; the original is private retained evidence.

<a id="e05"></a>
## E05 — Historical and authority references

[PORT-01-R1 index](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/docs/evidence/PORT-01-R1_MANUAL_RUNTIME_CLOSURE_2026-10-26.md)
records a separate manual Codespace scenario at
`ce72c5bb6f35b1935bb0c3dee1fa15b1b1aef40a`, with private original files and
operator-receipt provenance limits. Those seven original files were not newly
read for this index. Do not transfer their acceptance to another source/platform.

Owner-retained A0 review package
`RG_PORT_MVP_BASELINE_BOUNDARY_ADMISSION_REVIEW_HANDOFF.zip`, SHA-256
`5064c0b6bddd5f780f650426a3ec215459576d09d12309191f522d52c0dfc31e`,
documents the source/evidence boundary and conditions. It is not an execution
artifact. The current owner task approves the documentation reference and these
two local files; no canonical baseline/state installation or release follows.

The dated scope, protocol v3, subordinate portfolio mission and November 18
state/designation remain governing contextual sources. A documentation evidence
reference does not supersede adopted RG05 or Windows reproduction requirements.

<a id="limits"></a>
## Reproduction, retention and release limitations

Use the [pinned README](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/README.md) to inspect its exact
prerequisites and STOP conditions, not the different guide in an arbitrary local
checkout. It still records public-review provenance and Windows reproduction
gaps. This index is evidence navigation, **not an executable replacement runbook**.
Any setup/download/service/HTTP/SQL/cleanup/CI action requires its applicable
separate approval and ownership checks. Linux evidence cannot satisfy a mandatory
Windows route by analogy. R2.3 cannot silently replace the main guide.

For retrospective review: obtain the identified retained originals, verify outer
SHA-256, unique inventory/CRC/member manifests, compare source/run/attempt,
inspect exact test identities and scenario receipts, and retain all limitations.
An expiring link, a badge or a summary alone is insufficient. Old artifacts may
require private access; no permanent public mirror is created here.

RG05=BLOCKED; G05=DEFERRED BY OWNER / NOT SATISFIED; PRELAUNCH_DECISION=REFUSE;
STAGE_B=NOT_AUTHORIZED; RELEASE=NOT_AUTHORIZED. G06/G09 FS-B1 provenance and
Windows G02/G03/D–J/release obligations are not closed. Fake-provider green tests
do not establish live-model semantic quality or production safety. This index
does not designate Portfolio V1 released.

Return to the [requirements/risk matrix](TRACEABILITY_MATRIX.md).
