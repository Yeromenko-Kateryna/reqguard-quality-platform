# RG-07B-03 — local implementation evidence

Date: 2026-10-24 (Europe/Berlin). No commit, push or PR.

**RG-07B-03 READY FOR INDEPENDENT REVIEW**

## Repository and exact changed paths

Working directory: `C:\Users\katal\OneDrive\Рабочий стол\projects\reqguard-quality-platform`.
Branch: `main`. Initial and final HEAD: `13ce0305d951c0cf2e6c158c7432d6a48cbe780c`.

All task files are new, untracked files:

1. `reqguard/evaluation/metrics.py`
2. `tests/test_evaluation_metrics.py`
3. `docs/ai-quality/RG-07B-03_IMPLEMENTATION_EVIDENCE.md`

Tracked `git diff --stat` is empty. No staging was performed. The new-file
diffstat is recorded at the end of this report. Existing untracked `ChatGPT file/`,
the two RG-04 evidence files, and all existing untracked `quality/api/` paths
were preserved. No tracked files changed, including the normative specification,
dataset, accepted hard-fail oracles, product and CI.

## Implementation and input contract

`aggregate(assessments, annotations, manifest)` consumes existing
`hard_fail.Assessment` records, externally supplied `Annotation` records and a
manifest mapping. It runs no capture, provider, semantic judgment or annotation
generation. All 12 frozen IDs and categories are mandatory; input ordering may
vary. Duplicate, missing, unknown and contradictory assessment IDs are rejected.
Absent annotations remain pending. Invalid outputs cannot carry human labels.

`Label` holds five integer scores (RI, AI, TA, GU, SI), five rationales, five
`Evidence(reference, start, end)` spans in original capture bytes, annotator ID,
and explicit boolean expected-property, prohibition, safety and grounding
findings. Two different annotators and an explicit independence declaration are
required. The byte-span representation is half-open and must reference the same
retained capture and stay within its bytes.

`Adjudication` identifies a third annotator, selected integer scores for disputed
dimensions, decisions for disputed findings, written rationale and cited evidence.
Undisputed labels cannot be replaced by adjudication. Original labels and human
finals are retained beside enforced vectors. Missing decisions are never averaged.

Manifest keys are enumerated in `MANIFEST_FIELDS`. Version fields use
`RG-07A-spec-v1`; dataset hashes and all input hashes are pinned. The explicit
representation for tools is `disabled_tool_capabilities=True`; deadline is positive
milliseconds; category order is functional, ambiguous, safety. Seed/support is
`{"seed": integer-or-null, "supported": boolean-or-"unavailable"}`. Settings must
be a nonempty mapping explicitly supplied by the caller, including unset defaults.
UTC start/capture timestamps and exact commit/template hashes are validated.
Explicit `model_revision="unavailable"` remains visible as allowed by §2.4.
Other unavailable provenance blocks PASS. Missing manifest fields block PASS;
contradictory supplied values raise `AggregationError` rather than becoming a
claim about model failure. Fake providers cannot establish a semantic PASS.

All calculations and gate comparisons use `fractions.Fraction`, with N=12,
D=5 and category/safety denominators 4. No partial mean is calculated around
PENDING dimensions. `to_record()` serializes exact rational numerators and
denominators alongside approximate display values. Rate records also preserve
the original sample numerator/denominator, bounds and unknown IDs. Agreement
reports the actual available initial-pair denominator, including per-dimension
disagreements and absolute differences; mechanical pairs are excluded.

Every gate is reported, including after a failure. Evidence completeness is an
additional component gate. Known failures take precedence over incomplete gates.
Per-example dispositions include individual coverage and applicable safety gates.
Raw bytes remain in the caller's assessment/capture; the output retains hashes,
artifact references, identity, capture/validation provenance, hard-rule evidence,
original annotations and final/overridden vectors.

## Commands and actual results

All test invocations used the existing `.venv`; no dependency was installed.

```powershell
.venv\Scripts\python.exe -m pytest tests/test_evaluation_metrics.py tests/test_evaluation_dataset.py tests/test_evaluation_hard_fail.py -q
```

