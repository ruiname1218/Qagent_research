import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from qagent.core import dump
from qagent.memory import solve_family
from qagent.restart import Intervention, split_prompt

class RestartTests(unittest.TestCase):
    def test_private_context_budget_masking_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            failure={'compiled':True,'ran':True,'passed':False,'output':[1.,0.],'error':'SECRET_ERROR','kl':999}
            family=[]
            for f in ('qiskit','cirq','pennylane'):
                family.append({'framework':f,'task_id':'01','category':'test','complete_prompt':'Implement f','canonical_solution':'SECRET_REFERENCE'})
                dump(root/'runs/initial'/f'{f}_01/attempt_1/record.json',{'attempt':1,'generation':{'code':'def f(): return 0'},'evaluation':failure})
            def fake(prompt,folder,schema):
                f=folder.parent.parent.name.rsplit('_',1)[0]
                self.assertNotIn('SECRET_',prompt)
                for other in ('qiskit','cirq','pennylane'):
                    if other!=f:self.assertNotIn('PRIVATE_'+other,prompt)
                answer={'diagnosis':'PRIVATE_'+f,'contract':'Preserve U','hypothesis':'Try mapping','code':'def f(): return 1'}
                g={'code':json.dumps(answer),'usage':{},'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()}
                folder.mkdir(parents=True,exist_ok=True);(folder/'answer.txt').write_text(json.dumps(answer));dump(folder/'schema.json',schema);dump(folder/'generation.json',g)
                # At attempt 3 onward the two rejected outputs are identical.
                if int(folder.parent.name.split('_')[-1])>=3:
                    self.assertIn('[withheld for this restart]',prompt); self.assertNotIn('PRIVATE_',prompt)
                return g
            with patch('qagent.memory.ROOT',root),patch('qagent.restart.generate',side_effect=fake) as gen,patch('qagent.memory.generate',new=Intervention('restart')),patch('qagent.memory.evaluate',return_value=failure) as ev:
                rows=solve_family(family,root/'runs/experiment','initial',6,'private')
                self.assertEqual(gen.call_count,15);self.assertEqual(ev.call_count,15)
                self.assertEqual(rows,solve_family(family,root/'runs/experiment','initial',6,'private'))
                self.assertEqual(gen.call_count,15);self.assertEqual(ev.call_count,15)
            self.assertTrue(all(r['attempts']==6 for r in rows))

    def test_acceptance_stops_only_that_sdk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); family=[]
            for f in ('qiskit','cirq','pennylane'):
                family.append({'framework':f,'task_id':'01','category':'test','complete_prompt':'Implement f'})
                dump(root/'runs/initial'/f'{f}_01/attempt_1/record.json',{'attempt':1,'generation':{'code':'pass'},'evaluation':{'compiled':True,'ran':True,'passed':True,'output':[1.]}})
            with patch('qagent.memory.ROOT',root),patch('qagent.memory.generate') as gen,patch('qagent.memory.evaluate') as ev:
                rows=solve_family(family,root/'runs/experiment','initial',6,'private')
                gen.assert_not_called();ev.assert_not_called()
                self.assertTrue(all(r['attempts']==1 for r in rows))

if __name__=='__main__':unittest.main()
