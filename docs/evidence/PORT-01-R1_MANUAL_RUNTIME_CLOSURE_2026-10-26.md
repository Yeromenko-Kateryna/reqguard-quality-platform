# PORT-01-R1 — Manual Runtime Evidence Index and Closure Handoff

Date: 2026-10-26  
Project: ReqGuard Quality Platform  
Repository: Yeromenko-Kateryna/reqguard-quality-platform  
Pinned baseline commit: ce72c5bb6f35b1935bb0c3dee1fa15b1b1aef40a  
Acceptance authority: RG-00  
Document status: RG-00 document review ACCEPT with corrections D-01 and D-02 applied

## Acceptance and scope

RG-00 reports Phase A, Phase B manual E2E, and Phase B primary evidence
export as ACCEPT. These are supplied acceptance decisions, not decisions
newly assigned by this document or the independent reviewer.

Independent Codex verification found that all seven evidence hashes
matched, the complete positive response matched the pinned authored
fixture and exported SQL row, the three subsequent SQL snapshots were
byte-identical, and the Uvicorn log recorded both HTTP outcomes and
graceful shutdown.

The initial baseline provenance blocker was resolved through additional
historical operator receipts. Phase B baseline provenance remains
OPERATOR RECEIPT SUPPORTED, rather than embedded or cryptographically
attested file provenance.

The scenarios concern a deterministic fake provider. They do not establish
live-model semantic quality. This record does not declare Portfolio V1.0
released.

## Environment and retained state

- Runtime: private GitHub Codespace “wild spooky specter”.
- Application: ReqGuard browser UI → FastAPI → PostgreSQL.
- Provider: fake; authored deterministic response.
- Phase B evidence directory: /workspaces/port01-phase-b.Kd74bQgY.
- Uvicorn log: process 5989, loopback listener 127.0.0.1:8000.
- Codespace state: STOPPED, according to operator receipts.
- PostgreSQL test row retained:
  b719ebf0-1f93-413d-a910-1514b31cb363.
- SQL DELETE was not authorized. No cleanup is implied by this closure.

The pinned source was independently inspected. Deployment identity and
actual SQL execution context are supported by operator receipts; the
exported files do not independently attest the complete runtime identity.

## Evidence classification

- PRIMARY FILE VERIFIED: independently inspected bytes or contents.
- OPERATOR RECEIPT SUPPORTED: historical execution, provenance or
  acceptance information supplied by RG-00/operator.
- INFERENCE: a conclusion drawn from consistent evidence.
- UNKNOWN / MISSING: not established by the reviewed material.

## Private original evidence manifest

The seven original artifacts are held in a private evidence bundle and
are not committed or published. This index does not publish them or assign
public artifact URLs. E1–E7 are internal Markdown manifest anchors, not
download URLs. Authorized reviewers need access to the corresponding
private originals.

Hashes and sizes were independently calculated during PORT-01-R1.
No application or test rerun was used.

| ID | Artifact | Bytes | SHA-256 |
|---|---|---:|---|
| <a id="e1"></a>E1 | http200.original.har | 8184 | f61afdcbdd5d79e32f1e66da37402b1e2094055173ccf87b9088218b19c89866 |
| <a id="e2"></a>E2 | http422.original.har | 7561 | 0251b7394fcb8bbf50ee95e6f5f1a52c7b87591a7d5746212296fad8bf7f1395 |
| <a id="e3"></a>E3 | Phase B original: `/workspaces/port01-phase-b.Kd74bQgY/initial-table.json`; downloaded Windows copy: `initial-table (1).json` | 3 | 37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570 |
| <a id="e4"></a>E4 | after-200.json | 868 | a988895f3775122e90bf0c2e15fe9a51415a02a2ad2870277d4b20b0b1effa5f |
| <a id="e5"></a>E5 | before-422.json | 868 | a988895f3775122e90bf0c2e15fe9a51415a02a2ad2870277d4b20b0b1effa5f |
| <a id="e6"></a>E6 | after-422.json | 868 | a988895f3775122e90bf0c2e15fe9a51415a02a2ad2870277d4b20b0b1effa5f |
| <a id="e7"></a>E7 | uvicorn.log | 789 | eb893908055c347c23699fda905107de35d7b99a350ebf6ac0a1c30b5d5dc3ab |

