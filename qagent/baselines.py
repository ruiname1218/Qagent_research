import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import traceback
from .core import ROOT, dump, tasks, prepare_runtime, evaluate, generate, feedback

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['oneshot', 'feedback'])
    parser.add_argument('--run', required=True)
    parser.add_argument('--frameworks', default='qiskit,cirq,pennylane')
    parser.add_argument('--ids', default='')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--attempts', type=int, default=6)
    parser.add_argument('--initial-run')
    args = parser.parse_args()
    if not 1 <= args.attempts <= 6:
        parser.error('--attempts must be between 1 and 6')
    prepare_runtime()
    selected = [t for t in tasks() if t['framework'] in args.frameworks.split(',') and
                (not args.ids or t['task_id'] in args.ids.split(','))]
    run = ROOT/'runs'/args.run
    run.mkdir(parents=True, exist_ok=True)
    if (run/'config.json').exists():
        if json.loads((run/'config.json').read_text()) != vars(args):
            raise ValueError('Existing run has different settings')
    dump(run/'config.json', vars(args))
    def work(task):
        key = task['framework']+'_'+task['task_id']
        folder = run/key
        if (folder/'result.json').exists():
            return json.loads((folder/'result.json').read_text())
        records = []
        history = ''
        for i in range(args.attempts if args.mode == 'feedback' else 1):
            attempt = folder/f'attempt_{i+1}'
            if (attempt/'record.json').exists():
                record = json.loads((attempt/'record.json').read_text())
            else:
                if i == 0 and args.initial_run:
                    source = ROOT/'runs'/args.initial_run/key/'attempt_1/record.json'
                    generation = json.loads(source.read_text())['generation']
                elif (attempt/'generation.json').exists():
                    generation = json.loads((attempt/'generation.json').read_text())
                else:
                    prompt = task['complete_prompt']+history
                    generation = generate(prompt, attempt)
                result = evaluate(task, generation['code'])
                if result.get('infra_error'):
                    raise RuntimeError(result['error'])
                record = {'attempt': i+1, 'generation': generation, 'evaluation': result}
                dump(attempt/'record.json', record)
            records.append(record)
            if record['evaluation']['passed']:
                break
            history += '\n\nPrevious assistant code:\n'+record['generation']['code']+'\n\nUser feedback:\n'+feedback(record['evaluation'])
        final = {'key': key, 'task_id': task['task_id'], 'framework': task['framework'],
                 'category': task['category'], 'passed': records[-1]['evaluation']['passed'],
                 'attempts': len(records), 'records': records}
        dump(folder/'result.json', final)
        return final
    results = []
    errors = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(work,t):t for t in selected}
        for future in as_completed(futures):
            task = futures[future]
            try:
                result = future.result()
                results.append(result)
                print(f"{len(results)}/{len(selected)} {result['key']} passed={result['passed']} attempts={result['attempts']}", flush=True)
            except Exception:
                errors.append(task)
                error = traceback.format_exc()
                dump(run/(task['framework']+'_'+task['task_id'])/'error.json', {'error':error})
                print(error, flush=True)
            dump(run/'summary.json', {'expected':len(selected), 'completed':len(results),
                                      'passed':sum(r['passed'] for r in results),
                                      'tasks':[{k:v for k,v in r.items() if k!='records'} for r in results]})

    if errors:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
