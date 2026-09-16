PYTHON ?= python3
RUNS ?= reproduced

.PHONY: setup audit test replay-main replay-no-sharing replay fresh-main fresh-no-sharing fresh docker-build docker-audit

setup:
	./scripts/setup_benchmark.sh

audit:
	$(PYTHON) scripts/audit_results.py
	$(PYTHON) scripts/audit_ablation_results.py
	$(PYTHON) scripts/audit_no_peer_restart_full.py
	$(PYTHON) scripts/audit_no_peer_no_restart.py

test:
	$(PYTHON) -m unittest discover -s tests -v

replay-main:
	$(PYTHON) scripts/replay.py oneshot --output $(RUNS)/oneshot
	$(PYTHON) scripts/replay.py feedback --output $(RUNS)/feedback
	$(PYTHON) scripts/replay.py restart --output $(RUNS)/restart

replay-no-sharing:
	$(PYTHON) scripts/replay.py no_peer_restart_r1 --output $(RUNS)/no_peer_restart_r1
	$(PYTHON) scripts/replay.py no_peer_restart_r2 --output $(RUNS)/no_peer_restart_r2
	$(PYTHON) scripts/replay.py no_peer_no_restart --output $(RUNS)/no_peer_no_restart

replay: replay-main replay-no-sharing

fresh-main:
	@echo "Requires an authenticated Codex CLI with access to gpt-6-astra."
	$(PYTHON) scripts/restore_initial.py --run fresh_initial
	$(PYTHON) -m qagent oneshot --run fresh_oneshot --workers 3
	$(PYTHON) -m qagent feedback --run fresh_feedback --initial-run fresh_initial --attempts 6 --workers 3
	$(PYTHON) -m qagent restart --run fresh_restart --initial-run fresh_initial --attempts 6 --workers 6

fresh-no-sharing:
	@echo "Requires fresh_initial from make fresh-main and an authenticated Codex CLI."
	$(PYTHON) -m qagent.no_peer_no_restart --run fresh_no_peer_restart_r1 --initial-run fresh_initial --attempts 6 --workers 6 --with-restart
	$(PYTHON) -m qagent.no_peer_no_restart --run fresh_no_peer_restart_r2 --initial-run fresh_initial --attempts 6 --workers 6 --with-restart
	$(PYTHON) -m qagent.no_peer_no_restart --run fresh_no_peer_no_restart --initial-run fresh_initial --attempts 6 --workers 6

fresh: fresh-main fresh-no-sharing

docker-build:
	docker build -t quanbench-repair:local .

docker-audit:
	docker run --rm --privileged quanbench-repair:local make audit
