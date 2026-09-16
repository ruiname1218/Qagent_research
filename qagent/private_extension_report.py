"""Reconstruct allowed context, audit raw calls and compare private-memory extensions."""
import copy
import hashlib
import json
import numpy as np
from .core import ROOT, FRAMEWORKS, dump, feedback, tasks
from .report import collect, metrics
from .memory_ablation import BASE_POLICY, LEDGER_POLICY, memory_view
from .private_extensions import (SCHEMA, OWN, PEERS, LEDGER, apply_edits, intervention_input)
from .recover_transport_notice import is_transport_notice

def sha(data):
    return hashlib.sha256(data).hexdigest()

def expected_base(task, rows, attempt):
    framework = task['framework']
    own_history = rows[framework + '_' + task['task_id']]['records'][:attempt - 1]
    own = [{'code': r['generation']['code'], 'feedback': feedback(r['evaluation'])} for r in own_history]
    peers, ledger = [], []
    all_tasks = {t['framework']: t for t in tasks() if t['task_id'] == task['task_id']}
    for f in FRAMEWORKS:
        limit = attempt if FRAMEWORKS.index(f) < FRAMEWORKS.index(framework) else attempt - 1
        prior = rows[f + '_' + task['task_id']]['records'][:limit]
        r = prior[-1]
        if f != framework:
            peers.append({'framework': f, 'prompt': all_tasks[f]['complete_prompt'],
                'accepted': r['evaluation']['passed'], 'code': r['generation']['code'],
                'observed_output': r['evaluation'].get('output'),
                'error': r['evaluation'].get('error') if not r['evaluation']['ran'] else None})
        for previous in prior:
            e = previous['evaluation']
            ledger.append({'framework': f, 'attempt': previous['attempt'], 'accepted': e['passed'],
                           'diagnosis': previous.get('plan', {}),
                           'feedback': None if e['passed'] else feedback(e)})
    return (task['complete_prompt'] + '\n\n' + BASE_POLICY + LEDGER_POLICY +
            OWN + json.dumps(own) + PEERS + json.dumps(peers) +
            LEDGER + memory_view(ledger, framework, 'private'))

