"""Targeted post-hoc inspection, not an inference-time tool or a scoring change."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from .core import ROOT, dump, tasks, prepare_runtime, evaluate
from .report import collect
from .ledger_audit import QPE_PROBE

GHZ_STRUCTURE = '''
qc=GHZ3_SWAPTEST()
diagnostic_result={'qubits':qc.num_qubits,'classical_bits':qc.num_clbits,
 'operations':dict(qc.count_ops()),'registers':[(r.name,r.size) for r in qc.qregs]}
'''

def main():
    registry=json.loads((ROOT/'reports/peer_code_ablation_registry.json').read_text())
    taskmap={t['framework']+'_'+t['task_id']:t for t in tasks()}
    prepare_runtime();jobs=[]
    for arm,run in registry['runs'].items():
        rows=collect(run)
        for key,probe in [('qiskit_25',QPE_PROBE),('qiskit_26',GHZ_STRUCTURE)]:
            assert key in rows,(arm,key)
            r=rows[key];jobs.append((arm,key,probe,r['records'][-1]['generation']['code'],r['passed']))
    def work(job):
        arm,key,probe,code,passed=job
        fingerprint=hashlib.sha256((code+'\n'+probe).encode()).hexdigest()
        path=ROOT/'reports/peer_code_semantic'/arm/(key+'.json')
        if path.exists():
            r=json.loads(path.read_text());assert r['artifact_probe_sha256']==fingerprint;return r
        result=evaluate(taskmap[key],code,probe=probe)
        assert not result.get('infra_error'),result
        row={'arm':arm,'key':key,'officially_accepted':passed,'artifact_probe_sha256':fingerprint,
            'probe':probe,'ran':result['ran'],'error':result.get('error'),
            'observations':json.loads(result['stdout']) if result['ran'] else None}
        dump(path,row);return row
    with ThreadPoolExecutor(max_workers=4) as pool:checks=list(pool.map(work,jobs))
    report={'purpose':'Post-hoc inspection of QPE controlled gate and GHZ comparison circuit structure; no model calls, no feedback or selection.',
        'limitations':'QPE probes one controlled base gate up to global phase; global phase still matters under control. GHZ inspects structure, not circuit equivalence. No exhaustive semantic correctness claim.',
        'expected':8,'completed':len(checks),'checks':checks}
    dump(ROOT/'reports/peer_code_semantic.json',report)
    print(json.dumps([{k:v for k,v in r.items() if k!='probe'} for r in checks],indent=2))

if __name__=='__main__':main()
