"""Offline audit of the saved no-peer/no-restart trajectory; no LLM calls."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def audit():
    path = ROOT / 'results/ablation/no_peer_no_restart_results.json'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == 'f022036846e9dccd36db5927a25dde70c0b25b0f363c6579bbd6e156c067fd18'
    data = json.loads(path.read_text())
    initial = {r['key']: r for r in json.loads((ROOT / 'results/oneshot.json').read_text())}
    rows = data['tasks']
    assert len(rows) == 126 and {r['key'] for r in rows} == set(initial)
    proofs = {(r['key'], r['attempt']): r for r in data['inputs']}
    calls = 0
    for row in rows:
        records = row['records']
        assert 1 <= len(records) == row['attempts'] <= 6
        assert row['passed'] == records[-1]['evaluation']['passed']
        assert not any(r['evaluation']['passed'] for r in records[:-1])
        assert records[0]['generation']['code'] == initial[row['key']]['records'][0]['generation']['code']
        for i, r in enumerate(records[1:], 2):
            g = r['generation']
            assert r['attempt'] == i and not r['evaluation'].get('infra_error')
            assert g['intervention'] == {'mode': 'baseline'} and g['peer_information'] == 'none'
            assert g['stagnation_restart'] is False
            assert g['model'] == 'gpt-6-astra' and g['effort'] == 'medium'
            proof = proofs[(row['key'], i)]
            assert g['prompt_sha256'] == proof['prompt_sha256'] == proof['raw_sha256']['prompt.txt']
            calls += 1
    assert calls == data['new_completed_repair_calls'] == len(proofs) == 167
    assert sum(r['passed'] for r in rows) == data['passed'] == 102
    return data


if __name__ == '__main__':
    audit()
    print('PASS: 126 cases, 102 accepted, 167 repairs; hashes, budgets and saved intervention metadata verified.')
    print('Actual-input privacy was audited at export; sanitized raw traces are in artifacts/raw_traces_sanitized.tar.gz.')