def main():
    registry = json.loads((ROOT / 'reports/private_extension_registry.json').read_text())
    for path, value in registry['source_sha256'].items():
        assert sha((ROOT / path).read_bytes()) == value, path
    runs = dict(registry['runs'])
    followup_path = ROOT / 'reports/private_extension_followup_registry.json'
    followup = json.loads(followup_path.read_text()) if followup_path.exists() else None
    if followup:
        runs.update(followup['runs'])
    taskmap = {t['framework'] + '_' + t['task_id']: t for t in tasks()}
    keys = set(taskmap)
    assert len(keys) == 126
    initial = collect(registry['initial_run'])
    assert set(initial) == keys
    data = {arm: collect(name) for arm, name in runs.items()}
    audits, actions, recoveries = {}, [], []
    for arm, rows in data.items():
        assert set(rows) == keys, (arm, len(rows))
        run = ROOT / 'runs' / runs[arm]
        config = json.loads((run / 'config.json').read_text())
        mode = config['mode']
        assert config['attempts'] == 6 and config['initial_run'] == registry['initial_run']
        assert not list(run.glob('family_*_error.json'))
        audited = 0
        for key, row in rows.items():
            history = row['records']
            assert 1 <= row['attempts'] == len(history) <= 6
            assert history[0] == initial[key]['records'][0]
            assert row['passed'] == history[-1]['evaluation']['passed']
            for n, record in enumerate(history, 1):
                assert n == record['attempt']
                assert not record['evaluation'].get('infra_error')
                if n < len(history):
                    assert not record['evaluation']['passed']
                folder = run / key / f'attempt_{n}'
                assert json.loads((folder / 'record.json').read_text()) == record
                if n == 1:
                    continue
                base = (folder / 'base_prompt.txt').read_text()
                assert base == expected_base(taskmap[key], rows, n), (arm, key, n)
                prompt, schema, metadata = intervention_input(mode, base, SCHEMA, folder)
                raw = folder / 'model'
                g = json.loads((raw / 'generation.json').read_text())
                assert prompt == (raw / 'prompt.txt').read_text()
                assert schema == json.loads((raw / 'schema.json').read_text())
                assert sha(prompt.encode()) == g['prompt_sha256']
                assert g['model'] == 'gpt-6-astra' and g['effort'] == 'medium'
                assert not g['tool_events']
                answer = json.loads((raw / 'answer.txt').read_text())
                assert json.loads(g['code']) == answer
                events = [json.loads(l) for l in (raw / 'events.jsonl').read_text().splitlines()]
                completed = [e for e in events if e['type'] == 'turn.completed']
                assert len(completed) == 1 and completed[0]['usage'] == g['usage']
                other = [e for e in events if e['type'] == 'item.completed' and
                         e['item']['type'] not in ('agent_message', 'reasoning')]
                if other:
                    assert all(is_transport_notice(e) for e in other)
                    assert g['transport_notices'] == other
                    proof = json.loads((raw / 'transport_recovery.json').read_text())
                    for filename, digest in proof['raw_sha256'].items():
                        assert sha((raw / filename).read_bytes()) == digest
                    assert proof['new_model_calls'] == 0
                    recoveries.append({'arm': arm, 'key': key, 'attempt': n, 'proof': proof})
                plan = copy.deepcopy(answer)
                if mode == 'patch':
                    code = history[n - 2]['generation']['code']
                    metadata.update(base_code_sha256=sha(code.encode()), edit_mode=answer['edit_mode'])
                    try:
                        plan['code'] = apply_edits(code, answer)
                    except ValueError as exc:
                        message = 'Patch application failed: ' + str(exc)
                        metadata['patch_error'] = message
                        plan['code'] = 'raise ValueError(' + repr(message) + ')\n'
                    plan = {k: plan[k] for k in SCHEMA['required']}
                outer = dict(g, code=plan['code'], model_calls=1, intervention=metadata)
                assert outer == record['generation'] == json.loads((folder / 'generation.json').read_text())
                assert plan == json.loads((folder / 'answer.txt').read_text())
                assert record['plan'] == {k: v for k, v in plan.items() if k != 'code'}
                actions.append({'arm': arm, 'key': key, 'attempt': n, **metadata,
                                'edit_count': len(answer['edits']) if mode == 'patch' else None,
                                'accepted': record['evaluation']['passed']})
                audited += 1
        audits[arm] = {'new_calls_and_evaluations': audited, 'common_initial': 126,
                       'prompt_reconstructed_from_allowed_history': True}
    summaries = {arm: metrics(rows) for arm, rows in data.items()}
    pairs = [(m, 'baseline') for m in ('patch', 'contrast', 'restart')]
    if followup:
        pairs.append((followup['selected'] + '_r2', 'baseline_r2'))
    comparisons = {}
    for a, b in pairs:
        differences = np.array([sum(int(data[a][f + '_' + tid]['passed']) -
            int(data[b][f + '_' + tid]['passed']) for f in FRAMEWORKS) / 3 for tid in registry['ids']])
        ci = np.quantile(np.random.default_rng(20260915).choice(differences, (20000, 42)).mean(axis=1), [.025, .975]) * 100
        changes = [{'key': key, a: data[a][key]['passed'], b: data[b][key]['passed']}
                   for key in sorted(keys) if data[a][key]['passed'] != data[b][key]['passed']]
        comparisons[a + '-' + b] = {'difference_pp': float(differences.mean() * 100),
            'family_bootstrap_95_ci_pp': ci.tolist(), 'gains': sum(c[a] for c in changes),
            'losses': sum(c[b] for c in changes), 'discordant': changes}
    counts = {arm: {'edit': sum(a['arm'] == arm and a.get('edit_mode') == 'edit' for a in actions),
                   'replace': sum(a['arm'] == arm and a.get('edit_mode') == 'replace' for a in actions),
                   'patch_errors': sum(a['arm'] == arm and 'patch_error' in a for a in actions),
                   'zero_edit': sum(a['arm'] == arm and a.get('edit_mode') == 'edit' and a.get('edit_count') == 0 for a in actions),
                   'restarts': sum(a['arm'] == arm and a.get('restart', {}).get('triggered', False) for a in actions)}
              for arm in runs}
    semantic_path = ROOT / 'reports/private_extension_semantic.json'
    semantic = json.loads(semantic_path.read_text()) if semantic_path.exists() else None
    if semantic:
        for check in semantic['checks']:
            saved = data[check['arm']][check['key']]
            code = saved['records'][-1]['generation']['code']
            assert check['artifact_probe_sha256'] == sha((code + '\n' + check['probe']).encode())
            assert check['officially_accepted'] == saved['passed']
    semantic_table = ''
    if semantic:
        lines = []
        for check in semantic['checks']:
            obs = check['observations']
            if not check['ran']:
                detail = '検査を実行できず（JSON参照）'
            elif check['key'] == 'qiskit_25':
                detail = f"標準Grover反復と全体位相を除いて一致: {obs['same_Grover_up_to_global_phase']}"
            elif check['key'] == 'qiskit_43':
                detail = f"Toffoliと全体位相を除いて一致: {obs['matches_toffoli_up_to_global_phase']}、指定ゲートのみ: {obs['only_requested_gates']}"
            else:
                detail = f"5入力すべて理論値との差0.06以内: {all(o['within_0_06'] for o in obs)}"
            lines.append(f"| {check['arm']} | {check['key']} | {check['officially_accepted']} | {detail} |")
        semantic_table = f'''## 保存コードの事後検査

予定{semantic['expected']}件中{semantic['completed']}件を確認した。修正・候補選択には使っていない。

| 条件 | ケース | 公式合格 | 事後検査 |
|---|---|---|---|
''' + '\n'.join(lines) + '''

QPEは最初の制御2量子ビット演算の基底だけを調べ、全回路を検証したわけではない。
SWAPは5入力での標本検査、Toffoliは返された演算子とゲート名の確認。
標準Grover反復と異なることだけで、曖昧な問題文の全解釈を否定したとは扱わない。

'''
    report = {'registry': registry, 'followup_registry': followup, 'summaries': summaries,
        'audits': audits, 'comparisons': comparisons, 'action_counts': counts, 'actions': actions,
        'new_model_calls': sum(a['new_calls_and_evaluations'] for a in audits.values()),
        'outcomes': {k: {m: rows[k]['passed'] for m, rows in data.items()} for k in sorted(keys)},
        'posthoc_semantic': semantic, 'transport_recoveries': recoveries,
        'case26_audit': json.loads((ROOT / 'reports/private_extension_case26.json').read_text()),
        'analysis_source_sha256': sha((ROOT / 'qagent/private_extension_report.py').read_bytes())}
    dump(ROOT / 'reports/private_extension_results.json', report)
    labels = {'baseline': '共有台帳なし・基準', 'patch': '差分修正', 'contrast': '原因仮説の比較', 'restart': '停滞時の再構築'}
    for arm in runs:
        if arm.endswith('_r2'):
            labels[arm] = labels[arm[:-3]] + '・再実験'
    table = '\n'.join(f"| {labels[a]} | {s['passed']}/126 | {s['passed_by_5_generations']} | {s['model_calls']} | {s['usage']['input_tokens']:,} | {s['usage']['output_tokens']:,} |" for a, s in summaries.items())
    pair_table = '\n'.join(f"| {a} | {c['gains']} | {c['losses']} | {c['difference_pp']:+.2f} | [{c['family_bootstrap_95_ci_pp'][0]:+.2f}, {c['family_bootstrap_95_ci_pp'][1]:+.2f}] |" for a, c in comparisons.items())
    action_table = '\n'.join(f"| {a} | {c['edit']} | {c['replace']} | {c['patch_errors']} | {c['restarts']} |" for a, c in counts.items())
    text = f'''# 過去最高方式から台帳共有を外した拡張実験

## 比較した土台

過去に109/126を記録したdeliberative方式の生成ポリシーを使用した。
他SDKの診断・contract・仮説を渡さず、自分の診断履歴は保持するprivate条件を基準にした。
コード・最新の評価結果・合否とフィードバックの履歴は共有する。完全なSDK独立条件ではない。
過去のprivate条件は107/126だったが、今回の基準も修正を新しく生成した。
要求固定方式へ置き換えていない。過去109の成功コードを新しい修正へ流用していない。

## 実測結果

全条件126ケースを完了。各行は共通初回126件を含み、表の合計は新規呼び出し総数ではない。

| 条件 | 合格数 | 初回込み5提出時点 | LLM呼び出し | 入力トークン | 出力トークン |
|---|---:|---:|---:|---:|---:|
{table}

今回の新規LLM呼び出しと公式評価は各{report['new_model_calls']}回。
GPT-6 Astra / medium、共通初回、初回＋最大5修正、各修正1呼び出し・1候補・1公式評価。
合格時に停止。shots1000、seed1234。追加の推論時回路検証・検索・MADは使わない。
実トークン数と生成プログラム内部の計算量は同一ではない。入力はキャッシュ済みの分も含む。

## 拡張

- 差分修正：直前の自分のコードに最大12個の一意な文字列置換を適用する。
  大きな再構築はモデルが明示的に完全置換を選べる。パッチ不成立は実行エラーとして1評価を消費し、無料の再試行をしない。
- 原因仮説の比較：2つの原因について根拠・反証・変更・予測を出し、1つを選んで1候補に実装する。
  この追加の診断も自分だけが参照でき、他SDKへ共有しない。
- 停滞時の再構築：直近2回が実行成功・採点不合格で、出力のL1距離が0.02以下なら、
  その修正だけ自分の過去コードと診断を隠して再生成する。フィードバック・最新の他SDKコードは維持。
  発火しないときは基準と同じプロンプト・スキーマ。出力の近さは演算子同値の証明ではない。

| 条件 | 差分選択 | 全置換選択 | パッチ不成立 | 再構築発火 |
|---|---:|---:|---:|---:|
{action_table}

## ケースを対応させた比較

| 比較 | 拡張のみ合格 | 基準のみ合格 | 差（pp） | 42問題単位bootstrap 95%区間（pp） |
|---|---:|---:|---:|---:|
{pair_table}

3SDKが情報を共有するので42論理問題単位で20,000回再標本化、seed20260915。
区間は新しいLLM生成の変動を含まず、全ケース同点で[0,0]でも統計的同等性の証明ではない。
最初は各条件1系列。拡張が新しい基準を上回った場合だけ最高方式と基準を再実験する手順を実行前に固定した。
同点時の選択順は差分修正、原因仮説比較、再構築。選択後の比較は探索的であり、全方式の平均性能の推定ではない。

## 初回の再構築条件で増えたGHZ比較（task26）

初回の再構築条件ではQiskitのtask26が合格したが、この論理問題では3SDKとも
再構築条件が一度も発火していなかった。Qiskitの最初の修正は基準とプロンプト・スキーマも同一。
この増加を再構築機能の効果には帰属させない。
採用された回路は21量子ビットを使い、各ancillaで新しいGHZ3と|+++>を準備して
対応する1量子ビットだけを比較する。状態共有を変えており、全状態の重なりの検証とは異なる。
[発火履歴・同一入力・コード](private_extension_case26.json)。

{semantic_table}## 監査と限界

全ケースの共通初回・最大5修正・合格後停止・最終コードと公式評価を確認した。
各修正のプロンプトを、その時点で利用可能だった自分の履歴と他SDKコード・評価から完全に再構成した。
他SDKの診断を除外したこと、基準プロンプトの同一性、再構築条件、パッチ適用結果を照合した。
生ログの生成完了イベント、使用量、モデル設定、ツール無効、固定ソースhashも確認した。
モデルに参照解答・参照確率・採点コードを渡していない。

通信方式のフォールバック通知をツール実行と誤認して止まった応答は{len(recoveries)}件。
終了コード0・生成完了・ツール呼び出しなしを生ログで確認し、同じ回答を復元して再開した。
生の回答・イベントは変更せずhashを保存し、再問い合わせも行っていない。
その応答だけ生成時間をファイル時刻から推定した。通知と復元根拠はJSONに記録した。
初回の基準と再構築の停止した各1問題は、他の問題の実行中に別プロセスで再開した。
主バッチは各6並列だが、この復旧中は各条件で最大7問題が並行する可能性がある。
問題内のSDK順序・入力・呼び出し上限は維持した。経過時間を厳密な速度比較には使わない。

開発に使ったベンチマークであり、未見評価ではない。公式合格は数学的な正しさの証明ではない。
過去の109にも仕様適合性の懸念があるため、得点の増減と正しい回路生成の改善を区別する。
事後の意味検査は修正・選択へ返さない。[事後検査](private_extension_semantic.json)。

[実行前設定](private_extension_registry.json) / [全結果・使用量・監査](private_extension_results.json)
'''
    (ROOT / 'reports/PRIVATE_EXTENSION_RESULTS.md').write_text(text)
    print(json.dumps({'summaries': summaries, 'comparisons': comparisons, 'actions': counts}, indent=2))

if __name__ == '__main__':
    main()
