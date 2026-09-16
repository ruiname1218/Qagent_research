"""Create a sanitized raw-trace archive from the private experiment workspace.

Run only by the release maintainer, from an experiment checkout that contains
`runs/`. The public release already contains the resulting archive and manifest.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tarfile
import tempfile


FILES = ('prompt.txt', 'answer.txt', 'events.jsonl', 'schema.json', 'generation.json', 'stderr.txt')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sanitize_text(text):
    return re.sub(r'/home/[^/\s]+', '[LOCAL_PATH]', text)


def sanitize_value(value):
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_value(item) for key, item in value.items() if key != 'thread_id'}
    return value


def sanitize_events(text):
    events = []
    for line in text.splitlines():
        event = sanitize_value(json.loads(line))
        events.append(json.dumps(event, ensure_ascii=False, separators=(',', ':')))
    return '\n'.join(events) + ('\n' if events else '')


def write_trace(destination, source, manifest, label):
    destination.mkdir(parents=True, exist_ok=True)
    record = source.parent / 'record.json'
    public_record = destination / 'record.json'
    public_record.write_text(json.dumps(sanitize_value(json.loads(record.read_text())),
                                        ensure_ascii=False, indent=2) + '\n')
    entry = {'label': label, 'source_record_sha256': digest(record),
             'files': {'record.json': {'source_sha256': digest(record), 'public_sha256': digest(public_record)}}}
    for name in FILES:
        path = source / name
        if not path.exists():
            continue
        text = path.read_text()
        if name == 'events.jsonl':
            text = sanitize_events(text)
        else:
            text = sanitize_text(text)
        out = destination / name
        out.write_text(text)
        entry['files'][name] = {'source_sha256': digest(path), 'public_sha256': digest(out)}
    manifest.append(entry)


def write_failure(destination, source, manifest, label):
    destination.mkdir(parents=True, exist_ok=True)
    entry = {'label': label, 'kind': 'empty_backend_failure', 'files': {}}
    for path in source.iterdir():
        if not path.is_file():
            continue
        text = path.read_text()
        if path.name == 'events.jsonl':
            text = sanitize_events(text)
        elif path.suffix == '.json':
            text = json.dumps(sanitize_value(json.loads(text)), ensure_ascii=False, indent=2) + '\n'
        else:
            text = sanitize_text(text)
        out = destination / path.name
        out.write_text(text)
        entry['files'][path.name] = {'source_sha256': digest(path), 'public_sha256': digest(out)}
    manifest.append(entry)


def index_records(source_root):
    index = {}
    for path in (source_root / 'runs').glob('*/*/attempt_*/record.json'):
        index[digest(path)] = path
    return index


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--release-root', type=Path, required=True)
    args = parser.parse_args()
    release = args.release_root.resolve()
    source = args.source_root.resolve()
    results = release / 'results'
    manifest = []
    with tempfile.TemporaryDirectory(prefix='quanbench-traces-') as tmp:
        stage = Path(tmp) / 'traces'
        record_index = index_records(source)
        provenance = json.loads((results / 'provenance.json').read_text())
        for proof in provenance:
            record = record_index[proof['source_record_sha256']]
            raw = record.parent / 'model'
            label = f"{proof['condition']}/{proof['case']}/attempt_{proof['attempt']}"
            write_trace(stage / label, raw, manifest, label)
        evidence = json.loads((results / 'ablation/no_peer_restart_full_results.json').read_text())
        for run_name, run in evidence['runs'].items():
            for row in run['tasks']:
                for record in row['records'][1:]:
                    attempt = record['attempt']
                    raw = source / 'runs' / run_name / row['key'] / f'attempt_{attempt}' / 'model'
                    label = f"{run_name}/{row['key']}/attempt_{attempt}"
                    write_trace(stage / label, raw, manifest, label)
        no_restart = json.loads((results / 'ablation/no_peer_no_restart_results.json').read_text())
        for row in no_restart['tasks']:
            for record in row['records'][1:]:
                attempt = record['attempt']
                raw = source / 'runs/no_peer_no_restart_r1' / row['key'] / f'attempt_{attempt}' / 'model'
                label = f"no_peer_no_restart_r1/{row['key']}/attempt_{attempt}"
                write_trace(stage / label, raw, manifest, label)
        for failure in sorted((source / 'runs/no_peer_no_restart_r1').glob(
                '*/attempt_*/failed_model_calls/usage_limit_1')):
            attempt_dir = failure.parent.parent
            key = attempt_dir.parent.name
            label = f"no_peer_no_restart_r1/{key}/{attempt_dir.name}/usage_limit_1"
            write_failure(stage / label, failure, manifest, label)
        manifest_path = stage / 'manifest.json'
        manifest_path.write_text(json.dumps({'trace_count': len(manifest), 'traces': manifest}, indent=2) + '\n')
        artifacts = release / 'artifacts'
        artifacts.mkdir(exist_ok=True)
        archive = artifacts / 'raw_traces_sanitized.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            tar.add(stage, arcname='raw_traces_sanitized')
        (artifacts / 'raw_traces_sanitized.sha256').write_text(
            digest(archive) + '  artifacts/raw_traces_sanitized.tar.gz\n')
        print(json.dumps({'traces': len(manifest), 'archive': str(archive), 'sha256': digest(archive)}, indent=2))


if __name__ == '__main__':
    main()
