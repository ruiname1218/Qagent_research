from __future__ import annotations
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'vendor/quanbench-plus'
RUNTIME = ROOT / 'runtime/benchmark'
FRAMEWORKS = ('qiskit', 'cirq', 'pennylane')

def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False))
    tmp.replace(path)

def tasks():
    return [dict(json.loads(line), framework=f) for f in FRAMEWORKS
            for line in (VENDOR / f'prompts/{f}.jsonl').read_text().splitlines() if line.strip()]

def prepare_runtime():
    (RUNTIME / 'prompts').mkdir(parents=True, exist_ok=True)
    for framework in FRAMEWORKS:
        for name in ('responses', 'results', 'model_responses'):
            (RUNTIME/name/framework/'feedback_loop').mkdir(parents=True, exist_ok=True)
    # The execution sandbox only gets upstream Python modules, never its JSON data.
    for package in ('feedback_loop', 'utils'):
        for source in (VENDOR / package).rglob('*.py'):
            dest = RUNTIME / source.relative_to(VENDOR)
            dest.parent.mkdir(parents=True, exist_ok=True)
            content = source.read_bytes()
            if not dest.exists() or dest.read_bytes() != content:
                # Do not truncate modules while another worker is importing them.
                with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as tmp:
                    tmp.write(content)
                    staged = Path(tmp.name)
                staged.replace(dest)

def evaluate(task, code, seed=1234, timeout=90, probe=None):
    interpreter_dir = Path(sys.executable).resolve().parents[1]
    interpreter_alias = Path(os.readlink(sys.executable)).parents[1]
    cmd = ['bwrap', '--die-with-parent', '--unshare-all', '--new-session',
           '--ro-bind', '/usr', '/usr', '--ro-bind', '/lib', '/lib',
           '--ro-bind', '/lib64', '/lib64', '--proc', '/proc', '--dev', '/dev',
           '--tmpfs', '/tmp', '--dir', '/work', '--chdir', '/work',
           '--ro-bind', str(interpreter_dir), str(interpreter_dir),
           '--ro-bind', str(interpreter_dir), str(interpreter_alias),
           '--ro-bind', str(ROOT / '.venv'), str(ROOT / '.venv'),
           '--ro-bind', str(RUNTIME), '/benchmark',
           '--ro-bind', str(ROOT / 'qagent/worker.py'), '/worker.py',
           sys.executable, '/worker.py']
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/tmp', 'OMP_NUM_THREADS': '1',
           'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'PYTHONWARNINGS': 'ignore'}
    request = {k: task[k] for k in ('framework', 'task_id', 'entry_point')}
    request.update(code=code, seed=seed)
    if probe is not None:
        request['probe'] = probe
    start = time.monotonic()
    try:
        proc = subprocess.run(cmd, input=json.dumps(request), text=True,
                              capture_output=True, timeout=timeout, env=env)
        if proc.returncode:
            return dict(compiled=True, ran=False, passed=False, infra_error=True,
                        error=proc.stderr[-4000:], seconds=time.monotonic()-start)
        result = json.loads(proc.stdout)
    except subprocess.TimeoutExpired:
        return dict(compiled=True, ran=False, passed=False, error='Execution timeout', seconds=timeout)
    except json.JSONDecodeError:
        return dict(compiled=True, ran=False, passed=False, infra_error=True,
                    error='Invalid worker output: ' + proc.stdout[-2000:])
    result.update(passed=False, seed=seed, seconds=time.monotonic()-start)
    if result['ran'] and probe is None:
        import numpy as np
        sys.path.insert(0, str(VENDOR))
        from utils.get_kl_div import get_kl_div
        refs = json.loads((VENDOR / 'canonical_results/canonical_solutions.json').read_text())
        expected = next(t['canonical_output'] for t in refs if t['task_id'] == task['task_id'])
        if len(result['output']) != len(expected):
            result['error'] = f"shape mismatch: model_probs len {len(result['output'])},canonical_probs len {len(expected)}"
        elif not np.all(np.isfinite(result['output'])):
            result['error'] = 'Non-finite output'
        else:
            kl, passed = get_kl_div(np.array(result['output']), np.array(expected))
            result.update(kl=float(kl), passed=passed)
    return result

def feedback(result):
    # Match upstream wording and information, including its omission of shape details.
    if not result['compiled']:
        return 'Your previous code did not compile.\n\nHere is the error:\n' + result['error'] + '\n\nPlease fix the code and respond with the FULL corrected code.'
    if not result['ran']:
        return 'Your code compiled but failed at runtime.\n\nHere is the error:\n' + result['error'] + '\n\nPlease fix the issue and respond with the FULL corrected code.'
    import numpy as np
    return 'Your code ran, but the output does NOT match the expected canonical output.\n\nGot (stringified): ' + str(np.array(result['output']))[:2000] + '\n\nPlease try again and respond with the FULL corrected code.'

def extract_code(text):
    blocks = re.findall(r'```(?:python)?\s*\n(.*?)```', text, flags=re.S)
    return max(blocks, key=len).strip() if blocks else text.strip()

DISABLED = ('shell_tool', 'unified_exec', 'multi_agent', 'apps', 'plugins',
            'browser_use', 'browser_use_external', 'computer_use', 'image_generation',
            'skill_search', 'sleep_tool', 'view_image')

def generate(prompt, directory, effort='medium', timeout=480, schema=None):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'prompt.txt').write_text(prompt)
    with tempfile.TemporaryDirectory(prefix='qagent-model-') as work:
        cmd = ['codex', 'exec', '--ignore-user-config', '--ephemeral', '--skip-git-repo-check',
               '-C', work, '-m', 'gpt-6-astra', '-c', f'model_reasoning_effort="{effort}"',
               '-c', 'web_search="disabled"', '-c', 'mcp_servers={}',
               '--json', '-o', str(directory / 'answer.txt')]
        for feature in DISABLED:
            cmd += ['--disable', feature]
        if schema:
            dump(directory/'schema.json', schema)
            cmd += ['--output-schema', str(directory/'schema.json')]
        cmd += ['-']
        start = time.monotonic()
        with (directory/'events.jsonl').open('w') as out, (directory/'stderr.txt').open('w') as err:
            proc = subprocess.run(cmd, input=prompt, text=True, stdout=out, stderr=err, timeout=timeout)
    events = [json.loads(l) for l in (directory/'events.jsonl').read_text().splitlines() if l.strip()]
    completed = [e for e in events if e['type'] == 'turn.completed']
    tools = [e for e in events if e['type'] == 'item.completed' and e['item']['type'] not in ('agent_message','reasoning')]
    if proc.returncode or not completed or tools:
        raise RuntimeError(f'Invalid model run: exit={proc.returncode}, completed={bool(completed)}, tool_events={tools}')
    answer = (directory/'answer.txt').read_text()
    result = {'model': 'gpt-6-astra', 'effort': effort, 'seconds': time.monotonic()-start,
              'usage': completed[-1].get('usage', {}), 'tool_events': tools,
              'code': extract_code(answer), 'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest()}
    result['structured_output'] = schema is not None
    dump(directory/'generation.json', result)
    return result
