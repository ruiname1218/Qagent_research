import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from qagent.core import dump
from qagent.memory_ablation import solve_family
from qagent.private_extensions import OWN, PEERS, LEDGER, split_prompt
from qagent.peer_code_ablation import CodeVisibility, visibility_input, MASK

class PeerCodeTests(unittest.TestCase):
    def test_only_peer_code_fields_change(self):
        own=[{'code':'OWN','feedback':'F'}]; peers=[{'code':'PEER','framework':'cirq','prompt':'STUB','accepted':False,'observed_output':[1,0],'error':'TRACE'}]
        ledger=[{'framework':'qiskit','diagnosis':{'hypothesis':'PRIVATE'},'feedback':'F'}]
        text='POLICY'+OWN+json.dumps(own)+PEERS+json.dumps(peers)+LEDGER+json.dumps(ledger)
        self.assertEqual(visibility_input(text,'shared'),text)
        prefix,o,p,l=split_prompt(visibility_input(text,'masked'))
        self.assertEqual(prefix,'POLICY');self.assertEqual(o,own);self.assertEqual(l,ledger)
        self.assertEqual(p,[dict(peers[0],code=MASK)])

    def test_budget_visibility_restart_and_resume(self):
        for visibility in ('shared','masked'):
            with self.subTest(visibility=visibility),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);family=[]
                failure={'compiled':True,'ran':True,'passed':False,'output':[1.,0.],'error':'SECRET_SHAPE','kl':999}
                for f in ('qiskit','cirq','pennylane'):
                    family.append({'framework':f,'task_id':'01','category':'test','complete_prompt':'STUB_'+f,'canonical_solution':'SECRET_GOLD'})
                    dump(root/'runs/initial'/f'{f}_01/attempt_1/record.json',{'attempt':1,'generation':{'code':'CODE_'+f},'evaluation':failure})
                def fake(prompt,folder,schema):
                    f=folder.parent.parent.name.rsplit('_',1)[0];n=int(folder.parent.name.split('_')[-1])
                    self.assertNotIn('SECRET_',prompt)
                    for other in ('qiskit','cirq','pennylane'):
                        if other!=f:
                            self.assertNotIn('PRIVATE_'+other,prompt)
                            if visibility=='masked':self.assertNotIn('CODE_'+other,prompt)
                            else:self.assertIn('CODE_'+other,prompt)
                    if n>=3:
                        self.assertIn('[withheld for this restart]',prompt)
                        self.assertNotIn('PRIVATE_',prompt)
                    answer={'diagnosis':'PRIVATE_'+f,'contract':'U','hypothesis':'H','code':'CODE_'+f}
                    folder.mkdir(parents=True,exist_ok=True);(folder/'answer.txt').write_text(json.dumps(answer));dump(folder/'schema.json',schema)
                    g={'code':json.dumps(answer),'usage':{},'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()};dump(folder/'generation.json',g)
                    return g
                with patch('qagent.memory_ablation.ROOT',root),patch('qagent.private_extensions.generate',side_effect=fake) as gen,patch('qagent.memory_ablation.generate',new=CodeVisibility(visibility)),patch('qagent.memory_ablation.evaluate',return_value=failure) as ev:
                    rows=solve_family(family,root/'runs/test','initial',6,'private')
                    self.assertEqual(gen.call_count,15);self.assertEqual(ev.call_count,15)
                    self.assertTrue(all(r['attempts']==6 for r in rows))
                    self.assertEqual(rows,solve_family(family,root/'runs/test','initial',6,'private'))
                    self.assertEqual(gen.call_count,15);self.assertEqual(ev.call_count,15)

if __name__=='__main__':unittest.main()
