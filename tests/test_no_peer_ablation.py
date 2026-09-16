import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from qagent.core import dump
from qagent.memory_ablation import solve_family
from qagent.private_extensions import OWN, PEERS, LEDGER, split_prompt
from qagent.peer_code_ablation import visibility_input
from qagent.no_peer_ablation import PeerInformation, peer_information_input

class NoPeerTests(unittest.TestCase):
    def test_all_peer_fields_and_historical_rows_removed(self):
        own=[{'code':'OWN_CODE','feedback':'OWN_FEEDBACK'}]
        peers=[{'framework':'cirq','prompt':'PEER_TASK','code':'PEER_CODE','accepted':True,'observed_output':['PEER_OUTPUT'],'error':'PEER_ERROR'}]
        ledger=[{'framework':'qiskit','diagnosis':{'hypothesis':'OWN_NOTE'},'feedback':'OWN_HISTORY'}, {'framework':'cirq','diagnosis':{},'feedback':'PEER_HISTORY','accepted':True}]
        prompt='POLICY'+OWN+json.dumps(own)+PEERS+json.dumps(peers)+LEDGER+json.dumps(ledger)
        prefix,o,p,l=split_prompt(peer_information_input(prompt,'qiskit','none'))
        self.assertEqual(prefix,'POLICY');self.assertEqual(o,own);self.assertEqual(p,[]);self.assertEqual(l,[ledger[0]])
        self.assertNotIn('PEER_',peer_information_input(prompt,'qiskit','none'))
        self.assertEqual(peer_information_input(prompt,'qiskit','outcomes'),visibility_input(prompt,'masked'))

    def test_real_loop_never_sends_peer_information_and_resumes_without_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);family=[]
            for f in ('qiskit','cirq','pennylane'):
                family.append({'framework':f,'task_id':'01','category':'test','complete_prompt':'TASK_SENTINEL_'+f,'canonical_solution':'GOLD_SECRET'})
                failure={'compiled':True,'ran':False,'passed':False,'output':None,'error':'ERROR_SENTINEL_'+f}
                dump(root/'runs/initial'/f'{f}_01/attempt_1/record.json',{'attempt':1,'generation':{'code':'CODE_SENTINEL_'+f},'evaluation':failure})
            def fake(prompt,folder,schema):
                f=folder.parent.parent.name.rsplit('_',1)[0]
                for other in ('qiskit','cirq','pennylane'):
                    if other!=f:
                        for kind in ('TASK','CODE','ERROR','NOTE'):
                            self.assertNotIn(kind+'_SENTINEL_'+other,prompt)
                self.assertNotIn('GOLD_SECRET',prompt)
                answer={'diagnosis':'NOTE_SENTINEL_'+f,'contract':'U','hypothesis':'H','code':'CODE_SENTINEL_'+f}
                folder.mkdir(parents=True,exist_ok=True);(folder/'answer.txt').write_text(json.dumps(answer));dump(folder/'schema.json',schema)
                g={'code':json.dumps(answer),'usage':{},'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()};dump(folder/'generation.json',g);return g
            def evaluation(task,code):
                return {'compiled':True,'ran':True,'passed':False,'output':[1.,0.],'error':None}
            with patch('qagent.memory_ablation.ROOT',root),patch('qagent.private_extensions.generate',side_effect=fake) as gen,patch('qagent.memory_ablation.generate',new=PeerInformation('none')),patch('qagent.memory_ablation.evaluate',side_effect=evaluation) as ev:
                rows=solve_family(family,root/'runs/test','initial',6,'private')
                self.assertEqual(gen.call_count,15);self.assertEqual(ev.call_count,15)
                self.assertEqual(rows,solve_family(family,root/'runs/test','initial',6,'private'))
                self.assertEqual(gen.call_count,15);self.assertEqual(ev.call_count,15)
            for row in rows:
                for r in row['records'][1:]:
                    folder=root/'runs/test'/row['key']/f"attempt_{r['attempt']}"
                    _,own,peers,ledger=split_prompt((folder/'base_prompt.txt').read_text())
                    self.assertEqual(peers,[])
                    self.assertTrue(all(x['framework']==row['framework'] for x in ledger))
                    self.assertEqual(r['generation']['intervention']['restart']['triggered'],r['attempt']>=4)

if __name__=='__main__':unittest.main()
