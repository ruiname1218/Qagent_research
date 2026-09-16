"""Audit all four predeclared peer-code visibility trajectories and compare families."""
import copy
import hashlib
import json
from pathlib import Path
import numpy as np
from .core import ROOT, FRAMEWORKS, dump, tasks
from .report import collect, metrics
from .private_extension_report import expected_base
from .private_extensions import SCHEMA, intervention_input, split_prompt
from .peer_code_ablation import visibility_input, MASK
from .recover_transport_notice import is_transport_notice

def sha(data): return hashlib.sha256(data).hexdigest()

def main():
    registry=json.loads((ROOT/'reports/peer_code_ablation_registry.json').read_text())
    for name,digest in registry['source_sha256'].items():assert sha((ROOT/name).read_bytes())==digest,name
    taskmap={t['framework']+'_'+t['task_id']:t for t in tasks()}; keys=set(taskmap)
    initial=collect(registry['settings']['initial_run']);assert set(initial)==keys and len(keys)==126
    data={arm:collect(run) for arm,run in registry['runs'].items()}
    audits={};actions=[]
    for arm,rows in data.items():
        assert set(rows)==keys,(arm,len(rows))
        visibility=arm.split('_')[0];run=ROOT/'runs'/registry['runs'][arm]
        assert not list(run.glob('family_*_error.json'))
        config=json.loads((run/'config.json').read_text())
        assert config==dict(registry['settings'],visibility=visibility,replicate=int(arm[-1]))
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
                base=visibility_input(source,visibility)
                assert base==(folder/'base_prompt.txt').read_text()
                before=split_prompt(source);after=split_prompt(base)
                assert before[0]==after[0] and before[1]==after[1] and before[3]==after[3]
                assert after[2]==[dict(peer,code=MASK) for peer in before[2]] if visibility=='masked' else before[2]==after[2]
                assert all(not r['diagnosis'] for r in after[3] if r['framework']!=row['framework'])
                prompt,schema,metadata=intervention_input('restart',base,SCHEMA,folder)
                raw=folder/'model';g=json.loads((raw/'generation.json').read_text())
                assert prompt==(raw/'prompt.txt').read_text()
                assert schema==json.loads((raw/'schema.json').read_text())
                assert sha(prompt.encode())==g['prompt_sha256']
                assert g['model']=='gpt-6-astra' and g['effort']=='medium' and not g['tool_events']
                answer=json.loads((raw/'answer.txt').read_text());assert json.loads(g['code'])==answer
                events=[json.loads(l) for l in (raw/'events.jsonl').read_text().splitlines() if l.strip()]
                completed=[e for e in events if e['type']=='turn.completed']
                assert len(completed)==1 and completed[0]['usage']==g['usage']
                other=[e for e in events if e['type']=='item.completed' and e['item']['type'] not in ('agent_message','reasoning')]
                if other:
                    assert all(is_transport_notice(e) for e in other)
                    assert other==g['transport_notices']
                    proof=json.loads((raw/'transport_recovery.json').read_text())
                    assert proof['new_model_calls']==0
                    for name,digest in proof['raw_sha256'].items():assert sha((raw/name).read_bytes())==digest
                    recovered+=1
                expected=dict(g,code=answer['code'],model_calls=1,intervention=metadata,peer_code_visibility=visibility)
                assert expected==record['generation']==json.loads((folder/'generation.json').read_text())
                assert answer==json.loads((folder/'answer.txt').read_text())
                assert record['plan']=={k:v for k,v in answer.items() if k!='code'}
                calls+=1
                actions.append({'arm':arm,'key':key,'attempt':n,'passed':record['evaluation']['passed'],
                    'restart':metadata['restart'],'visible_peer_codes':2 if visibility=='shared' else 0,
                    'accepted_peers':record['accepted_peers']})
        audits[arm]={'completed':126,'new_calls_and_evaluations':calls,'transport_recoveries':recovered,
            'source_and_actual_prompts_reconstructed':True,'only_explicit_peer_code_visibility_changed':True}
    capacity_path=ROOT/'reports/peer_code_capacity_recovery.json'
    capacity=json.loads(capacity_path.read_text()) if capacity_path.exists() else None
    if capacity:
        archived=ROOT/capacity['failed_raw_folder']
        assert not (archived/'answer.txt').exists() and not (archived/'generation.json').exists()
        events=[json.loads(l) for l in (archived/'events.jsonl').read_text().splitlines()]
        assert [e['type'] for e in events]==['thread.started','turn.started','error','turn.failed']
        assert events[-1]['error']['message']=='Selected model is at capacity. Please try a different model.'
        for name,digest in capacity['raw_sha256'].items():assert sha((archived/name).read_bytes())==digest
        retry=ROOT/'runs'/registry['runs'][capacity['arm']]/capacity['case']/f"attempt_{capacity['attempt']}"/'model'
        for name in ['prompt.txt','schema.json']:
            assert (archived/name).read_bytes()==(retry/name).read_bytes()
    vqe_path=ROOT/'reports/peer_code_vqe_check.json'
    vqe=json.loads(vqe_path.read_text())
    assert len(vqe['checks'])==2
    for check in vqe['checks']:
        row=data[check['arm']][check['key']]
        assert row['passed']==check['officially_accepted']
        assert sha(row['records'][-1]['generation']['code'].encode())==check['code_sha256']
    summaries={arm:metrics(rows) for arm,rows in data.items()}
    deltas=np.array([[sum(int(data[f'shared_r{rep}'][f+'_'+tid]['passed'])-int(data[f'masked_r{rep}'][f+'_'+tid]['passed']) for f in FRAMEWORKS)/3 for tid in registry['ids']] for rep in (1,2)])
    avg=deltas.mean(axis=0)
    samples=np.random.default_rng(20260916).choice(avg,(20000,42)).mean(axis=1)*100
    ci=np.quantile(samples,[.025,.975]).tolist()
    repetitions={}
    for rep in (1,2):
        a,b=f'shared_r{rep}',f'masked_r{rep}'
        gains=[k for k in sorted(keys) if data[a][k]['passed'] and not data[b][k]['passed']]
        losses=[k for k in sorted(keys) if data[b][k]['passed'] and not data[a][k]['passed']]
        repetitions[str(rep)]={'shared':summaries[a]['passed'],'masked':summaries[b]['passed'],
            'difference_cases':len(gains)-len(losses),'difference_pp':float(deltas[rep-1].mean()*100),'gains':gains,'losses':losses}
    supported=all(r['difference_cases']>0 for r in repetitions.values()) and ci[0]>0
    primary={'mean_difference_pp':float(avg.mean()*100),'family_bootstrap_95_ci_pp':ci,
        'mean_difference_cases':float(sum(r['difference_cases'] for r in repetitions.values())/2),
        'predeclared_support_criterion_met':supported,'families':42,'repetitions':2}
    outcome={k:{arm:rows[k]['passed'] for arm,rows in data.items()} for k in sorted(keys)}
    semantic_path=ROOT/'reports/peer_code_semantic.json'
    semantic=json.loads(semantic_path.read_text()) if semantic_path.exists() else None
    if semantic:
        assert semantic['completed']==semantic['expected']==8
        for check in semantic['checks']:
            row=data[check['arm']][check['key']]
            assert check['officially_accepted']==row['passed']
            assert check['artifact_probe_sha256']==sha((row['records'][-1]['generation']['code']+'\n'+check['probe']).encode())

    report={'registry':registry,'summaries':summaries,'audits':audits,'repetitions':repetitions,'primary':primary,
        'outcomes':outcome,'actions':actions,'new_model_calls':sum(a['new_calls_and_evaluations'] for a in audits.values()),
        'posthoc_vqe':vqe,'capacity_recovery':capacity,'failed_backend_invocations':1 if capacity else 0,'posthoc_semantic':semantic,'analysis_source_sha256':sha(Path(__file__).read_bytes())}
    dump(ROOT/'reports/peer_code_ablation_results.json',report)
    labels={'shared':'コード共有あり','masked':'コードを伏せる'}
    table='\n'.join(f"| {labels[a.split('_')[0]]}・{a[-1]}回目 | {s['passed']}/126 | {s['model_calls']} | {s['usage']['output_tokens']:,} |" for a,s in summaries.items())
    changes='\n'.join(f"- {rep}回目：共有でのみ合格 {', '.join(r['gains']) or 'なし'}。伏せる条件でのみ合格 {', '.join(r['losses']) or 'なし'}。" for rep,r in repetitions.items())
    conclusion=('事前に定めた条件を満たし、この設定で生成コードを見せることの正の効果を支持する結果だった。' if supported else '事前に定めた支持条件を満たさず、SDK生成コードの共有が性能を上げたという結論は確立できなかった。')
    text=f'''# SDK生成コード共有の切り分け実験

## 結論

{conclusion}
平均差（共有あり−コードを伏せる）は {primary['mean_difference_cases']:+.1f}件/126、{primary['mean_difference_pp']:+.2f}ポイント。
42問題単位bootstrap 95%区間は [{ci[0]:+.2f}, {ci[1]:+.2f}] ポイント。
この区間は2回で捉えられないLLM変動全体や未見問題への一般化を保証しない。

## 全件実測

| 条件 | 合格数 | 初回込みLLM呼び出し | 初回込み出力トークン |
|---|---:|---:|---:|
{table}

各行に共通初回126件を含む。今回新規の生成・公式評価は各{report['new_model_calls']}回。
過去の108/126を主比較に使わず、両条件を2回ずつ新しく生成した。
全4条件×126ケースを完了し、途中結果による条件変更・選択的な繰返しは行っていない。

## 切り分けたもの

土台は台帳の診断共有を外したprivate-note restart構成。他SDKの診断・仮説はどちらも共有しない。
元のポリシー・JSON出力形式・自身の診断・停滞判定・最大5修正・1修正1呼び出し1評価を固定。
コードを伏せる条件では、latest peer evidenceの各code文字列だけを固定マーカーに置換する。
評価結果・合否・エラー・他SDKの問題文・履歴の表示規則は両条件とも同じ。
各条件の生成が変わればその後の観測値も変わるので、実際の評価結果の値まで固定した実験ではない。

これは「評価情報に加えて他SDKの完全な生成コードを明示する」効果の比較であり、
他SDKの情報をすべて除いた独立解法との比較ではない。トークン数も揃えていない。
エラー文に偶発的なコード断片が含まれる可能性は残る。ポリシー文面は両条件で同一のため、
コードを利用する指示も残るが、コード欄には非表示であることを明記した。

## 合否が異なるケース

{changes}

公式採点の合格は仕様・数学的正しさの証明ではない。
得点差を正しい回路生成の改善と言い換えるには、差が出た回路の意味検査が別途必要。

## 容量不足による呼び出し失敗

コード非表示1回目のPennyLane task41・最後の修正で、サービスがcapacityエラーを返した。
コード・回答・使用量・生成完了は一切返らなかった。元ログを変更せず別フォルダへ保存し、
同一のpromptとschema・同一モデルで空の候補枠を再試行したことをhashで照合した。
これは完了した修正生成とは別に数えるバックエンド呼び出し失敗1件であり、
実行前に定めた完了応答のtransport復元規則を超えた運用上の例外として開示する。
候補を見て捨てたり修正上限を増やしたりしていない。[失敗記録と再送の証跡](peer_code_capacity_recovery.json)。

## 対象を絞った事後検査

QPE(task25)とGHZ比較(task26)のQiskit最終回路を、全4系列で計8件検査した。
QPEは全系列で、最初の制御演算の基底が標準Grover反復と全体位相を除いても一致しなかった。
この検査だけで曖昧な問題文の全解釈を否定したとは扱わない。
共有あり2回目で合格したtask26は、GHZ/比較レジスタを途中でresetし、準備し直して
対応する1量子ビットごとの独立した局所SWAP比較を行う回路だった。
全状態の重なりを1回のSWAP testで測る回路とは異なる。これを広い意味での正しい回路生成の
改善と主張するには、要求の解釈を含めた検証が必要である。
共有あり2回目で増えたVQEのCirq/PennyLane(task41)は、Z2をZの二乗と解釈し、
ハミルトニアンを恒等演算子Iにしていた。optimizerを呼ぶ実装ではあるが、目的関数が一定となる。
追加の事後検査では2つのパラメータ点でエネルギーがともに約1、optimizerの反復0回、
初期パラメータからの変化0を確認した。PennyLaneの診断には受理されたCirqの回路構成を
転用した旨が記録されているが、この解釈が意図されたVQEを満たすかは別問題である。
[目的関数・最適化の事後確認](peer_code_vqe_check.json)。
事後検査はモデルへのフィードバックや候補選択に一切使っていない。
[検査内容・観測値](peer_code_semantic.json)。

## 証跡

全修正の元プロンプトを利用可能な履歴から再構成し、コード欄以外の変更がないことを確認した。
停滞時の文脈処理、他SDKの診断非共有、初回の同一性、最大5修正、合格後停止を照合した。
実際の生成完了イベント、モデル・effort、トークン使用量、回答→コード→採点記録を確認した。
通信フォールバックの通知だけで停止した完了応答は、生ログを保持し、再問い合わせせず同じ回答を復元した。
その他の未解決インフラエラーを含めたまま合格数を確定していない。

[実行前登録](peer_code_ablation_registry.json) / [全結果と監査](peer_code_ablation_results.json)
'''
    (ROOT/'reports/PEER_CODE_ABLATION_RESULTS.md').write_text(text)
    print(json.dumps({'primary':primary,'repetitions':repetitions,'summaries':summaries,'audits':audits},indent=2))

if __name__=='__main__':main()
