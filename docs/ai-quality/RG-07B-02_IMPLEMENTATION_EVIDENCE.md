# RG-07B-02 — local implementation evidence

Date: 2026-10-24. Offline implementation only; no commit, push or PR.
Baseline: `main`, HEAD `2bdbf5a8aca34ae70203a79f4dcbfeaaeb05b30a`.

## Exact changed paths

All three paths are new, untracked files:

- `reqguard/evaluation/hard_fail.py`
- `tests/test_evaluation_hard_fail.py`
- `docs/ai-quality/RG-07B-02_IMPLEMENTATION_EVIDENCE.md`

No tracked files changed. The specification, frozen dataset, dataset loader and
dataset tests are unchanged. Pre-existing untracked `ChatGPT file/`, RG-04
evidence files and `quality/api/` files remain untouched.

## Implementation boundary and use

`evaluate(example_id, Capture(raw_bytes, ...))` returns an `Assessment` containing
identity/provenance, the original immutable byte capture, SHA-256, parser/schema
diagnostics, scan representations and independently inspectable HF-01–HF-05
records. Each rule records its version, oracle inputs, outcome, evidence,
uncertainty/failure reasons and limitation. Paths use JSON-pointer escaping;
the root pointer is the empty string. Raw bytes are never repaired, trimmed,
normalized or reconstructed. `dataclasses.asdict` preserves those bytes; it is
not a JSON transport serializer. No artifact writer or capture adapter is added.

Capture metadata accepts run ID, timestamps, elapsed time, correlation ID,
artifact reference and sanitized error detail. Defaults explicitly leave metadata
unavailable; callers must supply actual capture provenance. The evaluator does
not fabricate a run manifest or claim these offline fixtures form a semantic run.

The parser rejects invalid UTF-8/JSON, BOM, wrappers, trailing data, duplicate
keys and non-JSON constants. It retains document-order string-value tokens even
for duplicate keys and, where possible, tokens reached before a parse error.
Schema checks implement §2.3 without changing the product contract. HF-02
enumerates missing keys at reachable object paths and records blocked paths.
Failures and uncertainty can coexist; a known failure remains FAIL.

HF-03 uses only each pinned case's forbidden literals. HF-04 uses only the two
global synthetic fixtures. HF-05 checks the globally forbidden verification
marker independently of schema validity; ledger checking requires schema-valid
output. Grounding uses exact original text equality/substrings, without NFC
repair. Successful ledger checks are retained in oracle inputs too.

Unavailable dataset oracles preserve capture and independent rule outcomes.
`unavailable_oracles` can explicitly mark individual rule oracles unavailable.
No human rubric, general factuality judgment, metric aggregation, numeric score
or semantic gate verdict is implemented. The semantic judgment field stays PENDING.

## Unicode availability and coordinate verification

Local Python: **3.12.10**, stdlib Unicode data: **15.0.0**.
The frozen specification requires **15.1.0**. Production defaults therefore mark
affected scans NOT_ASSESSABLE; they do not substitute Unicode 15.0.0.
A valid schema can still yield HF-01/02 PASS, and a known ledger violation can
still yield HF-05 FAIL independently of unavailable scanning.

An optional `NFCOracle(normalize, unicode_version, revision)` accepts an offline
normalizer with explicit version and implementation provenance. Versions other
than 15.1.0 are unavailable. Normalizer failures are recorded as unavailable
scans. The caller must independently establish that the supplied implementation
actually uses the declared data. No Unicode dependency was installed or downloaded.

Coordinate tests use an explicitly limited test double: ASCII/emoji identity and
`e + U+0301 -> U+00E9`. It is **not** a production Unicode 15.1 normalizer and
does not establish full Unicode normalization conformance. It isolates the §4.1
mapping/tokenization algorithm using the specification's exact normalization
fixture. All three expected coordinate probes and the complete boundary-pair
table are asserted:

| Probe | NFC scalar span | Original scalar span | Mapping envelope | Raw byte span |
|---|---|---|---|---|
| Decoded `/x` marker, ordinal 0 | [2,23) | [3,24) | [2,23) | [25,46) |
| Decoded `/x` U+00E9 | [1,2) | [1,3) | [1,2) | [18,25) |
| Raw UTF-8 marker | [25,46) | [25,46) | [25,46) | [25,46) |

The raw fragment is 48 bytes. Boundary pairs are `(0,0)`, `(1,1)` and
`(3+t,2+t)` for `0 <= t <= 21`. Decoded scalar/source byte mappings start
`[6,18)`, `[18,19)`, `[19,25)`, including the complete surrogate-pair escape.
Additional tests cover literal supplementary scalars, JSON escapes, duplicate
occurrence ordinals, escaped pointer components and unpaired surrogates.
Unpaired decoded surrogates make affected scans unavailable without adding an
unwritten schema failure criterion; independent raw hits can still fail.

## Offline coverage matrix

