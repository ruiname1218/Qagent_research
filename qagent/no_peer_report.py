"""Verify the actual model inputs contain no peer data in the none condition."""
import hashlib
import json
from pathlib import Path
import numpy as np
from .core import ROOT, FRAMEWORKS, dump, tasks
from .report import collect, metrics
from .private_extension_report import expected_base
from .private_extensions import SCHEMA, intervention_input, split_prompt, PEERS, LEDGER
from .no_peer_ablation import peer_information_input
from .recover_transport_notice import is_transport_notice


def sha(data):return hashlib.sha256(data).hexdigest()


def main():
    registry=json.loads((ROOT/'reports/no_peer_registry.json').read_text())
    for name,digest in registry['source_sha256'].items():assert sha((ROOT/name).read_bytes())==digest,name
    taskmap={t['framework']+'_'+t['task_id']:t for t in tasks()};keys=set(taskmap)
    initial=collect(registry['settings']['initial_run']);assert set(initial)==keys and len(keys)==126
    data={arm:collect(run) for arm,run in registry['runs'].items()}
    audits={};actions=[];failures=[]
    for arm,rows in data.items():
        assert set(rows)==keys,(arm,len(rows))
        level=arm.rsplit('_',1)[0];run=ROOT/'runs'/registry['runs'][arm]
        assert not list(run.glob('family_*_error.json'))
        config=json.loads((run/'config.json').read_text())
        assert config==dict(registry['settings'],level=level,replicate=int(arm[-1]))
        calls=recovered=0
        for key,row in rows.items():
            history=row['records'];assert 1<=row['attempts']==len(history)<=6
            assert history[0]==initial[key]['records'][0]
            assert row['passed']==history[-1]['evaluation']['passed']
            for n,record in enumerate(history,1):
                assert n==record['attempt'] and not record['evaluation'].get('infra_error')
                if n<len(history):assert not record['evaluation']['passed']
                folder=run/key/f'attempt_{n}'
                assert record==json.loads((folder/'record.json').read_text())
                if n==1:continue
                source=expected_base(taskmap[key],rows,n)
                assert source==(folder/'source_prompt.txt').read_text(),(arm,key,n,'source')
                base=peer_information_input(source,row['framework'],level)
                assert base==(folder/'base_prompt.txt').read_text()
                before=split_prompt(source);after=split_prompt(base)
                assert before[0]==after[0] and before[1]==after[1]
                if level=='none':
                    assert after[2]==[]
                    assert after[3]==[r for r in before[3] if r['framework']==row['framework']]
                assert all(not r['diagnosis'] for r in after[3] if r['framework']!=row['framework'])
                prompt,schema,metadata=intervention_input('restart',base,SCHEMA,folder)
                raw=folder/'model';g=json.loads((raw/'generation.json').read_text())
                assert prompt==(raw/'prompt.txt').read_text()
                if level=='none':
                    # Inspect the final sent prompt even when restart appends its policy.
                    peers,tail=prompt.split(PEERS,1)[1].split(LEDGER,1)
                    ledger,_=json.JSONDecoder().raw_decode(tail)
                    assert json.loads(peers)==[]
                    assert all(r['framework']==row['framework'] for r in ledger)
                assert schema==json.loads((raw/'schema.json').read_text())
                assert sha(prompt.encode())==g['prompt_sha256']
                assert g['model']=='gpt-6-astra' and g['effort']=='medium' and not g['tool_events']
                answer=json.loads((raw/'answer.txt').read_text());assert json.loads(g['code'])==answer
                events=[json.loads(l) for l in (raw/'events.jsonl').read_text().splitlines() if l.strip()]
                completed=[e for e in events if e['type']=='turn.completed']
                assert len(completed)==1 and completed[0]['usage']==g['usage']
                other=[e for e in events if e['type']=='item.completed' and e['item']['type'] not in ('agent_message','reasoning')]
                if other:
                    assert all(is_transport_notice(e) for e in other) and other==g['transport_notices']
                    proof=json.loads((raw/'transport_recovery.json').read_text());assert proof['new_model_calls']==0
                    for name,digest in proof['raw_sha256'].items():assert sha((raw/name).read_bytes())==digest
                    recovered+=1
                for archived in folder.glob('failed_model_calls/*'):
                    proof=json.loads((archived/'capacity_retry.json').read_text())
                    assert not (archived/'answer.txt').exists() and not (archived/'generation.json').exists()
                    ev=[json.loads(l) for l in (archived/'events.jsonl').read_text().splitlines()]
                    assert [e['type'] for e in ev]==['thread.started','turn.started','error','turn.failed']
                    assert ev[-1]['error']['message']=='Selected model is at capacity. Please try a different model.'
                    for name,digest in proof['raw_sha256'].items():assert sha((archived/name).read_bytes())==digest
                    for name in ['prompt.txt','schema.json']:assert (archived/name).read_bytes()==(raw/name).read_bytes()
                    failures.append({'arm':arm,'case':key,'attempt':n,'proof':proof})
                expected=dict(g,code=answer['code'],model_calls=1,intervention=metadata,peer_information=level)
                assert expected==record['generation']==json.loads((folder/'generation.json').read_text())
                assert answer==json.loads((folder/'answer.txt').read_text())
                assert record['plan']=={k:v for k,v in answer.items() if k!='code'}
                calls+=1
                actions.append({'arm':arm,'key':key,'attempt':n,'passed':record['evaluation']['passed'],
                    'restart':metadata['restart'],'sent_peer_evidence_rows':len(after[2]),
                    'sent_peer_history_rows':sum(r['framework']!=row['framework'] for r in after[3])})
        audits[arm]={'completed':126,'new_calls_and_evaluations':calls,'transport_recoveries':recovered,
            'source_and_actual_prompts_reconstructed':True,'none_condition_has_zero_peer_evidence_and_history_rows':level=='none'}
    examples=json.loads((ROOT/'reports/no_peer_case_analysis.json').read_text())
    hhl=json.loads((ROOT/'reports/no_peer_hhl_check.json').read_text())
    for check in hhl['checks']:
        row=data[check['arm']][check['key']]
        assert row['passed']==check['officially_accepted']
        assert row['records'][-1]['evaluation'].get('output')==check['output']
    for example in examples['examples']:
        for level,detail in example['conditions'].items():
            row=data[f"{level}_r{example['replicate']}"][example['key']]
            assert row['passed']==detail['passed'] and row['attempts']==detail['attempts']
            assert row['records'][-1]['plan']==detail['final_plan']
    summaries={arm:metrics(rows) for arm,rows in data.items()}
    deltas=np.array([[sum(int(data[f'outcomes_r{rep}'][f+'_'+tid]['passed'])-int(data[f'none_r{rep}'][f+'_'+tid]['passed']) for f in FRAMEWORKS)/3 for tid in registry['ids']] for rep in (1,2)])
    avg=deltas.mean(axis=0)
    ci=np.quantile(np.random.default_rng(2026091602).choice(avg,(20000,42)).mean(axis=1)*100,[.025,.975]).tolist()
    repetitions={}
    for rep in (1,2):
        a,b=f'outcomes_r{rep}',f'none_r{rep}'
        gains=[k for k in sorted(keys) if data[a][k]['passed'] and not data[b][k]['passed']]
        losses=[k for k in sorted(keys) if data[b][k]['passed'] and not data[a][k]['passed']]
        repetitions[str(rep)]={'outcomes':summaries[a]['passed'],'none':summaries[b]['passed'],
            'difference_cases':len(gains)-len(losses),'difference_pp':float(deltas[rep-1].mean()*100),'gains':gains,'losses':losses}
    supported=all(r['difference_cases']>0 for r in repetitions.values()) and ci[0]>0
    primary={'mean_difference_pp':float(avg.mean()*100),'family_bootstrap_95_ci_pp':ci,
        'mean_difference_cases':float(sum(r['difference_cases'] for r in repetitions.values())/2),
        'predeclared_support_criterion_met':supported,'direction':'outcomes minus none','families':42,'repetitions':2}
    report={'registry':registry,'summaries':summaries,'audits':audits,'repetitions':repetitions,'primary':primary,
        'outcomes':{k:{arm:rows[k]['passed'] for arm,rows in data.items()} for k in sorted(keys)},'actions':actions,
        'new_model_calls':sum(a['new_calls_and_evaluations'] for a in audits.values()),'failed_backend_invocations':len(failures),
        'trace_examples':examples,'hhl_math_check':hhl,'capacity_recoveries':failures,'analysis_source_sha256':sha(Path(__file__).read_bytes())}
    dump(ROOT/'reports/no_peer_results.json',report)
    labels={'outcomes':'コード非表示・それ以外の他SDK情報あり','none':'他SDKの情報すべて非表示'}
    table='\n'.join(f"| {labels[a.rsplit('_',1)[0]]}・{a[-1]}回目 | {s['passed']}/126 | {s['model_calls']} | {s['usage']['output_tokens']:,} |" for a,s in summaries.items())
    changes='\n'.join(f"- {rep}回目：他SDK情報ありでのみ合格 {', '.join(r['gains']) or 'なし'}。すべて非表示でのみ合格 {', '.join(r['losses']) or 'なし'}。" for rep,r in repetitions.items())
    conclusion=('この設定でコード以外の他SDK情報を見せることの一貫した正の効果を支持する結果だった。' if supported else 'コード以外の他SDK情報を見せることによる、一貫した精度向上の基準は満たさなかった。')
    text=f'''# 他SDK情報をすべて外した実験

## 結論

{conclusion}
平均差（コード以外の他SDK情報あり−すべて非表示）は {primary['mean_difference_cases']:+.1f}件/126、{primary['mean_difference_pp']:+.2f}ポイント。
42問題単位bootstrap95%区間は [{ci[0]:+.2f}, {ci[1]:+.2f}] ポイント。
区間が[0,0]でも一般的な無効性や同等性の証明ではなく、2回で生成変動全体を測ったわけではない。

## 全件実測

| 条件 | 合格数 | 初回込みLLM呼び出し | 初回込み出力トークン |
|---|---:|---:|---:|
{table}

全4系列×126ケースを完了。各行に共通初回126件を含む。
今回の新規の完了した修正生成・公式評価は各{report['new_model_calls']}回。
回答が返らなかった容量不足によるバックエンド呼び出し失敗は{len(failures)}回で、完了した生成とは別に数える。
その場合は候補を捨てず、失敗ログ保存後に同一prompt/schemaで空の候補枠を1回再送する実行前規則を適用した。

## 何を外したか

| 他SDKの情報 | 比較用：コード非表示 | 今回：すべて非表示 |
|---|---|---|
| 問題文 | 表示 | 非表示 |
| 完全な生成コード | 非表示 | 非表示 |
| 合否・観測出力・エラー | 表示 | 非表示 |
| 過去の合否・フィードバック | 表示 | 非表示 |
| 診断・仮説 | 非表示 | 非表示 |

最新peer evidenceを空配列にし、履歴から自分以外のSDKの行を削除した。
自分の問題文・生成コード・評価・診断は保持し、元と同じ停滞条件で自分のコード・診断を一時的に伏せる。
モデルはGPT-6 Astra/medium、同じ初回126件、最大5修正、各修正1候補・1公式評価。
固定ポリシーにSDK名・一般的なpeer利用の説明は残るが、他SDKでの当該問題の試行情報は一切渡さない。
入力長・トークン数を揃えた実験ではない。共有用に書かれた元ポリシーは変更していない。

host側の監査用source_promptと内部メタデータには他SDK情報を保存するが、
実際に送ったmodel/prompt.txtでは削除済み。モデルはツール無効の空の作業ディレクトリで動作し、
監査ファイルを参照する経路を設けていない。公式採点の参照解答・分布も渡していない。

## ケース別の差

{changes}

公式採点の合格を数学的・仕様上の正しさと同一視しない。
過去のコード共有あり107/110、コードだけ非表示107/107は別の実験として扱い、
今回の主比較には両条件とも新しく生成した2回を使用した。

## 具体的に使われた情報と採点上の限界

完了済みの修正履歴を事後に調べたところ、PennyLane HHLでは他SDKの合格出力が4要素であることを根拠に、
64要素の全レジスタ測定から2量子ビットの解レジスタだけを測定する修正を選んでいた。
Hadamard testでも、他SDKの合格出力が2要素であることからancillaだけの測定を選んだ。
Cirq QAOAでは出力分布と他SDKの合否を使い、測定ビット順やZZ回転規約を再検討した。
モデルの診断文は推論過程の証明ではないが、実際に見せた情報と生成変更に対応する具体例である。
どのフィールド単独の効果かは、この実験では切り分けていない。
[6ケース対の診断・可視情報・出力サイズ](no_peer_case_analysis.json)。

HHLの受理された出力は、成功ancillaへの条件付けを省いた測定であり、
問題文のAx=bを解いて正規化した状態の確率分布とは異なる。
全情報非表示2回目の不合格出力の方が、その数学的解に近かった。
したがって本結果は採点上の出力仕様への適合を含み、数学的に正しい回路生成の改善とは同一視しない。
[保存出力と線形代数による確認](no_peer_hhl_check.json)。
追加の確認結果を進行中のモデルへ渡したり、修正・候補選択に使ったりしていない。

## 監査

各修正の元入力を利用可能だった履歴から再構成し、フィルタ後と実際の送信入力を照合した。
すべて非表示の全モデル入力でpeer evidenceが空、履歴が自SDKの行だけであることを確認した。
共通初回、最大5修正、合格後停止、停滞処理、回答→生成コード→採点記録、生の生成完了と使用量を検証した。

[実行前登録](no_peer_registry.json) / [全結果と監査](no_peer_results.json)
'''
    (ROOT/'reports/NO_PEER_RESULTS.md').write_text(text)
    print(json.dumps({'primary':primary,'repetitions':repetitions,'summaries':summaries,'audits':audits},indent=2))

if __name__=='__main__':main()
