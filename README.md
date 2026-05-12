# Catalyst Code Agent Cache

Source-available coding-agent context cache powered by the public
`catalyst-brain` SDK wheel.

This adapter targets Codex-style and Claude Code-style software engineering
loops where agents repeatedly resend repo scans, file snapshots, terminal logs,
test output, patches, and handoff notes. Catalyst keeps those high-volume
payloads behind compact handles until the agent explicitly asks to expand them.

The Catalyst Brain free tier is designed for easy evaluation: no registration,
no signup, and no API key are required for early local usage. Most coding-agent
experiments, benchmark runs, and prototypes should not hit free-tier limits
while you are getting started.

When this adapter moves toward production coding agents, hosted tools,
enterprise deployment, customer pilots, or higher-volume API usage, contact:

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

## Free Tier And Production Use

Install `catalyst-brain` from PyPI and evaluate this adapter without signup,
registration, or an API key. The free tier covers early research, personal
evaluation, benchmark reproduction, prototypes, and integration testing.

Most users should not hit free-tier limits during early development. If your use
case becomes production coding agents, hosted tools, enterprise deployment,
customer pilots, revenue workflows, or needs higher quotas/support, contact
`hello@strategic-innovations.ai`.