E3 identifies the separate Phase B original and its downloaded copy, not
the Phase A snapshot. The independently inspected Windows file was named
initial-table.json and contained exactly [] followed by LF. Identical
empty-file bytes do not distinguish Phase A and Phase B captures. The
downloaded Phase B filename initial-table (1).json was not separately
opened by the independent reviewer; its provenance and reported hash are
recorded in R2.

## Preserved operator receipts

These entries preserve the supplied receipt substance without requiring
conversation history. They are transcriptions of operator reports, not
independently authenticated terminal recordings.

<a id="r1"></a>
### R1 — Acceptance authority

RG-00 supplied these dispositions:

- Phase A: ACCEPT.
- Phase B manual E2E: ACCEPT.
- Phase B primary evidence export: ACCEPT.
- Independent Codex evidence verification: completed.

The seven-file bundle does not supply detailed Phase A scenario evidence.
Phase A acceptance is therefore recorded as an authority decision, not
re-established as a new primary-file PASS.

<a id="r2"></a>
### R2 — Phase B baseline provenance reconciliation

A fresh read-only PostgreSQL query captured the Phase B initial snapshot
on 2026-10-26 before the HTTP 200 submission. Reported terminal result:
SNAPSHOT_EXIT=0; content [].

Export-only inspection at 2026-10-26T16:07:28Z reported:

- Source: /workspaces/port01-phase-b.Kd74bQgY/initial-table.json.
- Size: 3 bytes.
- Listing modification time: Oct 26 14:19; listing timezone not established.
- SHA-256:
  37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570.
- Distinct Phase A source:
  /workspaces/port01-phase-a.H9vYmXIE/evidence/initial-table.json.
- Downloaded Windows filename: initial-table (1).json, because the Phase A
  file already occupied initial-table.json.

The earlier closure document identified the previously inspected initial
file as Phase A. R2 supplies the separate Phase B capture chain. The
reviewer found this sufficient to resolve the provenance blocker under
the existing acceptance criteria, while preserving its operator-supported
classification.

<a id="r3"></a>
### R3 — SQL execution and shutdown

The supplied historical closure document,
REQGUARD_PHASE_B_EVIDENCE_CLOSURE_2026-10-26.md, reports:

- Successful read-only SQL captures and SQL exit status 0.
- Successful remote comparisons of the subsequent snapshots.
- Uvicorn interrupt, subsequent PID absence and no listener on port 8000.
- PostgreSQL container stop with state exited.
- Retained named volume reqguard_rg04_v11_pgdata_20261008.
- GitHub screenshot displaying Codespace “wild spooky specter” stopped.

The underlying terminal recordings and screenshots are not among E1–E7.
The document’s earlier statements that subsequent SQL files and the full
log were not exported are superseded by their later receipt and
independent inspection. Other historical claims remain receipt-supported.

## Positive scenario — content checks PASS

Request:

    POST /analyses
    {"requirement_text":"The user can quickly reset their password"}

