"""Unprivileged execution: no reference solutions, network, or user files mounted."""
import contextlib
import io
import json
import random
import sys
import traceback

sys.path.insert(0, '/benchmark')

def main():
    request = json.load(sys.stdin)
    import numpy as np
    np.random.seed(request['seed'])
    random.seed(request['seed'])
    from qiskit_aer import AerSimulator
    original_run = AerSimulator.run
    def seeded_run(self, circuits, *args, **kwargs):
        kwargs.setdefault('seed_simulator', request['seed'])
        return original_run(self, circuits, *args, **kwargs)
    AerSimulator.run = seeded_run
    from feedback_loop.api import get_probs_qiskit, get_probs_cirq, get_probs_pennylane, load_global_inputs
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            if request.get('probe'):
                namespace = {}
                exec(request['code'], namespace, namespace)
                exec(request['probe'], namespace, namespace)
                print(json.dumps(namespace.get('diagnostic_result'), default=str))
                output = np.array([])
            else:
                output = {'qiskit': get_probs_qiskit, 'cirq': get_probs_cirq,
                          'pennylane': get_probs_pennylane}[request['framework']](
                    request['task_id'], request['code'], request['entry_point'], 1000,
                    load_global_inputs(request['framework']))
        result = {'compiled': True, 'ran': True, 'output': output.tolist(), 'error': None}
    except Exception as exc:
        result = {'compiled': not isinstance(exc, SyntaxError), 'ran': False,
                  'output': None, 'error': traceback.format_exc()}
    result['stdout'] = captured.getvalue()[:4000]
    print(json.dumps(result))

if __name__ == '__main__':
    main()
