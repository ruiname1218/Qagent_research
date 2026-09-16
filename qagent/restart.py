"""One-call repair with conditional masking of own code and diagnosis."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from . import memory
from .core import ROOT, dump, generate, prepare_runtime, tasks
from .prompts import SCHEMA

OWN = '\nOwn previous attempts:\n'

PEERS = '\nLatest peer evidence:\n'

LEDGER = '\nShared hypothesis ledger:\n'

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
    if mode != 'restart':
        raise ValueError(mode)
    metadata['restart'] = stagnation(folder)
    if metadata['restart']['triggered']:
        prefix, own, peers, ledger = split_prompt(prompt)
        for row in own:
            row['code'] = '[withheld for this restart]'
        for row in ledger:
            row['diagnosis'] = {}
        prompt = prefix + OWN + json.dumps(own) + PEERS + json.dumps(peers) + LEDGER + json.dumps(ledger) + RESTART_POLICY
    return (prompt, schema, metadata)

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
        result = dict(generation, code=plan['code'], model_calls=1, intervention=metadata)
        (folder / 'answer.txt').write_text(json.dumps(plan, ensure_ascii=False))
        dump(folder / 'generation.json', result)
        return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', required=True)
    p.add_argument('--mode', choices=['restart'], default='restart')
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
    memory.generate = Intervention(a.mode)
    all_tasks = tasks()
    families = [[t for t in all_tasks if t['task_id'] == tid]
                for tid in sorted({t['task_id'] for t in all_tasks})]
    results, errors = [], []
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        fs = {pool.submit(memory.solve_family, family, run, a.initial_run, a.attempts, 'private'):
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