[E1](#e1) contains exactly one entry and exactly one POST, returning HTTP
200. Its JSON response contains:

- run_id: b719ebf0-1f93-413d-a910-1514b31cb363, a valid UUIDv4.
- provider: fake.
- status: completed.

The complete analysis structurally equals fake_analysis() in
reqguard/main.py at the pinned commit: every ambiguity field, missing
criterion, scenario title, all three ordered steps and expected result.
The comparison used static source parsing without executing product code.

[E4](#e4) contains exactly one row. Its run_id, provider, status,
original_input and complete analysis_payload match the HTTP response.
created_at is non-null: 2026-10-26T14:25:39.652107+00:00.

[E3](#e3) establishes empty snapshot content; [R2](#r2) supports its
separate Phase B capture before this submission. [E7](#e7) records one
POST /analyses returning 200.

## Negative scenario — content checks PASS

Request:

    POST /analyses
    {"requirement_text":"   "}

[E2](#e2) contains exactly one entry and exactly one POST. The request value
is exactly three U+0020 spaces. The response is HTTP 422 with:

- type: value_error.
- loc: ["body", "requirement_text"].
- msg: Value error, requirement_text must contain non-whitespace characters.
- input: the same three spaces.

[E4](#e4), [E5](#e5) and [E6](#e6) are byte-identical complete exported
snapshots. Each contains exactly one row. No additional committed rows
appear in the final snapshot. [E7](#e7) records one POST /analyses returning
422.

Snapshot equality does not prove the absence of every possible
intermediate mutation. Completeness of the live-table query is supported
by the operator SQL receipts, rather than authenticated by JSON alone.

## Evidence-to-claim traceability

| Claim | Support | Classification / result |
|---|---|---|
| RG-00 accepted Phase A and Phase B | [R1](#r1) | OPERATOR RECEIPT SUPPORTED |
| All seven hashes and sizes match | [E1–E7](#private-original-evidence-manifest) | PRIMARY FILE VERIFIED / PASS |
| Positive request, 200 and UUIDv4 | [E1](#e1) | PRIMARY FILE VERIFIED / PASS |
| Complete authored-fixture equality | [E1](#e1); pinned reqguard/main.py | PRIMARY FILE VERIFIED / PASS |
| Exported SQL row matches response | [E1](#e1), [E4](#e4) | PRIMARY FILE VERIFIED / PASS |
| Initial snapshot content is empty | [E3](#e3) | PRIMARY FILE VERIFIED / PASS |
| Empty baseline was captured in Phase B before submission | [R2](#r2) | OPERATOR RECEIPT SUPPORTED |
| Three-space request produces expected 422 | [E2](#e2); pinned validator | PRIMARY FILE VERIFIED / PASS |
| Subsequent snapshots are byte-identical | [E4](#e4), [E5](#e5), [E6](#e6) | PRIMARY FILE VERIFIED / PASS |
| Log contains both HTTP outcomes | [E7](#e7) | PRIMARY FILE VERIFIED / PASS |
| Browser submission path is consistent | E1/E2 initiator stacks; pinned static/app.mjs | PRIMARY FILE VERIFIED for metadata; INFERENCE for causal linkage |
| Manual UI interaction and rendered result | [R3](#r3) historical screenshot report | OPERATOR RECEIPT SUPPORTED |
| Uvicorn records graceful shutdown | [E7](#e7) | PRIMARY FILE VERIFIED / PASS |
| Docker and Codespace stopped; storage retained | [R3](#r3) | OPERATOR RECEIPT SUPPORTED |
| Test row present in final exported state | [E6](#e6) | PRIMARY FILE VERIFIED |
| Test row retained after shutdown | [R3](#r3); RG-00 handoff | OPERATOR RECEIPT SUPPORTED |

## Correlation and clock limitations

Matching UUID and full response/payload equality strongly support the
reported HTTP-to-database correlation. Both HAR initiator stacks identify
submitRequirement, consistent with pinned UI code.

The Uvicorn log has no per-request timestamps or run_id. HAR coverage is
limited to its recording windows. Full correlation-ID tracing and unique
causal attribution are not established.

The positive HAR starts at 2026-10-26T14:25:37.896Z. Adding its duration
gives an approximate end of 14:25:38.583557Z. SQL created_at is approximately
1.069 seconds later. Pinned persistence code saves before returning the
response, but browser/database clock synchronization is undocumented.
These timestamps cannot independently establish cross-system ordering.

Hashes establish byte identity against the recorded manifest. They do
not authenticate capture time, query scope, runtime identity or custody.

## Remaining unverified scope

- GitHub Actions CI results.
- Literal execution of the Windows README procedure.
- Live-model semantic quality.
- Full correlation-ID tracing.
- Detailed Phase A scenarios from primary artifacts in this bundle.
- Independent clock synchronization and complete runtime attestation.
- Underlying Docker/Codespace shutdown screenshots and terminal receipts
  as separately inspected primary artifacts.

These limits do not reverse the supplied RG-00 acceptance decisions.
They constrain what this evidence index claims.

## Closure recommendation

The verified contents and reconciled operator provenance support closure
documentation review. Preserve the originals privately and retain the
PostgreSQL test row. No rerun, SQL DELETE, publication or release is
authorized by this document.

READY FOR RG-00 DOCUMENT REVIEW