- Initial sandbox run: exit **1**, `263 passed, 18 errors in 5.66s`.
  All 18 errors occurred during setup of existing dataset tests using `tmp_path`:
  pytest could not create a numbered directory in sandbox Temp. They affected
  the copy test, 14 rejected-byte fixture cases, and three unavailable-artifact
  cases. No evaluation assertion failed in that run.
- Approved repeat outside sandbox: exit **0**, `281 passed in 1.76s`.
- After additional threshold/provenance tests: exit **0**, `297 passed in 2.21s`.
- Final run after per-example disposition refinement: exit **0**:

```text
........................................................................ [ 24%]
........................................................................ [ 48%]
........................................................................ [ 72%]
........................................................................ [ 96%]
.........                                                                [100%]
297 passed in 2.20s
```

No failures, errors, skips or xfails in the final run. This includes **120 new
RG-07B-03 tests and all 177 existing RG-07B-01/02 tests**.

```powershell
.venv\Scripts\python.exe -m pytest tests/test_evaluation_metrics.py --collect-only -q
```

Exit **0**, `120 tests collected in 0.05s`.

`git diff --check`: exit **0**; tracked diff empty. A separate no-index whitespace
check covers each new file. `git status --short` confirms the three new task
paths alongside the preserved pre-existing untracked paths. HEAD is unchanged.

## Five-fixture conformance matrix

These are hypothetical unit-test records, not observed model outputs or collected
human annotations. All synthetic score-vector construction is confined to
`tests/test_evaluation_metrics.py`. The ASCII NFC test double is confined there.

Expected values below are from §6.1; actual values are obtained from the aggregator.
Full fixture assertions cover component gates, affected means, agreement,
completeness, overrides, uncertainty and safety rates.

| Fixture | Expected H / C | Expected macro | Expected verdict | Actual versus expected |
|---|---|---|---|---|
| G-PASS | 0/12 / 0/12 | 4 | PASS AGAINST PROPOSED V1 THRESHOLDS | MATCH |
| G-CRITICAL | 1/12 / 1/12 | 59/15 | FAIL | MATCH |
| G-MISSING | 1/12 exact / [0/12,1/12] | 11/3 | FAIL | MATCH |
| G-ORACLE-UNKNOWN | [0/12,1/12] / [0/12,1/12] | 4 | INCOMPLETE | MATCH |
| G-ADJUDICATION-PENDING | 0/12 / 0/12 | PENDING | INCOMPLETE | MATCH |

G-PASS: every example/dimension/category/category-dimension mean is 4; safety
rates 0/4; all gates PASS.

G-CRITICAL: final S01=(4,4,4,4,0), E(S01)=16/5; M(SI)=11/3 and other dimensions=4;
safety category mean=19/5 and its SI mean=3; both safety rates=1/4.
Contract, critical and safety semantic gates FAIL; all others PASS.

G-MISSING: final F01=(0,0,0,0,0), source `invalid_output_zero`, E=0; all dimension
means=11/3; functional mean and dimension means=3; both safety rates=0/4.
Attempts=12/12, received=11/12, valid=11/12, annotated valid=11/11; initial
agreement denominator=55. Contract and individual gates FAIL; critical is
INCOMPLETE; all others PASS. HF-02–05 uncertainty does not inflate exact H.

G-ORACLE-UNKNOWN: all semantic means=4; both safety rates=0/4. Contract and
critical gates INCOMPLETE; remaining gates PASS. No complete H=0 or C=0 claim.

G-ADJUDICATION-PENDING: F01 RI/E, M(RI), functional RI/overall and macro remain
PENDING. All unaffected means=4; both safety rates=0/4; agreement=59/60, one
disputed pair; annotated valid=11/12. Per-dimension, overall, category, individual,
annotation and evidence gates INCOMPLETE; others PASS. Semantic verdict PENDING.

### Actual aggregator output

| Fixture | Actual H | Actual C | Actual M | Actual verdict |
|---|---|---|---|---|
| G-PASS | 0/12 | 0/12 | 4 | PASS AGAINST PROPOSED V1 THRESHOLDS |
| G-CRITICAL | 1/12 | 1/12 | 59/15 | FAIL |
| G-MISSING | 1/12 | [0/12, 1/12] | 11/3 | FAIL |
| G-ORACLE-UNKNOWN | [0/12, 1/12] | [0/12, 1/12] | 4 | INCOMPLETE |
| G-ADJUDICATION-PENDING | 0/12 | 0/12 | PENDING | INCOMPLETE |

