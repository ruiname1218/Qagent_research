# No SDK sharing: with and without stagnation reconsideration

| Condition | Accepted | Repetitions |
|---|---:|---:|
| No SDK sharing, reconsideration enabled | 103/126, 103/126 (81.7% each) | 2 |
| No SDK sharing, reconsideration disabled | 102/126 (81.0%) | 1 |

Full case-level evidence is bundled for all three trajectories. The two enabled
runs are in [`no_peer_restart_full_results.json`](../../results/ablation/no_peer_restart_full_results.json),
including every generated candidate, diagnostic note, evaluation and failed final
case. The disabled run is in
[`no_peer_no_restart_results.json`](../../results/ablation/no_peer_no_restart_results.json).
All three can be re-evaluated with `scripts/replay.py`.

The disabled run is `no_peer_no_restart_r1`. It reuses the same 126 initial
candidates and allows at most five repair calls and evaluations per case.
The model is GPT-6 Astra through Codex, reasoning effort medium. The original
private-diagnostic instructions, response schema, evaluation settings and SDK
order are retained. All task-specific peer prompt, code, output, errors,
acceptance and history are removed. Own code, feedback and diagnostic history
remain visible on every call; the stagnation intervention is disabled.

All 126 cases completed. There were 167 new successful model invocations, each
evaluated once. Sixteen invocations returned only usage-limit errors, without
candidates or usage events. Their raw logs were archived before retrying the
same candidate slots after access resumed. Completed candidates were reused.
This interruption means the run was not collected in a single uninterrupted batch.

The disabled trajectory, settings, source-input hashes and raw-file hashes are in
[`no_peer_no_restart_results.json`](../../results/ablation/no_peer_no_restart_results.json).
The export audit reconstructed every repair's own history from preceding records,
verified empty peer evidence and own-SDK-only ledger rows, checked unchanged own
diagnoses and code, verified absence of restart instructions, and checked completion
events, returned code, initial-candidate reuse and stopping budgets.
Sanitized raw events and prompts are bundled in
[`artifacts/raw_traces_sanitized.tar.gz`](../../artifacts/raw_traces_sanitized.tar.gz).
Unredacted source files remain in the experiment workspace at
`runs/no_peer_no_restart_r1/`.

The disabled run is new, while the two enabled runs are previous experiments.
They are not contemporaneous paired replications. A one-case difference with
unequal repetitions does not establish a stable or statistically confirmed benefit.
The metric is official benchmark acceptance, not proof of mathematical correctness.
