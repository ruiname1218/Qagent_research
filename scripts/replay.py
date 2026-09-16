"""Re-evaluate saved final candidates. Never invokes an LLM or alters results/."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from qagent.core import ROOT, dump, tasks, prepare_runtime, evaluate

def main():
    p=argparse.ArgumentParser(description=__doc__)
    choices=['oneshot','feedback','restart','no_peer_restart_r1','no_peer_restart_r2','no_peer_no_restart']
    p.add_argument('condition',choices=choices)
    p.add_argument('--ids',default='')
    p.add_argument('--workers',type=int,default=3)
    p.add_argument('--output',required=True,help='New directory outside the immutable results directory')
    a=p.parse_args(); dest=Path(a.output).resolve()
    if dest.exists() or dest==ROOT/'results' or ROOT/'results' in dest.parents:
        p.error('output must be a new directory outside results/')
    if a.condition == 'no_peer_no_restart':
        rows=json.loads((ROOT/'results/ablation/no_peer_no_restart_results.json').read_text())['tasks']
    elif a.condition.startswith('no_peer_restart_'):
        evidence=json.loads((ROOT/'results/ablation/no_peer_restart_full_results.json').read_text())
        run='no_peer_none_'+a.condition.rsplit('_',1)[1]
        rows=evidence['runs'][run]['tasks']
    else:
        rows=json.loads((ROOT/'results'/f'{a.condition}.json').read_text())
    if a.ids:
        ids=set(a.ids.split(',')); valid={r['task_id'] for r in rows}
        if not ids<=valid:p.error('unknown task ID')
        rows=[r for r in rows if r['task_id'] in ids]
    taskmap={t['framework']+'_'+t['task_id']:t for t in tasks()}
    prepare_runtime(); dest.mkdir(parents=True)
    def work(row):
        result=evaluate(taskmap[row['key']],row['records'][-1]['generation']['code'])
        out={'key':row['key'],'original_passed':row['passed'],'evaluation':result}
        dump(dest/(row['key']+'.json'),out)
        return out
    with ThreadPoolExecutor(max_workers=a.workers) as pool: results=list(pool.map(work,rows))
    summary={'condition':a.condition,'cases':len(results),'passed':sum(r['evaluation']['passed'] for r in results),
        'changed':[r['key'] for r in results if r['original_passed']!=r['evaluation']['passed']],
        'infrastructure_errors':[r['key'] for r in results if r['evaluation'].get('infra_error')]}
    dump(dest/'summary.json',summary);print(json.dumps(summary,indent=2))
    if summary['infrastructure_errors']:raise SystemExit(1)

if __name__=='__main__':main()
