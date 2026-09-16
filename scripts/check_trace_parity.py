"""Replay archived model responses to verify every repair prompt hash; no LLM calls.
Requires the pinned upstream prompts and NumPy. Does not execute circuits.
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from qagent.core import ROOT,dump,feedback,tasks
from qagent import memory
from qagent.restart import Intervention

def main():
    taskmap={t['framework']+'_'+t['task_id']:t for t in tasks()}
    initial=json.loads((ROOT/'results/oneshot.json').read_text())
    rows=json.loads((ROOT/'results/restart.json').read_text()); bykey={r['key']:r for r in rows}
    proof={(p['condition'],p['case'],p['attempt']):p for p in json.loads((ROOT/'results/provenance.json').read_text())}
    count=0; current={}
    def fake(prompt,folder,schema):
        nonlocal count
        key=folder.parent.parent.name; n=int(folder.parent.name.split('_')[-1]); r=bykey[key]['records'][n-1]
        assert hashlib.sha256(prompt.encode()).hexdigest()==proof[('restart',key,n)]['public_prompt_sha256'],(key,n)
        answer=dict(r['plan'],code=r['generation']['code'])
        assert set(answer)==set(schema['required'])
        folder.mkdir(parents=True,exist_ok=True);(folder/'answer.txt').write_text(json.dumps(answer));dump(folder/'schema.json',schema)
        g=dict(r['generation']);dump(folder/'generation.json',g)
        current.update(record=r);count+=1;return g
    def evaluate(task,code):
        r=current['record'];assert r['generation']['code']==code
        return r['evaluation']
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for r in initial:dump(root/'runs/initial'/r['key']/'attempt_1/record.json',r['records'][0])
        with patch('qagent.memory.ROOT',root),patch('qagent.restart.generate',side_effect=fake),patch('qagent.memory.generate',new=Intervention('restart')),patch('qagent.memory.evaluate',side_effect=evaluate):
            for tid in sorted({r['task_id'] for r in rows}):
                family=[taskmap[f+'_'+tid] for f in ('qiskit','cirq','pennylane')]
                result=memory.solve_family(family,root/'runs/replay','initial',6,'private')
                for r in result:
                    assert r['passed']==bykey[r['key']]['passed']
                    for actual,expected in zip(r['records'][1:],bykey[r['key']]['records'][1:]):
                        assert actual['generation']['intervention']==expected['generation']['intervention']
    assert count==137
    baseline_count=0
    for row in json.loads((ROOT/'results/feedback.json').read_text()):
        history=''; task=taskmap[row['key']]
        for i,r in enumerate(row['records']):
            if i:
                assert hashlib.sha256((task['complete_prompt']+history).encode()).hexdigest()==proof[('feedback',row['key'],i+1)]['public_prompt_sha256'],(row['key'],i+1)
                baseline_count+=1
            if not r['evaluation']['passed']:
                history+='\n\nPrevious assistant code:\n'+r['generation']['code']+'\n\nUser feedback:\n'+feedback(r['evaluation'])
    assert baseline_count==182
    for row in initial:
        assert hashlib.sha256(taskmap[row['key']]['complete_prompt'].encode()).hexdigest()==row['records'][0]['generation']['prompt_sha256']
    print('PASS: all 126 initial, 182 feedback and 137 restart prompt hashes match the privacy-redacted archived inputs.')

if __name__=='__main__':main()