Actual output record excerpts below are generated through `RunResult.to_record()`.
They retain selected fields for readability; the API also returns all examples,
provenance, source rule records, original annotations and detailed metrics.

G-PASS:

```json
{
  "evaluation_run_id": "synthetic-conformance-only",
  "verdict": "PASS AGAINST PROPOSED V1 THRESHOLDS",
  "semantic_verdict": "PASS",
  "gates": {
    "contract_hard_fail": "PASS",
    "critical_safety": "PASS",
    "per_dimension": "PASS",
    "overall_semantic": "PASS",
    "category": "PASS",
    "individual_coverage": "PASS",
    "safety_semantic": "PASS",
    "annotation": "PASS",
    "evidence": "PASS"
  },
  "macro": {
    "numerator": 4,
    "denominator": 1,
    "value": 4.0
  },
  "F01_final_scores": [
    4,
    4,
    4,
    4,
    4
  ],
  "F01_source": "human_final",
  "H": {
    "numerator": 0,
    "denominator": 12,
    "exact": true,
    "unknown_ids": []
  },
  "C": {
    "numerator": 0,
    "denominator": 12,
    "exact": true,
    "unknown_ids": []
  }
}
```

G-MISSING:

```json
{
  "evaluation_run_id": "synthetic-conformance-only",
  "verdict": "FAIL",
  "semantic_verdict": "FAIL",
  "gates": {
    "contract_hard_fail": "FAIL",
    "critical_safety": "INCOMPLETE",
    "per_dimension": "PASS",
    "overall_semantic": "PASS",
    "category": "PASS",
    "individual_coverage": "FAIL",
    "safety_semantic": "PASS",
    "annotation": "PASS",
    "evidence": "PASS"
  },
  "macro": {
    "numerator": 11,
    "denominator": 3,
    "value": 3.6666666666666665
  },
  "F01_final_scores": [
    0,
    0,
    0,
    0,
    0
  ],
  "F01_source": "invalid_output_zero",
  "H": {
    "numerator": 1,
    "denominator": 12,
    "exact": true,
    "unknown_ids": []
  },
  "C": {
    "numerator": 0,
    "denominator": 12,
    "exact": false,
    "unknown_ids": [
      "F01"
    ]
  }
}
```

G-ADJUDICATION-PENDING:

```json
{
  "evaluation_run_id": "synthetic-conformance-only",
  "verdict": "INCOMPLETE",
  "semantic_verdict": "PENDING",
  "gates": {
    "contract_hard_fail": "PASS",
    "critical_safety": "PASS",
    "per_dimension": "INCOMPLETE",
    "overall_semantic": "INCOMPLETE",
    "category": "INCOMPLETE",
    "individual_coverage": "INCOMPLETE",
    "safety_semantic": "PASS",
    "annotation": "INCOMPLETE",
    "evidence": "INCOMPLETE"
  },
  "macro": "PENDING",
  "F01_final_scores": [
    "PENDING",
    4,
    4,
    4,
    4
  ],
  "F01_source": "PENDING",
  "H": {
    "numerator": 0,
    "denominator": 12,
    "exact": true,
    "unknown_ids": []
  },
  "C": {
    "numerator": 0,
    "denominator": 12,
    "exact": true,
    "unknown_ids": []
  }
}
```


## Negative and boundary-test inventory

- 20 inconsistent-assessment cases: missing/duplicate/unknown/extra IDs,
  category/input/run/response mismatches, rule identity/version/outcome/reference,
  failure without evidence, inconsistent schema/HF-01, absent valid capture,
  negative/NaN elapsed time, reversed timestamps and missing hard rule.
- Seven invalid-score cases: negative, >4, float, boolean, string, null and NaN.
- 12 invalid-annotation cases: duplicate/unknown IDs, same annotator, short vector,
  missing rationale/evidence, wrong reference/out-of-range span, absent or
  nonboolean findings, unregistered annotator and excess labels.
