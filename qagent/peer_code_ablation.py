"""Ablate only explicit peer-generated code in the frozen private-note restart agent."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import hashlib
import json
from . import memory_ablation
from .core import ROOT, dump, prepare_runtime, tasks
from .private_extensions import Intervention, OWN, PEERS, LEDGER, split_prompt
from .recover_transport_notice import recover

MASK = '[Peer-generated code withheld in this condition.]'

def visibility_input(prompt, visibility):
    if visibility == 'shared':
        return prompt
    if visibility != 'masked':
        raise ValueError(visibility)
    prefix, own, peers, ledger = split_prompt(prompt)
    for row in peers:
        row['code'] = MASK
    return prefix + OWN + json.dumps(own) + PEERS + json.dumps(peers) + LEDGER + json.dumps(ledger)

class CodeVisibility(Intervention):
    def __init__(self, visibility):
        super().__init__('restart')
        self.visibility = visibility

    def __call__(self, prompt, folder, schema):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'source_prompt.txt').write_text(prompt)
        raw = folder / 'model'
        if (raw / 'events.jsonl').exists() and not (raw / 'generation.json').exists():
            raise RuntimeError('Existing unfinalized raw call; inspect/recover it before resuming, never silently resample: ' + str(raw))
        result = super().__call__(visibility_input(prompt, self.visibility), folder, schema)
        result['peer_code_visibility'] = self.visibility
        dump(folder / 'generation.json', result)
        return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--visibility', choices=['shared', 'masked'], required=True)
    p.add_argument('--replicate', type=int, choices=[1, 2], required=True)
    a = p.parse_args()
    registry = json.loads((ROOT / 'reports/peer_code_ablation_registry.json').read_text())
    for name, digest in registry['source_sha256'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    arm = f'{a.visibility}_r{a.replicate}'
    config = dict(registry['settings'], visibility=a.visibility, replicate=a.replicate)
    run = ROOT / 'runs' / registry['runs'][arm]
    run.mkdir(parents=True, exist_ok=True)
    with (run / '.execution.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (run / 'config.json').exists():
            assert json.loads((run / 'config.json').read_text()) == config
        dump(run / 'config.json', config)
        prepare_runtime()
        memory_ablation.generate = CodeVisibility(a.visibility)
        all_tasks = tasks()
        families = [[t for t in all_tasks if t['task_id'] == tid] for tid in registry['ids']]
        def work(family):
            error_path = run / f"family_{family[0]['task_id']}_error.json"
            for _ in range(16):
                try:
                    rows = memory_ablation.solve_family(family, run, config['initial_run'], config['attempts'], 'private')
                    error_path.unlink(missing_ok=True)
                    return rows
                except Exception as exc:
                    dump(error_path, {'error': repr(exc)})
                    if 'exit=0, completed=True' not in str(exc):
                        raise
                    candidates = [folder for task in family for folder in
                        (run / (task['framework'] + '_' + task['task_id'])).glob('attempt_*/model')
                        if (folder / 'events.jsonl').exists() and not (folder / 'generation.json').exists()]
                    if len(candidates) != 1:
                        raise
                    # Validates the exact transport notice and completed raw response.
                    # Reuses that response without a new call or added worker.
                    recover(candidates[0])
            raise RuntimeError('Too many transport recoveries')
        results, errors = [], []
        with ThreadPoolExecutor(max_workers=config['workers']) as pool:
            fs = {pool.submit(work, family):family[0]['task_id'] for family in families}
            for future in as_completed(fs):
                tid = fs[future]
                try:
                    rows = future.result(); results.extend(rows)
                    print(arm, tid, [(r['framework'],r['passed'],r['attempts']) for r in rows], flush=True)
                except Exception as exc:
                    errors.append(tid);print(arm, tid, 'ERROR',repr(exc),flush=True)
                dump(run / 'summary.json', {'expected':126,'completed':len(results),
                    'passed':sum(r['passed'] for r in results),'errors':errors,
                    'tasks':[{k:v for k,v in r.items() if k!='records'} for r in results]})
        if errors:
            raise SystemExit(1)

if __name__ == '__main__':main()
