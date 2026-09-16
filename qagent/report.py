import argparse
import json
from pathlib import Path
from .core import ROOT, dump

def collect(name):
    return {p.parent.name:json.loads(p.read_text()) for p in (ROOT/'runs'/name).glob('*/result.json')}

def metrics(results):
    rows = list(results.values())
    usage = {}
    seconds = 0
    model_calls = 0
    for row in rows:
        for record in row['records']:
            generation=record['generation']
            model_calls += generation.get('model_calls', int(bool(generation.get('usage'))))
            seconds += generation.get('seconds',0)
            for k,v in generation.get('usage',{}).items():
                if isinstance(v,(int,float)):
                    usage[k]=usage.get(k,0)+v
    return {'completed':len(rows), 'passed':sum(r['passed'] for r in rows),
            'passed_by_5_generations':sum(any(a['evaluation']['passed'] for a in r['records'][:5]) for r in rows),
            'generations':sum(r['attempts'] for r in rows), 'usage':usage,
            'model_calls':model_calls,
            'sum_generation_seconds':seconds}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('runs',nargs='+')
    p.add_argument('--output',default='reports/latest.json')
    a=p.parse_args()
    data={name:collect(name) for name in a.runs}
    common=set.intersection(*(set(d) for d in data.values())) if data else set()
    report={'all_available':{name:metrics(d) for name,d in data.items()},
            'paired_keys':sorted(common),
            'paired':{name:metrics({k:d[k] for k in common}) for name,d in data.items()},
            'outcomes':{k:{name:d[k]['passed'] for name,d in data.items()} for k in sorted(common)}}
    dump(ROOT/a.output,report)
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    main()
