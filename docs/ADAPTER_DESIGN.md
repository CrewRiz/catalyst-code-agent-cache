# Catalyst Code Agent Cache Design

This adapter is a source-available wedge for coding-agent token efficiency. It
depends on the closed-source `catalyst-brain` SDK and keeps implementation
claims at the adapter boundary.

## Surfaces

| Coding-agent surface | Compact Catalyst behavior |
| --- | --- |
| Repo maps | File summaries and `hkvc://code/file/...` refs replace repeated full files. |
| File inspection | Full content is fetched only through `fetch_file`. |
| Terminal commands | Full stdout/stderr live behind `hkvc://task/.../result`. |
| Test logs | Basic pass/fail metadata stays in context; full logs are deferred. |
| Patch diffs | Diff text is stored behind `hkvc://code/patch/...` with stats in context. |
| Handoff | Rain snapshot plus compact refs replace raw transcript replay. |

## Benchmark Targets

- SWE-bench style repair loops: compare full transcript replay vs compact refs.
- Repo-scan loops: compare repeated file context vs `compact_repo_map`.
- Test-debug loops: compare full pytest logs vs `record_test_run`.
- Patch-review loops: compare full diffs vs `record_patch` summaries.
- Agent handoff: compare raw session transcript vs `compact_handoff`.

Primary metrics:

- input tokens avoided
- wall-clock latency
- full-log retrieval accuracy
- task success parity
- replay/audit completeness

## Commercial Boundary

Research and evaluation are allowed. Production coding agents, hosted tools,
enterprise deployments, customer pilots, and revenue workflows require a
license or pilot agreement through `hello@strategic-innovations.ai`.
