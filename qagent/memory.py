"""Round-robin SDK repair with private diagnostic notes."""
import json
from .core import ROOT, dump, evaluate, feedback, generate
from .prompts import POLICY as BASE_POLICY, SCHEMA, LEDGER_POLICY

def memory_view(ledger, framework, mode='private'):
    assert mode == 'private'
    view = json.loads(json.dumps(ledger))
    for row in view:
        if row['framework'] != framework:
            row['diagnosis'] = {}
    return json.dumps(view)

def solve_family(family, run, initial_run, attempts, mode):
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
                        '\nShared hypothesis ledger:\n'+memory_view(ledger,framework,mode))
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