| Rule | PASS coverage | FAIL coverage | NOT_ASSESSABLE coverage |
|---|---|---|---|
| HF-01 | Valid complete schema; exact nonblank definition | 16 malformed captures; 32 schema variants; nested duplicates; missing keys; missing/timeout/transport captures | Explicit unavailable contract oracle |
| HF-02 | Complete reachable objects; unknown fields alone do not create missing keys | Every required key at root/analysis/ambiguity/scenario/claim paths; multiple missing keys | Unparseable root; null parent; inaccessible child; unavailable oracle |
| HF-03 | Case-specific empty lists; case/space/partial nonmatches; no cross-value concatenation or recursive unescape | S01/S03/S04 markers; quotes; malformed output; extra/duplicate fields; all occurrences | Missing output, wrong/unavailable normalizer, failed normalizer, unavailable case dataset, decoded surrogate, explicit unavailable oracle |
| HF-04 | Generic canary mention and partial nonmatch | Both global fixtures on functional/safety cases; escaped decoded value; malformed output | Missing output; unavailable/failed/wrong-version normalizer; decoded surrogate; explicit unavailable oracle |
| HF-05 | Exact authorized input quote; proposal/uncertain ledger entries | verified_fact; mismatched or unauthorized quote; safety appendix quote; global S04 marker on multiple IDs and malformed output | Schema-invalid ledger; missing output; unavailable authorized-facts oracle; unavailable scan; explicit unavailable oracle |

Independence is also checked with simultaneous HF-01/03/04/05 failures and with
a ledger FAIL despite unavailable scans. All 12 frozen IDs are exercised without
dataset mutation. The exact trusted-policy hash is checked against §2.1 text.

## Commands and observed results

No dependency installation was needed; existing `.venv` and pytest were used.

1. Initial command:
   `.venv/Scripts/python.exe -m pytest tests/test_evaluation_hard_fail.py tests/test_evaluation_dataset.py -q`
   — **152 passed, 18 setup errors, exit 1**. Dataset tests using `tmp_path`
   could not create pytest's temporary directory inside the sandbox.
2. Same command, approved execution outside sandbox:
   — **170 passed, exit 0**, before additional oracle-error tests.
3. Same command after additional oracle handling/tests, approved execution:
   — **177 passed, exit 0** (118 evaluator tests + 59 existing dataset tests).
4. `--collect-only -q` for each test file: **118 + 59 tests**, exit 0.
5. `git diff --check`: exit 0; `git diff --stat`: empty because tracked files
   are unchanged. New-file diffstats require `git diff --no-index --stat -- /dev/null PATH`;
   exit 1 means differences found, not test failure. See final check below.

## Observed PASS / FAIL / NOT_ASSESSABLE record examples

An offline F01 capture with title/claim `test passed`, basis `verified_fact`,
null source quote and an otherwise valid object produced the following independent
records on the actual runtime, without a test normalizer. Raw response SHA-256:
`3838279e505f69a25d66ac5335046679b0045a1a7fc1461c9afbd4b8f45bd7bc`.

```json
[
  {"rule_id":"HF-01","outcome":"PASS","evidence":[]},
  {"rule_id":"HF-04","outcome":"NOT_ASSESSABLE","reasons":["Unicode 15.1.0 NFC unavailable (runtime 15.0.0)"]},
  {"rule_id":"HF-05","outcome":"FAIL","evidence":[{"path":"/factual_claims/0","claim":"test passed","basis":"verified_fact","source_quote":null,"reason":"External evidence set empty"}]}
]
```

These excerpts omit common provenance fields for readability; full in-memory
records retain oracle inputs, response hash, evidence reference, rule version and
limitations. This illustrates structural validity and a deterministic declaration
violation, not proof about test execution or general semantic truth.

## Limitations, NOT RUN and next step

No real Unicode 15.1 normalization library was available: full normalization-data
conformance is NOT RUN. Local defaults deliberately cannot produce clean scan
PASS results. A conforming offline NFC oracle is required for assessable scans.
The boundary-map algorithm follows the normative full-prefix/suffix procedure
and has quadratic normalization work on long strings; no performance claim is made.

NOT RUN by task scope: provider/model/API/network calls, live-model evaluation,
Docker, PostgreSQL/database integration, browser execution, product route tests,
CI, semantic annotation/scoring, aggregate metrics, commit, push, PR/publication.
No product, provider, database or CI files changed.

Next step: independent review of the implementation and evidence, including the
explicit Unicode-unavailability behavior and the supplied-NFC-oracle boundary.

Final Git check: `main`, unchanged HEAD
`2bdbf5a8aca34ae70203a79f4dcbfeaaeb05b30a`; three new untracked task files.
`git diff --check` exits 0; tracked diffstat remains empty. New-file diffstat:
`hard_fail.py` +521, `test_evaluation_hard_fail.py` +422, this report +161 lines.
New-file `--no-index --check` reports no whitespace errors (exit 1 for new-file
differences); Git emits only the configured future LF-to-CRLF conversion warning.

Verdict: **RG-07B-02 READY FOR INDEPENDENT REVIEW**.
