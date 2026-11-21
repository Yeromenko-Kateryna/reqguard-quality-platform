# Portfolio evidence — accepted post-merge coverage

Documentation candidate prepared 21 November 2026. Source reference: commit
`4640729a9662ef76922f6b22243edb41db65d486`, tree `92b592c05753f839a390dd0bfeedbf6916a210a7`. These portfolio files are local documentation
candidates, not claimed to be present in that historical commit. No publication
or Portfolio V1 release is authorized.

Start with the [execution evidence index](EVIDENCE_INDEX.md#accepted-post-merge-evidence).
This table links existing requirement/risk aliases to tests and **accepted historical
execution**, not new runs. The unchanged D1 matrix below retains its older source
and execution identities. The PM labels only identify documentation entries.

| Requirement / risk | Test at accepted post-merge source | Accepted execution and receipt path | Verified boundary |
|---|---|---|---|
| MVP-REQ-01/04; RISK-01/04 | [B01: supported fixture: browser HTTP 200, visible result, independent committed SQL row](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/quality/browser/analyses.spec.ts) | [P01](EVIDENCE_INDEX.md#p01): [RG-06D 44945635070, attempt 1](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/44945635070/attempts/1); `results.json`, `supported-sql.json` | Chromium displays the fake/completed response; independent SQL row matches run_id and complete analysis. One supported fixture, not general requirement understanding. |
| MVP-REQ-03; RISK-03 | [B02: invalid whitespace: actual FastAPI HTTP 422 and unchanged SQL snapshot](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/quality/browser/analyses.spec.ts) | [P01](EVIDENCE_INDEX.md#p01): same accepted run; `invalid-sql.json` | Actual HTTP 422 and unchanged SQL snapshot. Not all invalid-input boundaries. |
| MVP-REQ-02/04; RISK-02/04 | [B03: unsupported fixture: browser HTTP 200, visible unsupported result, independent SQL NULL row](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/quality/browser/analyses.spec.ts) | [P01](EVIDENCE_INDEX.md#p01): same accepted run; `unsupported-sql.json` | Unsupported response preserves original input and SQL NULL; no semantic analysis claimed. |
| MVP-REQ-05/10; RISK-05/10 | [B01/B03 browser cases](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/quality/browser/analyses.spec.ts) and [source-bound harness](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/scripts/run_rg06d_ci.py) | [P01](EVIDENCE_INDEX.md#p01): `launch.json`, `supported-cleanup.json`, `unsupported-cleanup.json`, `sql-cleanup.json`, `run-summary.json` | Exact commit/run/attempt; recorded owned cleanup CLEANED, uncertainty false, sentinel preserved. Not RG05 isolation or independent post-job Engine inspection. |
| MVP-REQ-06/07/08; RISK-06/07/08 | [11 frontend contract cases](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/tests/ui.test.mjs) — exact executed names in P02 | [P02](EVIDENCE_INDEX.md#p02): [frontend 44945635046, attempt 1](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/44945635046/attempts/1); `ui-contracts.xml`, validation/source receipts | DOM-adapter contracts, including error/loading/markup handling; these are not real-browser E2E. |
| MVP-REQ-11; RISK-11 | [dataset suite](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/tests/test_evaluation_dataset.py), [hard-fail suite](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/tests/test_evaluation_hard_fail.py), [metrics suite](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/4640729a9662ef76922f6b22243edb41db65d486/tests/test_evaluation_metrics.py) | [P03](EVIDENCE_INDEX.md#p03): [offline 44945635146, attempt 1](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/actions/runs/44945635146/attempts/1); retained suite/gate logs | Accepted 297-test mechanical evaluator suite; separate integrity/fake jobs qualified in P03. Not live-model semantic quality. |

Windows main-guide literal reproduction remains **BLOCKED**. The separately accepted
R2.3 manual demo is qualified evidence at a different commit, not Ubuntu CI or
main-guide reproduction. Privacy acceptance covers known Playwright Git metadata
structures and inspected uploaded files; it is not universal PII detection.
See [access and remaining limits](EVIDENCE_INDEX.md#current-limits).

## Historical D1 matrix — retained verbatim

The following original 18 November candidate is preserved without revising its
claims, review labels or a4e74599… links. Its historical status statements are not
new current observations or a replacement for the post-merge entries above.

# Portfolio MVP requirements-to-tests traceability

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

## Reading the statuses

VERIFIED HISTORICAL means the exact retained artifact and identified tests support
that bounded capability at the stated execution revision. It does not mean this
implementation task ran tests. SOURCE ONLY and HISTORICAL CI METADATA are not
runtime verification. A partial row must retain its qualification when quoted.

| Requirement ID | Risk ID | Existing behavior / evidence objective | Identifiable tests / source | Execution reference | Status and limit |
|---|---|---|---|---|---|
| MVP-REQ-01 | RISK-01 | Exact supported text yields fake/completed analysis and the same run_id in visible UI and committed SQL. | [`B01`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/quality/browser/analyses.spec.ts#L155); [`test_fixture_analysis`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/test_analyses.py#L22) | [E01](EVIDENCE_INDEX.md#e01) | VERIFIED HISTORICAL — one supported browser/HTTP/SQL scenario; Python source alone is not an E01 pytest run. |
| MVP-REQ-02 | RISK-02 | Other valid text yields unsupported_fixture, null analysis, exact original input and SQL NULL. | [`B03`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/quality/browser/analyses.spec.ts#L233); [`test_unsupported_fixture`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/test_analyses.py#L65) | [E01](EVIDENCE_INDEX.md#e01) | VERIFIED HISTORICAL — padded unsupported synthetic text; not all possible strings. |
| MVP-REQ-03 | RISK-03 | Whitespace receives actual HTTP 422 and leaves SQL snapshot unchanged. | [`B02`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/quality/browser/analyses.spec.ts#L202); [`test_validation_never_invokes_provider_or_repository`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/test_persistence_unit.py#L20) | [E01](EVIDENCE_INDEX.md#e01) | VERIFIED HISTORICAL — whitespace network case; complete provider/repository unit matrix is SOURCE ONLY here. |
| MVP-REQ-04 | RISK-04 | Correlate committed rows, JSONB/status/schema and response by UUID, not timestamps. | [`B01`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/quality/browser/analyses.spec.ts#L155) / [`B03`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/quality/browser/analyses.spec.ts#L233); [`test_exact_metadata`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/test_postgres_integration.py#L67) | [E01](EVIDENCE_INDEX.md#e01) | VERIFIED HISTORICAL — E01 schema/baseline and three scenario receipts; separate Python integration execution not claimed. |
| MVP-REQ-05 | RISK-05 | Preserve sentinel and unrelated rows; delete only proven owned rows, stop on uncertain cleanup. | [`B01`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/quality/browser/analyses.spec.ts#L155) / [`B03`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/quality/browser/analyses.spec.ts#L233); [Ownership negative-case source](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/quality/browser/owned-cleanup.test.ts#L57) | [E01](EVIDENCE_INDEX.md#e01) | VERIFIED HISTORICAL — recorded CLEANED positive scenario and unchanged sentinel; no universal isolation guarantee. |
| MVP-REQ-06 | RISK-06 | Display actual API fields and render untrusted text as text nodes. | [`B01`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/quality/browser/analyses.spec.ts#L155); [Markup/text-node contract](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/ui.test.mjs#L118) | [E01](EVIDENCE_INDEX.md#e01), [E02](EVIDENCE_INDEX.md#e02) | VERIFIED HISTORICAL — browser fixture rendering plus adversarial DOM-adapter test; not browser-wide XSS certification. |
| MVP-REQ-07 | RISK-07 | Disable duplicate submission while loading and replace stale completed/unsupported/error state. | [Loading and stale-state contracts](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/ui.test.mjs#L135) | [E02](EVIDENCE_INDEX.md#e02) | VERIFIED HISTORICAL — DOM-adapter contracts; E01 single-POST assertions have a narrower browser scope. |
| MVP-REQ-08 | RISK-08 | Distinguish validation, persistence/server, uncertain transport and malformed response; never automatically retry. | [UI failure contracts](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/ui.test.mjs#L65); [`test_db_errors_are_sanitized_without_retry`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/test_persistence_unit.py#L30) | [E02](EVIDENCE_INDEX.md#e02) | PARTIALLY VERIFIED — 11 DOM contracts include 422/503/500/network/malformed cases; live database outage/uncertain COMMIT not exercised by E01. |
| MVP-REQ-09 | RISK-09 | Strict string/non-whitespace, 1–2000 characters, valid UUID and OpenAPI completed/unsupported envelopes. | [`test_invalid_text`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/test_analyses.py#L58); [`test_openapi_request_and_response_contracts`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/test_analyses.py#L80) | [E03 source limits](EVIDENCE_INDEX.md#e03) | SOURCE ONLY for full Python matrix at this baseline; E01 verifies three network cases, not all length/type/OpenAPI boundaries. |
| MVP-REQ-10 | RISK-10 | Bind execution, dependencies, test identities, artifacts and cleanup receipts to exact CI source/attempt. | [RG06D workflow](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/.github/workflows/rg06d-e2e.yml); [Frontend workflow](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/.github/workflows/rg-ui-contracts.yml); [Admission-test source](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/scripts/test_rg06d_admission.py) | [E01](EVIDENCE_INDEX.md#e01), [E02](EVIDENCE_INDEX.md#e02) | VERIFIED HISTORICAL within recorded gates: 25 runtime inputs and three frontend source hashes rechecked; no fresh setup or all-suite claim. |
| MVP-REQ-11 | RISK-11 | Keep deterministic dataset/rules/metrics/evidence/fake execution separate from semantic evaluation. | [`test_exact_artifact_and_specification_fixture`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/test_evaluation_dataset.py#L23); [`test_safety_semantic_gate_independent_of_hard_rules`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/test_evaluation_metrics.py#L352); [`test_complete_run_and_exact_byte_roundtrip`](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/tests/test_evaluation_execution.py#L62) | [E03](EVIDENCE_INDEX.md#e03) | HISTORICAL CI METADATA + SOURCE — offline raw outputs not independently recounted here; live semantic quality NOT VERIFIED. |
| MVP-REQ-12 | RISK-12 | Provide English, revision-bound evidence and honest reproduction/platform limitations. | [Pinned README](https://github.com/Yeromenko-Kateryna/reqguard-quality-platform/blob/a4e74599a047f2db251d8e951e0b53718be97b92/README.md); [this evidence index](EVIDENCE_INDEX.md#limits) | [E04](EVIDENCE_INDEX.md#e04), [E05](EVIDENCE_INDEX.md#e05) | DOCUMENTATION REVIEW PENDING; no Windows main-guide reproduction or Portfolio V1 release is claimed. |

## Risk register

| Risk ID | Failure being controlled / assessed |
|---|---|
| RISK-01 | Wrong fixture/status or unrelated row accepted as success. |
| RISK-02 | Unsupported input loses padding or stores JSON null instead of SQL NULL. |
| RISK-03 | Invalid requests reach persistence or create an unnoticed row. |
| RISK-04 | Response is confused with committed data; schema/payload mapping drifts. |
| RISK-05 | Cleanup deletes foreign/changed data or removes sentinel on uncertainty. |
| RISK-06 | API text is interpreted as markup; result fields are missing. |
| RISK-07 | Duplicate clicks or stale UI state produce misleading outcomes. |
| RISK-08 | 503/500/network/malformed success is reported as success or retried. |
| RISK-09 | Strict request boundaries, UUID or OpenAPI envelope silently change. |
| RISK-10 | Green CI is attributed to different source, attempt or missing artifact. |
| RISK-11 | Synthetic evaluator success is presented as live semantic quality. |
| RISK-12 | An unverified guide/platform or partial demo is presented as release readiness. |

## Coverage gaps and boundaries

- API Python tests use TestClient and persistence stubs where declared. They are
  not automatically real-socket/real-DB evidence. Full current Python execution is
  not supplied by the three Chromium cases or 11 frontend contracts.
- E01 supplies real HTTP/SQL for supported, whitespace-invalid and unsupported
  inputs. Live 503/500/uncertain COMMIT and all request boundaries remain outside
  that three-case browser artifact. E02 uses a DOM adapter and response seams.
- Offline mechanical checks do not establish live-model semantics, authentic human
  labels, production AI safety or all-platform filesystem behavior.
- Windows R2.3 is a separate qualified manual candidate. It does not verify the
  approved main's Windows guide or satisfy Ubuntu automated CI by substitution.
- RG05 remains BLOCKED; G05 is DEFERRED BY OWNER / NOT SATISFIED. REFUSE,
  STAGE_B=NOT_AUTHORIZED and RELEASE=NOT_AUTHORIZED remain. Windows reproduction,
  G02/G03/D–J and all existing independent/security/release gates are not waived.

No application/test/workflow behavior or canonical state is changed by these IDs
or documents. See the [evidence index](EVIDENCE_INDEX.md) for exact revisions,
retention, private-source access and NOT VERIFIED items.
