# Reproducing the artifact

## Levels of reproduction

1. **Audit the release**: verifies bundled traces, hashes, coverage and stopping budgets without an LLM or benchmark download.
2. **Replay saved candidates**: evaluates saved final code against the pinned QuanBench+ checkout.
3. **Run a fresh replication**: queries GPT-6 Astra through Codex again; hosted-model sampling is stochastic.

## Native setup

```bash
git clone https://github.com/ruiname1218/Qagent_research.git
cd Qagent_research
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.lock
make setup
make audit
```

Linux requires `bwrap` for the evaluator sandbox. `make setup` downloads QuanBench+ at commit `2dfd1a863b13d3762a734ed96742adb39e65e34b`.

## Replay all reported candidates

```bash
make replay RUNS=reproduced
```

This writes new evaluation records under `reproduced/`; it never changes bundled results.

## Docker

```bash
docker build -t quanbench-repair:local .
docker run --rm --privileged quanbench-repair:local make audit
```

The evaluator uses Linux user namespaces through Bubblewrap, so common Docker installations need `--privileged`.

## Fresh model replication

Authenticate the Codex CLI and ensure access to `gpt-6-astra`, then run:

```bash
make fresh
```

It generates one new common initial set, reports that set as the one-shot run,
then runs the five repair trajectories from it. Record the Codex CLI version and
release timestamp with a new replication.

## Trace audit

`artifacts/raw_traces_sanitized.tar.gz` contains 1,197 completed condition-level
trace records and 16 empty usage-limit failure records. Local paths and Codex
thread identifiers are redacted.

```bash
sha256sum -c artifacts/raw_traces_sanitized.sha256
tar -xzf artifacts/raw_traces_sanitized.tar.gz
```

The trace manifest stores source and public hashes for each file. Credentials, session identifiers and unredacted local logs are not included.
