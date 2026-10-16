# Verified LLM interface output measurements

Correctness gates and output sizes are independent. Negative savings mean more output.
Python 3.12.15; tokenizer cl100k_base; tiktoken 0.14.0.

## Correctness

Full suite: 1,083 passed; 0 failed; 0 errors; 0 skipped.

| Scenario / seed | Accepted actions | Guelph / Ghibelline actions | Lookups | Tactical elections | Raw menu entries reconstructed | Endpoint |
|---|---:|---:|---:|---:|---:|---|
| A / 11 | 125 | 72 / 53 | 206 | 4 | 834 | Turn 2; draw |
| C / 11 | 223 | 104 / 119 | 368 | 0 | 1,613 | Turn 8; guelph |
| F / 20261012 | 1,580 | 801 / 779 | 2,891 | 56 | 26,421 | Turn 14; guelph |

Every selected action ran in independent direct and interface states with identical results/state; all post-action invariants passed. Full menu pages reconstructed all original entries at every measured position. All elections in the direct control were explicitly chosen by its callback, not silently replaced by interface defaults.

## Named-tokenizer counts

| Scenario | Old truncated/full menu | Equivalent facts/formatted full menu | Equivalent facts/compact full menu | New including all lookup results | Savings vs formatted | Savings vs compact | Model requests + selections (additional) |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 131,104 | 338,914 | 316,525 | 322,380 | 4.88% | -1.85% | 10,792 |
| C | 289,424 | 726,429 | 681,905 | 691,228 | 4.85% | -1.37% | 19,791 |
| F | 4,141,448 | 8,269,331 | 7,436,466 | 5,985,042 | 27.62% | 19.52% | 133,672 |

## Character counts

| Scenario | Old truncated/full menu | Equivalent facts/formatted full menu | Equivalent facts/compact full menu | New including all lookup results | Savings vs formatted | Savings vs compact | Model requests + selections (additional) |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 372,914 | 1,116,799 | 1,068,834 | 1,077,263 | 3.54% | -0.79% | 28,913 |
| C | 813,473 | 2,350,199 | 2,252,702 | 2,261,862 | 3.76% | -0.41% | 51,838 |
| F | 11,828,244 | 25,838,878 | 23,896,355 | 19,167,508 | 25.82% | 19.79% | 369,508 |

## Exhaustive reads and scope

| Scenario | Reading every menu page: characters | Reading every menu page: tokens |
|---|---:|---:|
| A | 234,196 | 75851 |
| C | 473,445 | 152973 |
| F | 8,738,081 | 2867999 |

Deterministic real games; full chosen-category pages plus relevant full Lord/board records and first-use action/card references; all requests counted.

Counts sum each serialized payload separately, including extra fact/reference reads, action pages, reaction views and tactical choices. Request/selection traffic is shown separately, not silently omitted from an API-cost claim. The raw detailed JSON includes exact UTF-8 counts too.

The old documented prompt omitted facts and live elections. It is not a correctness-equivalent target; the new complete path can be substantially larger. Formatting and pagination controls above keep the same essential facts and additional full-detail reads. No result is called a saving by ignoring extra lookup outputs.

- Not a live LLM behavior or quality evaluation.
- The legacy prompt omitted information and within-combat choices; it is NOT a correctness-equivalent baseline.
- Equivalent-information controls include the same essential facts, all additional fact/reference reads, and every tactical choice. Formatted and compact full-menu controls are separate.
- The deterministic measurement policy caches static references after first use per faction. A fresh-context model may need additional repeated reads; this is not a live-provider measurement.
- Exhaustively paging the menu can cost more than one full-menu payload.
- Output savings are not provider billing savings; conversation resends, system prompts and caching differ.

See `LLM_INTERFACE_CHANGES.md` and `LLM_PLAY_GUIDE.md`. Reproduce with `PYTHONPATH=src python benchmarks/interface_output.py --tokens --out interface-output.json`.
