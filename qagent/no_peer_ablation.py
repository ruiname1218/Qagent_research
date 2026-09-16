"""Remove all task-specific peer evidence, including outcome history."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import hashlib
import json
from . import memory_ablation
from .core import ROOT, dump, prepare_runtime, tasks
from .private_extensions import Intervention, OWN, PEERS, LEDGER, split_prompt
from .peer_code_ablation import visibility_input
from .recover_transport_notice import recover
from .retry_empty_capacity import archive_capacity


def peer_information_input(prompt, framework, level):
    if level == 'outcomes':
        return visibility_input(prompt, 'masked')
    if level != 'none':
        raise ValueError(level)
    prefix, own, peers, ledger = split_prompt(prompt)
    own_ledger = [row for row in ledger if row['framework'] == framework]
    return prefix + OWN + json.dumps(own) + PEERS + '[]' + LEDGER + json.dumps(own_ledger)


class PeerInformation(Intervention):
    def __init__(self, level):
        super().__init__('restart')
        self.level = level

    def __call__(self, prompt, folder, schema):
        framework = folder.parent.name.rsplit('_', 1)[0]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'source_prompt.txt').write_text(prompt)
        raw = folder / 'model'
        if (raw / 'events.jsonl').exists() and not (raw / 'generation.json').exists():
            raise RuntimeError('Existing unfinalized raw call; inspect/recover before resuming: ' + str(raw))
        result = super().__call__(peer_information_input(prompt, framework, self.level), folder, schema)
        result['peer_information'] = self.level
        dump(folder / 'generation.json', result)
        return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--level', choices=['outcomes', 'none'], required=True)
    p.add_argument('--replicate', type=int, choices=[1, 2], required=True)
    a = p.parse_args()
    registry = json.loads((ROOT / 'reports/no_peer_registry.json').read_text())
    for name, digest in registry['source_sha256'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    arm = f'{a.level}_r{a.replicate}'
    config = dict(registry['settings'], level=a.level, replicate=a.replicate)
    run = ROOT / 'runs' / registry['runs'][arm]
    run.mkdir(parents=True, exist_ok=True)
    with (run / '.execution.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (run / 'config.json').exists():
            assert json.loads((run / 'config.json').read_text()) == config
        dump(run / 'config.json', config)
        prepare_runtime()
        memory_ablation.generate = PeerInformation(a.level)
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
                    candidates = [folder for task in family for folder in
                        (run / (task['framework'] + '_' + task['task_id'])).glob('attempt_*/model')
                        if (folder / 'events.jsonl').exists() and not (folder / 'generation.json').exists()]
                    if len(candidates) != 1:
                        raise
                    if 'exit=0, completed=True' in str(exc):
                        recover(candidates[0])
                    elif 'exit=1, completed=False' in str(exc):
                        archive_capacity(candidates[0])
                    else:
                        raise
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
