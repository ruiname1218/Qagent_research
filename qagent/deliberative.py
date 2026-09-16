"""Shared hypothesis ledger with exactly one generation and evaluation per repair."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from .core import ROOT, FRAMEWORKS, dump, tasks, prepare_runtime, evaluate, feedback, generate
from .cross import POLICY as BASE_POLICY

SCHEMA = {'type': 'object', 'properties': {k: {'type': 'string'} for k in
          ('diagnosis', 'contract', 'hypothesis', 'code')},
          'required': ['diagnosis', 'contract', 'hypothesis', 'code'],
          'additionalProperties': False}

LEDGER_POLICY = '''
Maintain an explicit hypothesis ledger. Each call has exactly ONE code candidate
and ONE evaluation; do not generate a portfolio or call tools. Return JSON with
diagnosis, contract, hypothesis, code string fields. This JSON format overrides
the earlier request for a plain Python module.

Separate failure classes before writing code:
* Runtime/interface: fix the exact input/output representation from the traceback.
  Preserve the quantum operation and supplied inputs. Never replace an input with
  an assumed default. PennyLane inputs may be quantum functions or QNodes: handle
  their actual operation representation.
* Accepted peer: transfer its mathematical contract, including prepared state,
  parameter dependence, returned register, measurement map and relative phase.
  Preserve the target's working interface.
* All peers rejected: agreement is NOT validation. Consult the rejected-hypothesis
  ledger and investigate a DIFFERENT justified mathematical convention or task
  interpretation. Do not merely translate another rejected program.

For each hypothesis state which observed failure it explains, the exact semantic
change, and its predicted observable effect. Avoid several unrelated changes at
once. Separate the unitary from input preparation and readout: inverse transform,
controls, register size, ancilla inclusion and endian order are independent choices.
When the prompt leaves these open, enumerate plausible choices in the contract,
then select an untested one supported by the task. Peer output agreement is not
proof of success. Repeated similar rejected outputs require reconsidering an
untested specification assumption, not cosmetic rewrites or random reseeding.

Preserve gate restrictions and parameter dependence. Never prepare guessed outputs,
hardcode test values, fabricate samples, alter shots/seeds or replace the requested
quantum algorithm with a classical answer. Do not access references or evaluator
internals. The concise contract should specify input type, registers, prepared
state, mathematical unitary/ansatz, parameters, measured subset and output order.
Return a full executable native-framework implementation. No extra diagnostic run.
'''
def solve_family(family, run, initial_run, attempts):
    records={}
    for task in family:
        key=task['framework']+'_'+task['task_id']
        source=ROOT/'runs'/initial_run/key/'attempt_1/record.json'
        initial=json.loads(source.read_text())
        records[task['framework']]=[initial]
        dump(run/key/'attempt_1/record.json',initial)
    for round_number in range(2,attempts+1):
        for task in family:
            framework=task['framework']
            history=records[framework]
            if history[-1]['evaluation']['passed']:
                continue
            key=framework+'_'+task['task_id']
            folder=run/key/f'attempt_{round_number}'
            if (folder/'record.json').exists():
                record=json.loads((folder/'record.json').read_text())
            else:
                own=[{'code':r['generation']['code'],'feedback':feedback(r['evaluation'])} for r in history]
                peers=[]
                for peer in family:
                    if peer['framework']==framework:
                        continue
                    r=records[peer['framework']][-1]
                    peers.append({'framework':peer['framework'], 'prompt':peer['complete_prompt'],
                                  'accepted':r['evaluation']['passed'],
                                  'code':r['generation']['code'],
                                  'observed_output':r['evaluation'].get('output'),
                                  'error':r['evaluation'].get('error') if not r['evaluation']['ran'] else None})
                ledger=[]
                for peer in family:
                    for prior in records[peer['framework']]:
                        e=prior['evaluation']
                        ledger.append({'framework':peer['framework'],
                                       'attempt':prior['attempt'], 'accepted':e['passed'],
                                       'diagnosis':prior.get('plan',{}),
                                       'feedback':None if e['passed'] else feedback(e)})
                prompt=(task['complete_prompt']+'\n\n'+BASE_POLICY+LEDGER_POLICY+
                        '\nOwn previous attempts:\n'+json.dumps(own)+
                        '\nLatest peer evidence:\n'+json.dumps(peers)+
                        '\nShared hypothesis ledger:\n'+json.dumps(ledger))
                if (folder/'generation.json').exists():
                    generation=json.loads((folder/'generation.json').read_text())
                else:
                    generation=generate(prompt,folder,schema=SCHEMA)
                plan=json.loads((folder/'answer.txt').read_text())
                generation['code']=plan['code']
                dump(folder/'generation.json',generation)
                result=evaluate(task,generation['code'])
                if result.get('infra_error'):
                    raise RuntimeError(result['error'])
                record={'attempt':round_number,'generation':generation,'evaluation':result,
                        'accepted_peers':[p['framework'] for p in peers if p['accepted']]}
                record['plan']={k:v for k,v in plan.items() if k!='code'}
                dump(folder/'record.json',record)
            history.append(record)
    results=[]
    for task in family:
        key=task['framework']+'_'+task['task_id']
        history=records[task['framework']]
        result={'key':key,'task_id':task['task_id'],'framework':task['framework'],
                'category':task['category'],'passed':history[-1]['evaluation']['passed'],
                'attempts':len(history),'records':history}
        dump(run/key/'result.json',result)
        results.append(result)
    return results

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run',required=True)
    p.add_argument('--initial-run',required=True)
    p.add_argument('--ids',default='')
    p.add_argument('--attempts',type=int,default=6)
    p.add_argument('--workers',type=int,default=3)
    a=p.parse_args()
    prepare_runtime()
    run=ROOT/'runs'/a.run
    dump(run/'config.json',vars(a))
    all_tasks=tasks()
    ids=a.ids.split(',') if a.ids else sorted({t['task_id'] for t in all_tasks})
    families=[[t for t in all_tasks if t['task_id']==tid] for tid in ids]
    results=[]
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures={pool.submit(solve_family,f,run,a.initial_run,a.attempts):f[0]['task_id'] for f in families}
        for future in as_completed(futures):
            tid=futures[future]
            try:
                rows=future.result()
                results.extend(rows)
                print('family',tid,[(r['framework'],r['passed'],r['attempts']) for r in rows],flush=True)
            except Exception as exc:
                dump(run/f'family_{tid}_error.json',{'error':str(exc)})
                print('family',tid,'ERROR',str(exc),flush=True)
            dump(run/'summary.json',{'expected':len(families)*3,'completed':len(results),
                                    'passed':sum(r['passed'] for r in results),
                                    'tasks':[{k:v for k,v in r.items() if k!='records'} for r in results]})

if __name__=='__main__':
    main()