- Each of the 25 manifest fields is independently removed and must block PASS.
- 22 contradictory-manifest cases, including versions/hashes/order, tools,
  deadline, timestamps, settings, annotator IDs, commits and seed/support types.
- Missing labels, a single label and absent independence remain PENDING without
  fabricated scores. Five invalid-adjudication cases cover a non-third annotator,
  fractional score, changing an undisputed score, missing rationale and bad evidence.
- Score and finding disagreements require adjudication. Resolution preserves
  original labels and undisputed values. Unresolved expected-property findings
  also block the annotation gate without changing already agreed numeric scores.
- Critical SI and HF-05 GU overrides preserve initial perfect labels. Overlapping
  failures count once in H/C and once in each rule. Critical failures outside
  the safety subset are still global critical failures.
- GU/SI safety gates and agreed safety/grounding flags fail independently of HF
  results and high means. All four aggregate semantic threshold groups are
  exercised independently; the overall threshold test uses 191/60, which must
  fail even though a one-decimal display could read 3.2.
- Exact equality at thresholds passes. Known numeric failure outranks PENDING.
  Four denominator-mismatch cases cover both rate and mean helpers.
- Known HF failure outranks absent manifest and annotations. Fake-only evidence
  cannot PASS. Invalid output cannot be supplied human labels.
- All-invalid captures retain fixed denominators and mechanical count 12;
  agreement with denominator zero is NOT AVAILABLE. Reordered inputs preserve
  frozen output order and the macro identity (sum of 60 final scores / 60).
- Output provenance, explicit zero PASS/FAIL/NOT_ASSESSABLE counts, strict JSON
  serialization and input immutability are checked.

## Limitations and UNKNOWNs

No live semantic quality or human annotation evidence was produced. Authentic
annotator independence, annotation truth, complete free-text findings, manifest
authenticity, run-ID uniqueness across stored runs, and inclusion of every
provider default cannot be certified by this arithmetic module. Supplied
identifiers, rationale and references are validated structurally. A well-formed
but dishonest provider/annotation declaration is outside this offline trust boundary.

Existing Unicode 15.1 oracle availability is unchanged. Unit fixtures use only an
explicit ASCII test double, not a general Unicode conformance implementation.
No unspecified oracle, semantic inference, general disclosure detector or model
fault attribution has been added. There are no unresolved normative ambiguities
identified in the requested sections. Proposed thresholds remain uncalibrated.

## Operations NOT RUN

Model/API/network calls; actual human annotation collection; Docker; PostgreSQL
or other database execution; browser/UI/Playwright; product/API/integration tests;
CI execution or edits; dependency installation; live Unicode normalization
certification; commit; staging; push; PR; publication; remote mutations; paid AI.
These are outside the requested offline aggregation scope or explicitly prohibited.

Next step: independent review of the implementation and synthetic conformance
evidence against RG-07A §§2.4, 4, 5, 6 and 6.1 before any separate publication task.

## Final git status and whitespace checks

```text
?? "ChatGPT file/"
?? RG-04_EVIDENCE_COMPLETION.md
?? RG-04_IMPLEMENTATION_EVIDENCE.md
?? docs/ai-quality/RG-07B-03_IMPLEMENTATION_EVIDENCE.md
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
?? reqguard/evaluation/metrics.py
?? tests/test_evaluation_metrics.py
```

- reqguard/evaluation/metrics.py: exit 1; no whitespace errors
- tests/test_evaluation_metrics.py: exit 1; no whitespace errors
- docs/ai-quality/RG-07B-03_IMPLEMENTATION_EVIDENCE.md: exit 1; no whitespace errors

Git emitted LF-to-CRLF working-copy notices; no whitespace errors.
Exit 1 is the no-index difference status for comparison of each added file with
NUL; the checks emitted no whitespace-error diagnostics.

## Final new-file diffstat

```text
reqguard/evaluation/metrics.py | 493 +
tests/test_evaluation_metrics.py | 480 +
docs/ai-quality/RG-07B-03_IMPLEMENTATION_EVIDENCE.md | 408 +
3 files changed, 1381 insertions(+)
```
