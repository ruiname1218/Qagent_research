# Provenance and release transformations

## Selected sources

| Public condition | Experimental source |
|---|---|
| oneshot | `oneshot_astra_medium_r1` |
| feedback | `feedback_full126_r1` |
| restart | `private_extension_restart_r1` |
| no peer information, restart enabled (run 1) | `no_peer_none_r1` |
| no peer information, restart enabled (run 2) | `no_peer_none_r2` |
| no peer information, restart disabled | `no_peer_no_restart_r1` |

The feedback source combines disjoint task partitions recursively. Each original
call's actual source run is recorded in `results/provenance.json`. The exporter
checked all 445 distinct source calls (697 entries counting reused initials) against
completed model events, token usage and original prompt hashes. Raw responses were
not regenerated for this release.

## Included and omitted data

Included: every case's generated code, explicit structured diagnosis/contract/hypothesis,
evaluations, acceptance, attempt index, usage and source hashes. All selected failures
are retained. Canonical solutions/distributions, benchmark prompt files, Codex auth,
CLI session identifiers and unredacted machine-specific logs are not bundled. Sanitized
event and stderr files are included in the trace archive. Upstream prompts are fetched
separately at the pinned commit.

User home paths in evaluation tracebacks are replaced with `[LOCAL_PATH]`. Original
prompt hashes and original record/event/answer hashes remain in provenance. A separate
`public_prompt_sha256` records the hash of the original input after the same structured
redaction. `check_trace_parity.py` reconstructs these inputs from released records and
upstream prompts, without querying the model. Original code strings are preserved.

The public dataset is a curated trace export. Its sanitized raw trace bundle contains
the prompt, answer, event, schema, generation and stderr files for every comparison-table
record, while local paths and Codex thread identifiers are removed. Local checks establish
internal consistency and correspondence to the provided hashes; this is not an independent
cryptographic attestation by the hosted model provider. Unredacted source logs remain in
the source experimental workspace.

## Code extraction

`docs/source_manifest.json` maps extracted modules to source files and hashes.
Core execution/scoring and worker files are copied unchanged. Prompt constants are
preserved. Unused experimental policies and CLI modes were removed; internal modules
were renamed. Public baseline resume checks reject changed settings, and failures
return a nonzero exit status. These operational changes do not alter model prompts.
The release was checked by reconstructing all initial and repair prompts.

## Transport recovery

One restart call, `pennylane_08` attempt 2, completed successfully after a WebSocket-to-HTTPS
fallback notice. The experimental validator mistook the notice for a tool call.
The already-completed answer was recovered from unchanged raw files and evaluated
once; no resampling or additional model call occurred. Its duration was estimated
from file timestamps; token usage is from the completed event. An isolated failed-family
resumer temporarily allowed up to seven families instead of six. No within-family
ordering or budget changed. This artifact does not compare wall-clock runtimes.
The public frozen backend retains the original strict event validator: a similar
transport event in a new run causes an explicit failure, not an automatic retry.

## Validation levels

1. `audit_results.py`: file integrity, full coverage, common initial codes/outputs,
   stop-on-accept rules, limits and cost aggregation; standard library only.
2. Unit tests: private-note filtering, masking, call budgets, stopping and resume.
3. `check_trace_parity.py`: 445 reconstructed inputs against redacted-source hashes;
   requires upstream prompts and NumPy, no model execution.
4. `audit_no_peer_restart_full.py` and `audit_no_peer_no_restart.py`: complete
   code/evaluation histories, input hashes, visibility metadata and repair budgets
   for the three no-sharing trajectories in the comparison table.
5. `replay.py`: actual sandboxed execution and official re-scoring of saved final
   candidates. Release smoke validation covered task01 in all three SDKs for the
   selected restart trajectory and repaired `cirq_03` for each no-sharing trajectory.
6. `python -m qagent ...`: new stochastic model generation, a different experiment.

## Additional ablation records

`results/ablation/` contains the preregistration, aggregate reports, paired
case-level outcomes, targeted post-hoc checks, and a checksum manifest for the
code-visibility and all-peer-information comparisons. It additionally contains
complete generated-code, diagnosis and evaluation histories for both 103/126
no-peer restart runs and the 102/126 no-peer/no-restart run. The experimental
workspace retains the raw model folders; unredacted event streams are not bundled.
Run `scripts/audit_ablation_results.py` for all eight information-ablation outcome
sets and the two dedicated full-evidence audits for the three no-sharing trajectories
used in the comparison table.
