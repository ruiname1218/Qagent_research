# Release artifacts

`raw_traces_sanitized.tar.gz` contains the sanitized Codex trace files used for
all six trajectories in the comparison table. It includes prompt, structured
answer, event stream, schema, generation metadata, stderr and record files for
every completed model call, plus the 16 empty usage-limit failures in the 102/126
run. Thread identifiers and local filesystem paths are redacted.
The companion SHA-256 file verifies the archive.

Extract with:

```bash
tar -xzf artifacts/raw_traces_sanitized.tar.gz
sha256sum -c artifacts/raw_traces_sanitized.sha256
```

The trace manifest maps every archived file to its source and public hashes.
