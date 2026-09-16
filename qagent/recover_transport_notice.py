"""Recover a completed, tool-free response rejected solely for a transport notice.

Never requests another model response or edits raw logs. Only explicit failed
family folders with exit=0 are eligible. All notices and estimated timing persist.
"""
import argparse
import hashlib
import json
from pathlib import Path
from .core import ROOT, dump, extract_code

def is_transport_notice(event):
    return (event.get('type') == 'item.completed' and event.get('item', {}).get('type') == 'error'
            and event['item'].get('message', '').startswith('Falling back from WebSockets to HTTPS transport.'))

def recover(folder):
    folder = Path(folder).resolve()
    assert folder.is_relative_to(ROOT / 'runs')
    assert folder.name == 'model'
    assert not (folder / 'generation.json').exists()
    key = folder.parent.parent.name
    run = folder.parent.parent.parent
    family_error = json.loads((run / ('family_' + key.rsplit('_', 1)[1] + '_error.json')).read_text())
    assert 'exit=0, completed=True' in family_error['error']
    events = [json.loads(l) for l in (folder / 'events.jsonl').read_text().splitlines()]
    completed = [e for e in events if e['type'] == 'turn.completed']
    other = [e for e in events if e['type'] == 'item.completed' and e['item']['type'] not in ('agent_message', 'reasoning')]
    assert len(completed) == 1 and other and all(is_transport_notice(e) for e in other)
    answer = (folder / 'answer.txt').read_text()
    json.loads(answer)  # All these experiments use JSON schemas.
    prompt = (folder / 'prompt.txt').read_text()
    estimate = max(0., (folder / 'events.jsonl').stat().st_mtime - (folder / 'prompt.txt').stat().st_mtime)
    generation = {'model': 'gpt-6-astra', 'effort': 'medium', 'seconds': estimate,
                  'usage': completed[0]['usage'], 'tool_events': [], 'code': extract_code(answer),
                  'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(), 'structured_output': True,
                  'transport_notices': other, 'seconds_estimated_from_file_timestamps': True}
    proof = {'reason': 'Completed model response; only transport fallback notifications, no tool calls.',
             'original_family_error': family_error, 'transport_notices': other,
             'raw_sha256': {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                            for name in ('prompt.txt', 'answer.txt', 'events.jsonl', 'stderr.txt', 'schema.json')},
             'new_model_calls': 0, 'seconds_estimated_from_file_timestamps': True}
    dump(folder / 'transport_recovery.json', proof)
    dump(folder / 'generation.json', generation)
    return {'folder': str(folder), 'recovered': True, 'new_model_calls': 0}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folders', nargs='+')
    args = parser.parse_args()
    print(json.dumps([recover(p) for p in args.folders], indent=2))
