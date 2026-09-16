# Results and interpretation

Complete case-level trajectories, audits and replay names for every score in the
comparison table are indexed in [Evidence inventory](EVIDENCE.md).

## Selected full trajectories

| Condition | Accepted | Rate | Qiskit | Cirq | PennyLane | Model calls* | Output tokens* |
|---|---:|---:|---:|---:|---:|---:|---:|
| One-shot | 74/126 | 58.7% | 27/42 | 24/42 | 23/42 | 126 | 35,773 |
| Feedback | 99/126 | 78.6% | 34/42 | 34/42 | 31/42 | 308 | 107,287 |
| Restart | 108/126 | 85.7% | 37/42 | 36/42 | 35/42 | 263 | 126,467 |

*Each row includes the shared 126 initial calls. Distinct calls across these three
trajectories total 445: 126 initial + 182 feedback repairs + 137 restart repairs.
Raw event usage was checked during export. Records, code, evaluations and hashes
are in `results/`; all intermediate failures are included.

The observed restart-minus-feedback difference is +9 cases (+7.1 percentage points).
Restart uses cross-SDK evidence and different repair instructions in addition to
conditional masking. This comparison does not isolate the masking mechanism.
Restart also used more output tokens than feedback despite fewer calls.

## Mechanism and repeatability

The restart trigger fired 22 times in the selected trajectory. In a development
comparison, the otherwise matching private-note architecture without masking scored
107/126. The added accepted case was `qiskit_26`, but masking **never triggered in
any SDK of task family 26**. Its first repair prompt and schema matched the control.
The one-case difference therefore does not demonstrate a causal benefit of masking.
The archived check is `results/mechanism_check.json`.

A predeclared follow-up generated fresh repairs from the same initial candidates
with frozen settings. It completed all 126 cases per condition: restart scored
**107/126**, and the control without masking scored **108/126**. These are supplementary
repeatability observations, not replacements selected into the main table. The
main 108/126 result is real but is not a demonstrated stable advantage of masking.
A case-level summary and source hashes are in `results/repeat_check.json`.

## Acceptance is not a proof of correctness

- The accepted task26 Qiskit circuit uses 21 qubits and fresh state copies for three
  local pairwise SWAP tests. This changes data sharing and does not verify a
  whole-state overlap implementation.
- In task25, some accepted QPE implementations do not use the standard Grover
  iterate as their controlled base operator; preparation-versus-iterate semantics
  need separate review.
- These observations are targeted checks, not a complete semantic audit of every
  accepted program. The primary metric is **official benchmark acceptance**.

## Limits on research claims

These are development results on one benchmark, with one shared initial generation
set and limited fresh-repair repetitions. Task families contain three correlated SDK
cases. No statistical superiority, held-out generalization, token-matched advantage,
or novelty of shared memory/diagnosis is established by this artifact.

A supported description is: “We implement and release a cross-SDK repair harness
with private diagnostic notes and conditional context masking, and report its
selected full-benchmark trajectories alongside one-shot and feedback baselines.”
A claim that masking caused the score improvement is unsupported by these results.

## Information sharing ablations

### No-sharing comparison with and without context masking

| Condition | Run 1 | Run 2 | Acceptance rate |
|---|---:|---:|---:|
| No SDK sharing; stagnation reconsideration enabled | 103/126 | 103/126 | 81.7% in each run |
| No SDK sharing; stagnation reconsideration disabled | 102/126 | Not run | 81.0% |

Both keep private own diagnostics, the common initial candidates and the five-repair
limit. The new disabled condition completed all 126 cases with 167 new repair calls
and evaluations. Sixteen empty usage-limit failures were preserved and retried after
access resumed; no returned candidate was discarded. Actual repair inputs were audited
for zero peer information and full own code/diagnostic history. This single new run
does not establish a causal or stable benefit from the one-case difference.
See [protocol and audit details](ablation/NO_PEER_RESTART_COMPARISON.md).

These follow-up experiments keep the private-diagnostic restart harness and remove
shared information in stages. They are separate from the selected 74/99/108 main
table and use fresh repairs from the same common initial candidates.

| Comparison | Run 1 | Run 2 | Mean |
|---|---:|---:|---:|
| Peer code visible | 107/126 | 110/126 | 108.5/126 |
| Peer code masked | 107/126 | 107/126 | 107.0/126 |
| Peer outcomes/history retained | 106/126 | 107/126 | 106.5/126 |
| All task-specific peer information removed | 103/126 | 103/126 | 103.0/126 |

For code visibility, the mean difference was +1.5 cases (+1.19 percentage points),
with a 42-family bootstrap 95% interval of [0.00, +3.17] points. For all peer
information, the mean difference was +3.5 cases (+2.78 percentage points), with
interval [0.00, +6.35]. The intervals include zero, so these experiments suggest
a relationship between cross-SDK evidence and acceptance in these trajectories,
but do not establish a statistically confirmed or generally superior method.
Both comparisons used two fresh repetitions and were not token-matched.

The all-information-hidden condition removed the other SDK's task prompt, full
code, acceptance, observed output, error, and historical rows from the actual model
input. The current SDK's own code, feedback, diagnosis, and restart logic were
retained. Audit reports and paired outcomes are in `results/ablation/`.

The extra accepted cases include output-shape and measurement-register changes.
Post-hoc checks found examples where official acceptance was closer to an expected
interface than to a mathematical solution, so these scores must be called
benchmark acceptance rather than semantic circuit correctness.
