# Evaluation protocol

## Dataset and scoring

- QuanBench+ commit `2dfd1a863b13d3762a734ed96742adb39e65e34b`.
- 42 task families × Qiskit, Cirq and PennyLane = 126 cases.
- IDs 01–44, excluding 05 and 38. All cases, including failures, are retained.
- Upstream execution handlers, 1,000 shots, seed 1234, upstream KL acceptance
  threshold 0.05. The host computes acceptance from the canonical distribution.
- Reference code/distributions are not provided to the model. Runtime error
  messages and observed outputs are available; expected distributions and KL
  values are not included in model feedback.
- Upstream Python execution modules and their built-in test inputs are mounted in
  the circuit sandbox. Canonical JSON data, user files and network access are not.
  This is not a claim that execution is independent of benchmark-specific handlers.

## Shared model settings

Codex `gpt-6-astra`, reasoning effort `medium`, one candidate per call, tool use
and web search disabled, fresh temporary working directory. Exact invocation is in
`qagent/core.py`. Requests run independently; history is explicitly in the prompt.
The execution timeout is 90 seconds; the model subprocess timeout is 480 seconds.

## Conditions

1. **One-shot:** original complete prompt, one generation and one evaluation.
2. **Feedback:** the original prompt followed by all previous own code and failure
   feedback. One new call and one evaluation per repair. SDK cases are independent.
3. **Restart:** original prompt plus fixed policies in `qagent/prompts.py`; own
   code/feedback history; latest generated peer code, peer task prompt, observed
   output and acceptance; historical outcomes plus own diagnostic notes.
   Every call returns `diagnosis`, `contract`, `hypothesis`, `code`.

For restart, each task family is processed round-robin in Qiskit → Cirq → PennyLane
order. An earlier SDK's current-round result is visible to later SDKs. An accepted
SDK stops generating but its latest evidence remains visible. Other SDKs' diagnostic
notes are masked in every call. Historical prompt labels still say “Shared hypothesis
ledger”; the implementation filters its diagnostic fields to the current SDK.
The label is retained to preserve the measured prompt, not to imply shared diagnoses.

Before repair submission 3 or later, inspect the previous two own evaluations.
Trigger masking only if both ran successfully, both were rejected, their output
vectors are comparable, and their L1 distance is at most 0.02. Mask all own previous
code and diagnostic entries for this call. Retain own observed feedback and latest
peer code/results. Append the frozen restart instruction. A subsequent call can
restore own history if the trigger no longer holds. Similar sampled outputs do not
prove that two circuits are equivalent.

## Budgets and reuse

- Both repair conditions: initial + at most five repairs = six submissions per SDK;
  stop at the first accepted result. Restart has at most 18 submissions per family.
- One call and one official evaluation per repair; no auxiliary model calls,
  searches, candidate portfolios or inference-time diagnostic probes.
- The common initial codes and model usage come from one 126-call run. Feedback
  re-executed initial codes; restart reused the initial evaluation records.
  Their initial numerical outputs and acceptance labels match. One error traceback
  differs in worker line numbers; the actual feedback history is preserved.
- Equal submission caps do not mean equal information or token budgets. Restart
  uses the aligned tasks from three SDKs; feedback solves each independently.
- “Five repairs” differs from “five total generations.” At five total submissions,
  feedback scored 98 and restart 108. No direct claim about reproducing a paper's
  five-generation setting is made here.

## Trajectory selection

The released main table is a selected three-condition comparison from development.
Feedback combines disjoint task partitions; no case is selected from competing runs
by whether it passed. The restart trajectory is the first full run of that variant.
The benchmark was also used to develop/select the architecture. The release does
not claim these were the only experiments performed or a held-out final evaluation.
See RESULTS.md for the subsequent repetition and mechanism limitation.

## Additional information ablations

The release includes two further comparisons. The code-visibility experiment keeps
peer task prompts, outcomes, errors, acceptance and historical rows, but replaces
only each peer's latest full `code` field with a fixed marker in the masked
condition. The all-peer-information experiment compares that condition with a new
`none` condition: `Latest peer evidence` is `[]`, and the ledger contains only rows
for the current SDK. Thus the model receives no task-specific peer prompt, code,
outcome, error, acceptance, or peer history. The host retains source prompts and
internal metadata for audit, but they are not sent to the model.

Both conditions use the same private diagnostic/restart policy, common initial 126,
one call and one evaluation per repair, and at most five repairs. Each was run twice
for all 126 cases. The predeclared interpretation rule required a positive paired
difference in both repetitions and a family-bootstrap lower bound above zero before
calling the information effect consistently supported. Neither comparison met that
strict rule; see the ablation reports for exact scores, discordant cases, recovery
events, and limitations.
