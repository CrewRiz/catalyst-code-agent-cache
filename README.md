# Catalyst Code Agent Cache

Source-available coding-agent context cache powered by the closed-source,
monetized `catalyst-brain` SDK.

This adapter targets Codex-style and Claude Code-style software engineering
loops where agents repeatedly resend repo scans, file snapshots, terminal logs,
test output, patches, and handoff notes. Catalyst keeps those high-volume
payloads behind compact handles until the agent explicitly asks to expand them.

Commercial, enterprise, hosted, revenue-generating, or customer pilot use
requires a written agreement:

```text
hello@strategic-innovations.ai
```

## Install

The public dependency is the Catalyst Brain SDK:

```bash
python -m pip install catalyst-brain
```

For local evaluation of this adapter:

```bash
git clone https://github.com/CrewRiz/catalyst-code-agent-cache
cd catalyst-code-agent-cache
python -m pip install -e ".[dev]"
pytest -q
catalyst-code-agent-cache-smoke
```

## Why This Adapter

Coding agents are context-hungry. A single session can duplicate the same repo
map, command output, test failure, and patch diff across many turns. That is a
direct cost, latency, and quality problem.

`catalyst-code-agent-cache` provides a drop-in context layer:

- compact repo maps instead of repeated full file payloads
- file content refs with explicit fetch
- deferred stdout/stderr for shell commands and test runs
- patch diff refs with changed-file and line stats
- compact Rain handoff state for agent-to-agent continuation
- savings reports suitable for benchmark and FinOps dashboards

## Example

```python
from catalyst_code_agent_cache import CatalystCodeAgentCache

cache = CatalystCodeAgentCache(dim=1024)

file_ref = cache.record_file(
    "src/billing.py",
    "def webhook(event):\n    return issue_api_key(event['tenant'])\n",
    tags=("billing", "license"),
)
test_ref = cache.record_test_run(
    "pytest -q",
    stdout="120 passed, 2 skipped in 8.4s\n",
    framework="pytest",
)

print(cache.search_files("billing license webhook", top_k=1))
print(cache.fetch_file(file_ref["content_ref"])["content"])
print(cache.fetch_command(test_ref["result_ref"])["stdout"])
print(cache.report())
```

## API Surface

| Method | Purpose |
| --- | --- |
| `record_file(path, content, tags=...)` | Store file content behind a compact ref. |
| `scan_repo(root)` | Index text files while ignoring generated/vendor directories. |
| `compact_repo_map()` | Return compact file summaries plus context savings. |
| `search_files(query)` | Search cached summaries without expanding full content. |
| `fetch_file(ref_or_path)` | Explicitly fetch full file content. |
| `record_command(...)` | Defer command stdout/stderr behind a task result ref. |
| `record_test_run(...)` | Compact test output and parse basic pass/fail counts. |
| `fetch_command(ref_or_task_id)` | Explicitly fetch full command output. |
| `record_patch(name, diff)` | Store patch diffs behind compact refs. |
| `compact_handoff(...)` | Export compact Rain-backed coding-agent handoff state. |
| `report()` | Summarize context/token savings across repo, logs, and patches. |

## Claim Boundary

This repository intentionally shows adapter behavior and measurable savings
without disclosing Catalyst Brain internals. Claims should be validated with
the included smoke tests, downstream benchmarks, and your own coding-agent
traces.

Use the public benchmark repository for reproducible SDK-level evidence:

```text
https://github.com/CrewRiz/catalyst-brain-benchmarks
```

## License Boundary

Research/evaluation is allowed. Production coding agents, enterprise
deployments, hosted tools, customer pilots, or revenue workflows require a
license. Contact `hello@strategic-innovations.ai`.
