"""Run from repository root with PYTHONPATH=. .venv/bin/python scripts/peer_code_vqe_probe.py."""
from pathlib import Path
import json,hashlib
from qagent.core import tasks,evaluate,dump,ROOT
probe='''
import numpy as np
original_minimize=minimize
checks=[]
def tracked_minimize(fun,x0,*args,**kwargs):
    initial=np.asarray(x0,dtype=float)
    shifted=initial.copy(); shifted[0]+=0.37
    before=[float(fun(initial)),float(fun(shifted))]
    result=original_minimize(fun,x0,*args,**kwargs)
    checks.append({'energy_at_initial_and_shifted':before,'parameter_change_norm':float(np.linalg.norm(np.asarray(result.x)-initial)),'iterations':int(result.nit)})
    return result
minimize=tracked_minimize
output=VQE_Z2([0.1,0.2,0.3,0.4])
diagnostic_result=checks
'''
taskmap={t['framework']+'_'+t['task_id']:t for t in tasks()}
checks=[]
for f in ['cirq','pennylane']:
 key=f+'_41'; row=json.loads((ROOT/'runs/peer_code_shared_r2'/key/'result.json').read_text());code=row['records'][-1]['generation']['code']
 result=evaluate(taskmap[key],code,probe=probe)
 checks.append({'key':key,'arm':'shared_r2','officially_accepted':row['passed'],'code_sha256':hashlib.sha256(code.encode()).hexdigest(),'probe':probe,'ran':result['ran'],'error':result.get('error'),'observations':json.loads(result['stdout']) if result['ran'] else None})
report={'purpose':'Post-hoc examination of the two accepted VQE gain cases; never fed to models.','interpretation':'Both accepted implementations interpret Z2 as Z squared = identity. An optimizer is called, but its objective is constant. The finite perturbation check below illustrates the consequence, not a complete VQE correctness proof.','checks':checks}
dump(ROOT/'reports/peer_code_vqe_check.json',report)
print(json.dumps(report,indent=2))
