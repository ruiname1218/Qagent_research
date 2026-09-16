"""Offline audit of the two complete no-peer/restart evidence trajectories."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIGEST = '57e82bef7f337612f3871697f0c4d1dc06525bc834d3904b08c4e59987081d64'


def audit():
    path = ROOT / 'results/ablation/no_peer_restart_full_results.json'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == DIGEST
    report = json.loads(path.read_text())
    initial = {row['key']: row for row in json.loads((ROOT / 'results/oneshot.json').read_text())}
    proofs = {(row['run'], row['key'], row['attempt']): row for row in report['input_proofs']}
    expected = {
        'no_peer_none_r1': {'passed': 103, 'records': 293, 'repairs': 167, 'triggers': 23},
        'no_peer_none_r2': {'passed': 103, 'records': 292, 'repairs': 166, 'triggers': 14},
    }
    counted_proofs = set()
    for run_name, metrics in expected.items():
        run = report['runs'][run_name]
        rows = run['tasks']
        assert len(rows) == run['completed'] == 126
        assert {row['key'] for row in rows} == set(initial)
        assert sum(row['passed'] for row in rows) == run['passed'] == metrics['passed']
        assert sum(len(row['records']) for row in rows) == run['records_including_initial'] == metrics['records']
        repairs = triggers = 0
        for row in rows:
            records = row['records']
            assert 1 <= len(records) == row['attempts'] <= 6
            assert row['passed'] == records[-1]['evaluation']['passed']
            assert not any(record['evaluation']['passed'] for record in records[:-1])
            source = initial[row['key']]['records'][0]
            assert records[0]['generation']['code'] == source['generation']['code']
            assert records[0]['evaluation']['passed'] == source['evaluation']['passed']
            for attempt, record in enumerate(records[1:], 2):
                generation = record['generation']
                assert record['attempt'] == attempt and not record['evaluation'].get('infra_error')
                assert generation['model'] == 'gpt-6-astra' and generation['effort'] == 'medium'
                assert generation['peer_information'] == 'none'
                assert generation['intervention']['mode'] == 'restart'
                key = (run_name, row['key'], attempt)
                proof = proofs[key]
                assert proof['prompt_sha256'] == generation['prompt_sha256'] == proof['raw_sha256']['prompt.txt']
                visibility = proof['visibility']
                assert visibility['sent_peer_evidence_rows'] == 0
                assert visibility['sent_peer_history_rows'] == 0
                triggered = generation['intervention']['restart']['triggered']
                assert visibility['restart_policy_present'] == triggered
                if triggered:
                    assert visibility['withheld_own_code_rows'] == attempt - 1
                    assert visibility['diagnosis_rows_present'] == 0
                    triggers += 1
                else:
                    assert visibility['withheld_own_code_rows'] == 0
                counted_proofs.add(key)
                repairs += 1
        assert repairs == run['new_completed_repair_calls'] == metrics['repairs']
        assert triggers == run['restart_triggers'] == metrics['triggers']
    assert counted_proofs == set(proofs) and len(proofs) == 333
    assert all(report['audit'].values())
    return report


if __name__ == '__main__':
    audit()
    print('PASS: two complete 126-case trajectories; scores 103 / 103, 333 repairs, 37 restart triggers.')
    print('Verified full code/evaluation histories, initial reuse, stopping budgets, input hashes and visibility metadata.')
