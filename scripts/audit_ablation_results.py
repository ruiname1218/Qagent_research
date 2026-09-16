"""Audit the two information-sharing ablations without calling a model."""
from pathlib import Path
import csv
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
AB = ROOT / "results" / "ablation"
EXPECTED = {f"{framework}_{i:02d}" for framework in ("qiskit", "cirq", "pennylane")
            for i in range(1, 45) if i not in (5, 38)}


def load(name):
    return json.loads((AB / name).read_text())


def main():
    peer = load("peer_code_ablation_results.json")
    none = load("no_peer_results.json")
    assert peer["primary"]["families"] == 42
    assert none["primary"]["families"] == 42
    assert peer["primary"]["predeclared_support_criterion_met"] is False
    assert none["primary"]["predeclared_support_criterion_met"] is False

    peer_expected = {
        "shared_r1": 107, "masked_r1": 107,
        "shared_r2": 110, "masked_r2": 107,
    }
    none_expected = {
        "outcomes_r1": 106, "none_r1": 103,
        "outcomes_r2": 107, "none_r2": 103,
    }
    for arm, score in peer_expected.items():
        assert peer["summaries"][arm]["passed"] == score
        assert len(peer["outcomes"]) == 126
        assert set(peer["outcomes"]) == EXPECTED
    for arm, score in none_expected.items():
        assert none["summaries"][arm]["passed"] == score
        assert len(none["outcomes"]) == 126
        assert set(none["outcomes"]) == EXPECTED

    for arm, audit in peer["audits"].items():
        assert audit["completed"] == 126
        assert audit["source_and_actual_prompts_reconstructed"]
    for arm, audit in none["audits"].items():
        assert audit["completed"] == 126
        assert audit["source_and_actual_prompts_reconstructed"]
        if arm.startswith("none_"):
            assert audit["none_condition_has_zero_peer_evidence_and_history_rows"]

    with (AB / "cases.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["experiment", "condition", "case", "passed"])
        for experiment, report in (("peer_code", peer), ("all_peer_information", none)):
            for key, outcomes in report["outcomes"].items():
                for condition, passed in outcomes.items():
                    writer.writerow([experiment, condition, key, int(passed)])

    manifest = {}
    for path in sorted(AB.iterdir()):
        if path.name == "checksums.json" or not path.is_file():
            continue
        manifest[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (AB / "checksums.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("PASS: 8 ablation trajectories, 1008 case outcomes, and actual-input audits verified.")
    print("Code visibility: 107/107 and 110/107; all peer information: 106/103 and 107/103.")
    print("Neither predeclared consistency criterion was met; no superiority claim is emitted.")


if __name__ == "__main__":
    main()
