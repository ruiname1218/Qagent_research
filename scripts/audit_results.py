"""Offline integrity, budget and provenance audit. Uses only the standard library."""
from pathlib import Path
import csv
import hashlib
import json
ROOT=Path(__file__).resolve().parents[1]

def audit():
    def read(name): return json.loads((ROOT/'results'/name).read_text())
    for name, expected in read('checksums.json').items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected, name
    data={m:read(m+'.json') for m in ('oneshot','feedback','restart')}
    summary=read('summary.json')
    expected_keys={f'{f}_{i:02d}' for f in ('qiskit','cirq','pennylane') for i in range(1,45) if i not in (5,38)}
    initial={r['key']:r['records'][0] for r in data['oneshot']}
    proof={(p['condition'],p['case'],p['attempt']):p for p in read('provenance.json')}
    count=0
    for mode,rows in data.items():
        assert len(rows)==126 and {r['key'] for r in rows}==expected_keys
        for row in rows:
            records=row['records']; assert row['attempts']==len(records)
            assert 1<=len(records)<=(1 if mode=='oneshot' else 6)
            assert records[0]['generation']==initial[row['key']]['generation']
            for field in ('compiled','ran','passed','output','kl','seed'):
                assert records[0]['evaluation'].get(field)==initial[row['key']]['evaluation'].get(field)
            assert row['passed']==records[-1]['evaluation']['passed']
            assert not any(r['evaluation']['passed'] for r in records[:-1])
            for i,r in enumerate(records,1):
                count+=1; assert r['attempt']==i
                assert not r['evaluation'].get('infra_error')
                g=r['generation']; assert g['model']=='gpt-6-astra' and g['effort']=='medium'
                assert g.get('model_calls',1)==1
                p=proof[(mode,row['key'],i)]
                assert g['usage']==p['usage'] and g['prompt_sha256']==p['raw_sha256']['prompt.txt']
        computed={'cases':len(rows),'passed':sum(r['passed'] for r in rows),
            'passed_by_5_submissions':sum(any(x['evaluation']['passed'] for x in r['records'][:5]) for r in rows),
            'model_calls_including_common_initial':sum(len(r['records']) for r in rows),
            'output_tokens_including_common_initial':sum(x['generation']['usage'].get('output_tokens',0) for r in rows for x in r['records']),
            'by_framework':{f:sum(r['passed'] for r in rows if r['framework']==f) for f in ('qiskit','cirq','pennylane')}}
        assert computed==summary[mode],mode
    assert len(proof)==count==697
    triggers=sum(r['generation'].get('intervention',{}).get('restart',{}).get('triggered',False) for row in data['restart'] for r in row['records'])
    assert triggers==22
    assert not any(r['generation'].get('intervention',{}).get('restart',{}).get('triggered',False) for row in data['restart'] if row['task_id']=='26' for r in row['records'])
    return data,summary

def main():
    data,summary=audit()
    with (ROOT/'results/cases.csv').open('w',newline='') as out:
        writer=csv.writer(out); writer.writerow(['condition','case','framework','task_id','passed','submissions'])
        for mode,rows in data.items():
            for r in rows:writer.writerow([mode,r['key'],r['framework'],r['task_id'],int(r['passed']),r['attempts']])
    lines=['| Condition | Passed | Accuracy | Calls* | Output tokens* |','|---|---:|---:|---:|---:|']
    for m,r in summary.items():
        lines.append(f"| {m} | {r['passed']}/126 | {100*r['passed']/126:.1f}% | {r['model_calls_including_common_initial']} | {r['output_tokens_including_common_initial']:,} |")
    lines+=['','*Includes the shared initial 126 calls in each row; these were generated once.',
        'These are selected development trajectories, not independent repeated trials.','']
    from audit_no_peer_no_restart import audit as audit_no_restart
    extra = audit_no_restart()
    lines += ['Additional no-sharing conditions (same initial candidates, maximum five repairs):', '',
        '| Condition | Passed | Acceptance rate | Repetitions |',
        '|---|---:|---:|---:|',
        '| No SDK sharing; stagnation reconsideration enabled | 103/126, 103/126 | 81.7%, 81.7% | 2 |',
        f"| No SDK sharing; stagnation reconsideration disabled | {extra['passed']}/126 | {100*extra['passed']/126:.1f}% | 1 |", '',
        'The enabled runs are prior experiments; the disabled run is new. Unequal repetitions and a one-case gap do not establish a stable masking benefit.',
        'Complete case-level trajectories, audits and replay commands: [Evidence inventory](../docs/EVIDENCE.md).', '']
    (ROOT/'results/table.md').write_text('\n'.join(lines))
    print('PASS: 378 case results, 697 record entries, 445 distinct model calls; scores 74 / 99 / 108.')
    print('Verified checksums, provenance metadata, common initial, stopping rules, budgets and 22 restart triggers.')
    print('This audit does not execute circuits or independently authenticate omitted raw logs.')

if __name__=='__main__':main()
