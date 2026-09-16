| Condition | Passed | Accuracy | Calls* | Output tokens* |
|---|---:|---:|---:|---:|
| oneshot | 74/126 | 58.7% | 126 | 35,773 |
| feedback | 99/126 | 78.6% | 308 | 107,287 |
| restart | 108/126 | 85.7% | 263 | 126,467 |

*Includes the shared initial 126 calls in each row; these were generated once.
These are selected development trajectories, not independent repeated trials.

Additional no-sharing conditions (same initial candidates, maximum five repairs):

| Condition | Passed | Acceptance rate | Repetitions |
|---|---:|---:|---:|
| No SDK sharing; stagnation reconsideration enabled | 103/126, 103/126 | 81.7%, 81.7% | 2 |
| No SDK sharing; stagnation reconsideration disabled | 102/126 | 81.0% | 1 |

The enabled runs are prior experiments; the disabled run is new. Unequal repetitions and a one-case gap do not establish a stable masking benefit.
Complete case-level trajectories, audits and replay commands: [Evidence inventory](../docs/EVIDENCE.md).
