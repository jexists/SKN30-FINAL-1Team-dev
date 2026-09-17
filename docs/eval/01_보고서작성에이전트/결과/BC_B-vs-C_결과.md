# Linked B/C frozen Judge — complete

Persistent output: `/Users/j3s30p/playdata/project/FINAL-report-evaluation-dataset/backend/evaluation_results/reports/BC-linked-20260908`.
Final unchanged comparison: `comparisons/cb66010f7fd2efc02424bb63218e7c41e3a0fce2ad9324e8b0d6d975feb7e19d.json` and `cb66010f7fd2efc02424bb63218e7c41e3a0fce2ad9324e8b0d6d975feb7e19d.md`.

Judge A = **B-linked archived control**; Judge B = **C-linked current source candidate**. X/Y blindness and reversed order remain unchanged. gpt-5.6-luna; concurrency4; v2/source-id-string-v3; weights40/20/20/15/5. Provider defaults remain unspecified exactly as frozen.

Prepare and existing checker passed:209 jobs =105 absolute (53 control +52 candidate) +104 pair-order jobs for52 common generated outputs. Fixed daily01/meeting15 pilot8/8 passed; root authorized the remaining201 in `CONTINUE.json` based on protocol/transport, independent of scores. The same plan/config/helper/loader remained fixed.

All209 first attempts returned:204 validated,5 review_required;0 execution errors,0 interruptions,0 retries,0 remaining. Returned model metadata:209 gpt-5.6-luna. The unchanged summarizer completed; request byte equality, canonical hashes, raw-content/usage equality and exact local result revalidation passed. Final existing checker passed. No new audit gate or evaluator mutation was introduced after the final root note.

These are weighted rubric scores out of100, not measured accuracy. Means use only the frozen summarizer’s accepted scored cohorts; invalid returns are neither zero scores nor retries. Valid degraded generation stays eligible (B3, C5).

| Kind | B control scored / generated | B mean | C candidate scored / generated | C mean | Common scored / generated | Common B mean | Common C mean |
|---|---:|---:|---:|---:|---:|---:|---:|
| all | 51/53 | 96.3971 | 51/52 | 94.0441 | 50/52 | 96.3250 | 93.9250 |
| meeting | 36/36 | 97.8125 | 36/36 | 93.8542 | 36/36 | 97.8125 | 93.8542 |
| daily | 11/12 | 94.3182 | 11/12 | 96.9318 | 10/12 | 93.7500 | 96.6250 |
| weekly | 4/4 | 89.3750 | 4/4 | 87.8125 | 4/4 | 89.3750 | 87.8125 |
| monthly | 0/1 | — | 0/0 | — | 0/0 | — | — |

The50-case common scored cohort excludes daily02/daily08 because one absolute return failed validation. C monthly01 failed generation at the unchanged199,604/180,000-character input guard: no candidate absolute request, no pair and no fabricated quality score. Its36 input meetings remain evidence, with no generated monthly output. B monthly01 retained its one absolute request, but that returned source_authority failure is also unscored.

| Kind | B wins | C wins | Ties | Review required | Order disagreements | Ineligible |
|---|---:|---:|---:|---:|---:|---:|
| all | 13 | 11 | 4 | 24 | 22 | 1 |
| meeting | 11 | 9 | 4 | 12 | 11 | 0 |
| daily | 2 | 1 | 0 | 9 | 8 | 0 |
| weekly | 0 | 1 | 0 | 3 | 3 | 0 |
| monthly | 0 | 0 | 0 | 0 | 0 | 1 |

Of52 eligible pairs,28 reconcile and24 require review:22 order disagreements plus2 invalid pair returns; both_unsuitable0. Disagreements remain disagreements, never ties. Exact mapped verdicts are in `full-evidence.json` and the existing comparison.

Returned validation failures (all ValueError; raw text and returned usage preserved):

| Case | Task / visible role or X/Y mapping | Exact validation code |
|---|---|---|
| daily02 | absolute: B control | `source_authority` |
| daily08 | absolute: C candidate | `inherited_truth_and_input_evidence` |
| daily10 | pair: {"X": "B", "Y": "A"} | `report_passages_required` |
| meeting12 | pair: {"X": "A", "Y": "B"} | `report_passages_required` |
| monthly01 | absolute: B control | `source_authority` |

Returned Judge usage across all209 attempts: **8,387,313 input +263,377 output =8,650,690 total tokens**. Unknown usage records0; no unreturned or uncertain attempts. This is returned usage, not a billing or speed claim.

All plan/payloads, raw unmodified LangChain AIMessage JSON (not HTTP wire envelopes), attached exact quotes, scores, reasons, pair verdicts, failures and usage remain under `requests/`, `calls/`, `comparisons/`. Preflight holds copied frozen evaluator/checker, private loader, helper/config, rubric, protocol/readiness, pilot/continuation and execution evidence. Exact per-call hashes are in `full-evidence.json`; final file hashes are in `artifact_hashes.json`.

Plan SHA-256: `f0ff5c4d5c00fc2099c5060ef18b198fa891ffb42334279fd4836e39b7bd5201`  
Execution config SHA-256: `388c3f51e73a52dd1b55a4a83e819a9c181d0f3721a5c2959aa7f073a8668662`  
Helper SHA-256: `0ce041176f5c1b16bf09463fe1e69feb0eb23868d3c27d1aa96d798e0d04997d`  
Private loader SHA-256: `8d9e7a8af50ba7ffdc8ac1a3725d220d52f6c1941930c0a671d460ea4d4108dc`

Owned pilot/full wrapper and loader PIDs 60359, 60360, 60622, 60624 ended; every listed prepare/check/summarize/verification command exited0. No live subprocess remains. Frozen source/helper hashes and246 owned immutable prepared/pilot files remain unchanged. Final hashes were captured after logs/outputs closed.

One connected synthetic53-case story, independently generated meeting variation, shared writer/Judge model and mechanically simulated pending HITL remain limitations. Source quote existence is not semantic truth; frozen weekly guidance/source-contract issues and independent audit annotations remain separate from unchanged scores. Root interprets the final comparison; no causal, production, billing, speed or generalization conclusion is made. No source/runner/seed/gold/historical result, supervisor result report or semantic finding was edited.
