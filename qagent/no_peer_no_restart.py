"""Evaluate the no-peer-information condition without stagnation restart masking."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from . import memory_ablation
from .core import ROOT, dump, prepare_runtime, tasks
from .private_extensions import Intervention, OWN, PEERS, LEDGER, split_prompt


def no_peer_prompt(prompt, framework):
    prefix, own, _peers, ledger = split_prompt(prompt)
    own_ledger = [row for row in ledger if row['framework'] == framework]
    return prefix + OWN + json.dumps(own) + PEERS + '[]' + LEDGER + json.dumps(own_ledger)


class NoPeerRepair(Intervention):
    def __init__(self, with_restart=False):
        super().__init__('restart' if with_restart else 'baseline')
        self.with_restart = with_restart

    def __call__(self, prompt, folder, schema):
        framework = folder.parent.name.rsplit('_', 1)[0]
        folder.mkdir(parents=True, exist_ok=True)
        raw = folder / 'model'
        if (raw / 'events.jsonl').exists() and not (raw / 'generation.json').exists():
            events = [json.loads(line) for line in (raw / 'events.jsonl').read_text().splitlines()
                      if line.strip()]
            message = "You've hit your usage limit."
            if (events and events[-1].get('type') == 'turn.failed'
                    and events[-1].get('error', {}).get('message', '').startswith(message)):
                archive = folder / 'failed_model_calls' / 'usage_limit_1'
                if archive.exists():
                    raise RuntimeError(f'repeated usage-limit failure for candidate: {folder}')
                archive.parent.mkdir(parents=True, exist_ok=True)
                raw.rename(archive)
            else:
                raise RuntimeError(f'unfinalized model call requires inspection: {raw}')
        result = super().__call__(no_peer_prompt(prompt, framework), folder, schema)
        result['peer_information'] = 'none'
        result['stagnation_restart'] = self.with_restart
        dump(folder / 'generation.json', result)
        return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', default='no_peer_no_restart_r1')
    p.add_argument('--initial-run', default='oneshot_astra_medium_r1')
    p.add_argument('--attempts', type=int, default=6)
    p.add_argument('--workers', type=int, default=6)
    p.add_argument('--with-restart', action='store_true',
                   help='Enable the published conditional stagnation masking policy.')
    a = p.parse_args()
    run = ROOT / 'runs' / a.run
    config = {**vars(a), 'model': 'gpt-6-astra', 'effort': 'medium'}
    if (run / 'config.json').exists():
        if json.loads((run / 'config.json').read_text()) != config:
            raise RuntimeError(f'run configuration differs: {run}')
    else:
        dump(run / 'config.json', config)
    prepare_runtime()
    memory_ablation.generate = NoPeerRepair(a.with_restart)
    all_tasks = tasks()
    families = [[t for t in all_tasks if t['task_id'] == tid]
                for tid in sorted({t['task_id'] for t in all_tasks})]
    results, errors = [], []
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        fs = {pool.submit(memory_ablation.solve_family, family, run, a.initial_run,
                          a.attempts, 'private'): family[0]['task_id'] for family in families}
        for future in as_completed(fs):
            tid = fs[future]
            try:
                rows = future.result()
                results.extend(rows)
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
