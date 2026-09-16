"""Archive an empty capacity failure before one identical-input retry; no candidate discarded."""
from pathlib import Path
import hashlib
import json
from .core import ROOT, dump


def archive_capacity(folder):
    folder=Path(folder).resolve()
    assert folder.is_relative_to(ROOT/'runs') and folder.name=='model'
    assert not (folder/'answer.txt').exists() and not (folder/'generation.json').exists()
    events=[json.loads(line) for line in (folder/'events.jsonl').read_text().splitlines() if line.strip()]
    assert [e['type'] for e in events]==['thread.started','turn.started','error','turn.failed']
    assert events[-1]['error']['message']=='Selected model is at capacity. Please try a different model.'
    assert events[-2]['message']==events[-1]['error']['message']
    archive=folder.parent/'failed_model_calls/capacity_1'
    assert not archive.exists(), 'Only one empty capacity retry per candidate slot'
    proof={'reason':events[-1]['error']['message'],'candidate_returned':False,'usage_reported':False,
        'failed_backend_invocations':1,'raw_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()},
        'source_error':json.loads((folder.parent.parent.parent/('family_'+folder.parent.parent.name.rsplit('_',1)[1]+'_error.json')).read_text()),
        'retry_rule':'One identical prompt/model/schema retry after verified empty capacity failure, no discarded candidate.'}
    archive.parent.mkdir(parents=True,exist_ok=True)
    folder.rename(archive)
    dump(archive/'capacity_retry.json',proof)
    return proof
