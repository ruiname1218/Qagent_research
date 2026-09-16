"""Single-call repair architectures on the highest-scoring policy, private notes only."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import hashlib
import json
from . import memory_ablation
from .core import ROOT, dump, generate, prepare_runtime, tasks
from .deliberative import SCHEMA

OWN = '\nOwn previous attempts:\n'
PEERS = '\nLatest peer evidence:\n'
LEDGER = '\nShared hypothesis ledger:\n'
MODES = ('baseline', 'patch', 'contrast', 'restart')

PATCH_SCHEMA = {'type': 'object', 'properties': {
    **{k: {'type': 'string'} for k in ('diagnosis', 'contract', 'hypothesis')},
    'edit_mode': {'type': 'string', 'enum': ['edit', 'replace']},
    'edits': {'type': 'array', 'maxItems': 12, 'items': {
        'type': 'object', 'properties': {'old': {'type': 'string'}, 'new': {'type': 'string'}},
        'required': ['old', 'new'], 'additionalProperties': False}},
    'replacement_code': {'type': 'string'}},
    'required': ['diagnosis', 'contract', 'hypothesis', 'edit_mode', 'edits', 'replacement_code'],
    'additionalProperties': False}
CONTRAST_SCHEMA = copy.deepcopy(SCHEMA)
CONTRAST_SCHEMA['properties']['alternatives'] = {'type': 'array', 'minItems': 2, 'maxItems': 2,
    'items': {'type': 'object', 'properties': {k: {'type': 'string'} for k in
        ('cause', 'supporting_evidence', 'counterevidence', 'change', 'predicted_effect')},
        'required': ['cause', 'supporting_evidence', 'counterevidence', 'change', 'predicted_effect'],
        'additionalProperties': False}}
CONTRAST_SCHEMA['properties']['selected'] = {'type': 'integer', 'enum': [0, 1]}
CONTRAST_SCHEMA['required'] += ['alternatives', 'selected']

PATCH_POLICY = '''
REPAIR OUTPUT INTERVENTION: Return the provided edit schema instead of the earlier
code field. There is still exactly one candidate, one model call and one evaluation.
Prefer precise edits to your latest own code when only a local defect is supported.
For edit_mode="edit", set replacement_code="" and give up to 12 ordered exact
old/new replacements. Each old text must be nonempty and occur EXACTLY ONCE in the
current code at that edit step. Copy anchors literally, including whitespace.
The host applies edits to the latest own candidate below, in order, atomically.
If the algorithm/interface needs substantial reconstruction, use edit_mode="replace",
edits=[], and provide a complete module in replacement_code. Select this explicitly;
there is no automatic fallback or free retry for invalid edits. Describe the reason
for the chosen scope in diagnosis. Preserve justified working portions, but do not
protect an incorrect algorithm merely to keep the diff small.
'''
CONTRAST_POLICY = '''
CAUSAL COMPARISON INTERVENTION: Before selecting a repair, state exactly two distinct
plausible explanations of the observed failure in alternatives. For each give the
observed supporting evidence, counterevidence or missing evidence, the specific
code/semantic change it would require, and its predicted observable effect.
Select one using selected=0 or 1 and implement ONLY that repair in the single code
candidate. When a traceback identifies the problem, one alternative may be ruled
out; do not invent uncertainty or change the quantum algorithm unnecessarily.
Distinguish observationally indistinguishable hypotheses from refuted ones. For
semantic failures compare genuinely different causal explanations, not stylistic
rewrites. Predictions and peer agreement are not observations or proof. There is
no additional execution, model call or candidate portfolio. Keep entries concise.
'''
RESTART_POLICY = '''
STAGNATION RESTART: Your last two executions were rejected and had output L1
distance at most 0.02. This is a signal to reconsider the approach, not proof
that the two programs implement the same unitary. For this repair the host has
withheld your old code and diagnostic notes to reduce anchoring. Your observed
feedback and latest peer code/results remain available. Derive a fresh native
implementation from the original task. Reconsider unsupported assumptions instead
of reconstructing an old candidate from memory. Preserve the specified operation,
inputs, gate restrictions and output interface. No extra call or evaluation.
'''

def split_prompt(prompt):
    prefix, rest = prompt.split(OWN, 1)
    own, rest = rest.split(PEERS, 1)
    peers, ledger = rest.split(LEDGER, 1)
    return prefix, json.loads(own), json.loads(peers), json.loads(ledger)

def apply_edits(base, answer):
    if answer['edit_mode'] == 'replace':
        if answer['edits'] or not answer['replacement_code'].strip():
            raise ValueError('replace requires empty edits and a nonempty complete module')
        return answer['replacement_code']
    if answer['edit_mode'] != 'edit' or answer['replacement_code']:
        raise ValueError('edit requires empty replacement_code')
    if len(answer['edits']) > 12:
        raise ValueError('at most 12 edits allowed')
    candidate = base
    for index, edit in enumerate(answer['edits']):
        old = edit['old']
        if not old or candidate.count(old) != 1:
            raise ValueError(f'edit {index}: old anchor must be nonempty and occur exactly once')
        candidate = candidate.replace(old, edit['new'], 1)
    return candidate

def stagnation(folder):
    n = int(folder.name.split('_')[-1])
    if n < 3:
        return {'triggered': False, 'reason': 'fewer than two prior attempts'}
    evaluations = [json.loads((folder.parent / f'attempt_{i}/record.json').read_text())['evaluation']
                   for i in (n - 2, n - 1)]
    if not all(e['ran'] and not e['passed'] for e in evaluations):
        return {'triggered': False, 'reason': 'last two are not execution-successful rejections'}
    a, b = [e.get('output') for e in evaluations]
    if not isinstance(a, list) or not isinstance(b, list) or len(a) != len(b):
        return {'triggered': False, 'reason': 'outputs not comparable'}
    distance = sum(abs(float(x) - float(y)) for x, y in zip(a, b))
    return {'triggered': distance <= .02, 'l1_distance': distance, 'threshold': .02}

def intervention_input(mode, prompt, schema, folder):
    metadata = {'mode': mode}
    if mode == 'baseline':
        return prompt, schema, metadata
    if mode == 'patch':
        return prompt + PATCH_POLICY, PATCH_SCHEMA, metadata
    if mode == 'contrast':
        return prompt + CONTRAST_POLICY, CONTRAST_SCHEMA, metadata
    if mode != 'restart':
        raise ValueError(mode)
    metadata['restart'] = stagnation(folder)
    if metadata['restart']['triggered']:
        prefix, own, peers, ledger = split_prompt(prompt)
        for row in own:
            row['code'] = '[withheld for this restart]'
        for row in ledger:
            row['diagnosis'] = {}
        prompt = (prefix + OWN + json.dumps(own) + PEERS + json.dumps(peers) +
                  LEDGER + json.dumps(ledger) + RESTART_POLICY)
    return prompt, schema, metadata

class Intervention:
    def __init__(self, mode):
        self.mode = mode

    def __call__(self, prompt, folder, schema):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'base_prompt.txt').write_text(prompt)
        actual, output_schema, metadata = intervention_input(self.mode, prompt, schema, folder)
        raw = folder / 'model'
        if (raw / 'generation.json').exists():
            generation = json.loads((raw / 'generation.json').read_text())
            assert generation['prompt_sha256'] == hashlib.sha256(actual.encode()).hexdigest()
            assert json.loads((raw / 'schema.json').read_text()) == output_schema
        else:
            generation = generate(actual, raw, schema=output_schema)
        answer = json.loads((raw / 'answer.txt').read_text())
        plan = {k: v for k, v in answer.items()}
        if self.mode == 'patch':
            base = split_prompt(prompt)[1][-1]['code']
            metadata['base_code_sha256'] = hashlib.sha256(base.encode()).hexdigest()
            metadata['edit_mode'] = answer['edit_mode']
            try:
                plan['code'] = apply_edits(base, answer)
            except ValueError as exc:
                # This consumes the one evaluation and surfaces through ordinary runtime feedback.
                message = 'Patch application failed: ' + str(exc)
                metadata['patch_error'] = message
                plan['code'] = 'raise ValueError(' + repr(message) + ')\n'
            plan = {k: plan[k] for k in SCHEMA['required']}
        result = dict(generation, code=plan['code'], model_calls=1, intervention=metadata)
        (folder / 'answer.txt').write_text(json.dumps(plan, ensure_ascii=False))
        dump(folder / 'generation.json', result)
        return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', required=True)
    p.add_argument('--mode', choices=MODES, required=True)
    p.add_argument('--initial-run', default='oneshot_astra_medium_r1')
    p.add_argument('--attempts', type=int, default=6)
    p.add_argument('--workers', type=int, default=6)
    a = p.parse_args()
    assert 2 <= a.attempts <= 6
    run = ROOT / 'runs' / a.run
    if (run / 'config.json').exists():
        assert json.loads((run / 'config.json').read_text()) == vars(a)
    dump(run / 'config.json', vars(a))
    prepare_runtime()
    memory_ablation.generate = Intervention(a.mode)
    all_tasks = tasks()
    families = [[t for t in all_tasks if t['task_id'] == tid]
                for tid in sorted({t['task_id'] for t in all_tasks})]
    results, errors = [], []
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        fs = {pool.submit(memory_ablation.solve_family, family, run, a.initial_run, a.attempts, 'private'):
              family[0]['task_id'] for family in families}
        for future in as_completed(fs):
            tid = fs[future]
            try:
                rows = future.result()
                results.extend(rows)
                (run / f'family_{tid}_error.json').unlink(missing_ok=True)
                print('family', tid, [(r['framework'], r['passed'], r['attempts']) for r in rows], flush=True)
            except Exception as exc:
                errors.append(tid)
                dump(run / f'family_{tid}_error.json', {'error': repr(exc)})
                print('family', tid, 'ERROR', repr(exc), flush=True)
            dump(run / 'summary.json', {'expected': 126, 'completed': len(results),
                 'passed': sum(r['passed'] for r in results), 'errors': errors,
                 'tasks': [{k: v for k, v in r.items() if k != 'records'} for r in results]})
    if errors:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
