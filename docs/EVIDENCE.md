# Evidence inventory

Every score in the main comparison table has a complete 126-case trajectory in
this artifact. A trajectory contains the initial candidate, every repair candidate,
diagnostic fields, execution result, official acceptance label and stopping count,
including unsuccessful final candidates.

| Table result | Complete trajectory | Offline audit | Replay condition |
|---|---|---|---|
| One-shot 74/126 | [`oneshot.json`](../results/oneshot.json) | `scripts/audit_results.py` | `oneshot` |
| Independent feedback 99/126 | [`feedback.json`](../results/feedback.json) | `scripts/audit_results.py` | `feedback` |
| Cross-SDK restart 108/126 | [`restart.json`](../results/restart.json) | `scripts/audit_results.py` | `restart` |
| No sharing, restart enabled 103/126 (run 1) | [`no_peer_restart_full_results.json`](../results/ablation/no_peer_restart_full_results.json) | `scripts/audit_no_peer_restart_full.py` | `no_peer_restart_r1` |
| No sharing, restart enabled 103/126 (run 2) | same file, separate run | same audit | `no_peer_restart_r2` |
| No sharing, restart disabled 102/126 | [`no_peer_no_restart_results.json`](../results/ablation/no_peer_no_restart_results.json) | `scripts/audit_no_peer_no_restart.py` | `no_peer_no_restart` |

The audits verify 126-case coverage, common initial candidates, maximum five
repairs, stopping after acceptance, saved code/evaluation consistency and model
metadata. The no-sharing exports additionally contain per-call prompt hashes,
raw-file hashes and visibility metadata. Their export-time audits inspected the
actual prompt text and raw completion events before bundling.

Run a saved final candidate against a separately installed, pinned QuanBench+
checkout with:

```bash
.venv/bin/python scripts/replay.py no_peer_restart_r1 --output runs/replay_no_peer_restart_r1
```

The sanitized prompt, structured-answer, event, schema, generation and stderr
files for all table trajectories are bundled in
[`artifacts/raw_traces_sanitized.tar.gz`](../artifacts/raw_traces_sanitized.tar.gz).
The archive removes local paths and Codex thread identifiers, and its manifest
maps every public file to a source hash. The release therefore supports trace
inspection, code-level replay and integrity checks. It remains distinct from a
cryptographic attestation by the hosted model provider.

QuanBench+ benchmark prompts, canonical data and reference implementation are
not redistributed. The setup instructions pin the upstream commit that readers
must fetch before replaying circuits.
