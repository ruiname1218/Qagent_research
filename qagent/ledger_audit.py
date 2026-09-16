"""Post-hoc prompt-derived checks; never fed back into the agent's attempts."""
import json
from .core import ROOT, tasks, dump, evaluate
from .report import collect

QPE_PROBE = '''
import numpy as np
from qiskit.quantum_info import Operator
qc=qpe_grover00_gate(3)
controlled=next(x.operation for x in qc.data if hasattr(x.operation,'base_gate') and x.operation.num_qubits==3)
actual=Operator(controlled.base_gate).data
s=np.ones(4)/2
D=2*np.outer(s,s)-np.eye(4)
O=np.diag([-1,1,1,1])
G=D@O
diagnostic_result={'controlled_gate':controlled.name,
 'distance_to_Grover':float(np.linalg.norm(actual-G)),
 'distance_to_negative_Grover':float(np.linalg.norm(actual+G)),
 'distance_to_negative_diffusion':float(np.linalg.norm(actual+D)),
 'same_Grover_up_to_global_phase':bool(np.isclose(abs(np.trace(actual.conj().T@G)),4))}
'''

SWAP_PROBE = '''
import numpy as np
import pennylane as qml
observations=[]
for theta in [0.,np.pi/4,np.pi/2,3*np.pi/4,np.pi]:
    def preparation():
        qml.RY(theta,wires=0)
    samples=np.asarray(swaptest_zaxis(preparation)).reshape(-1)
    predicted=(1-np.cos(theta/2)**2)/2
    measured=float(np.mean(samples))
    observations.append({'theta':theta,'expected_p1':float(predicted),
                         'observed_p1':measured,'within_0_06':bool(abs(measured-predicted)<.06)})
diagnostic_result=observations
'''


def main():
    all_tasks = {t['framework']+'_'+t['task_id']: t for t in tasks()}
    rows = collect('deliberative_pilot18_r1')
    report = {'purpose': 'Post-hoc specification checks; no feedback into solving', 'checks': {}}
    for key, probe in [('qiskit_25', QPE_PROBE), ('pennylane_06', SWAP_PROBE)]:
        code = rows[key]['records'][-1]['generation']['code']
        result = evaluate(all_tasks[key], code, probe=probe)
        report['checks'][key] = {'probe': probe, 'ran': result['ran'],
                                'error': result.get('error'),
                                'observations': json.loads(result['stdout']) if result['ran'] else None}
    dump(ROOT/'reports/deliberative_semantic_audit.json', report)
    print(report)


if __name__ == '__main__':
    main()
