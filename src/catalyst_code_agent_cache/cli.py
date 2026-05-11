from __future__ import annotations

import json

from catalyst_code_agent_cache import CatalystCodeAgentCache


def _source_file(index: int) -> tuple[str, str]:
    path = f"src/service_{index:02d}.py"
    content = "\n".join(
        [
            f"class Service{index}:",
            "    def run(self, tenant_id: str, payload: dict) -> dict:",
            "        # Synthetic fixture for token-efficiency smoke tests.",
            f"        return {{'tenant': tenant_id, 'feature': 'feature_{index}', 'payload': payload}}",
            "",
        ]
        * 18
    )
    return path, content


def main() -> int:
    cache = CatalystCodeAgentCache(dim=1024)
    for index in range(18):
        path, content = _source_file(index)
        tags = ("billing", "license") if index % 3 == 0 else ("repo", "agent")
        cache.record_file(path, content, tags=tags)

    stdout = "\n".join([f"tests/test_service_{i}.py::test_flow PASSED" for i in range(80)])
    stdout += "\n80 passed, 2 skipped, 1 warning in 14.31s\n"
    test = cache.record_test_run("pytest -q", stdout=stdout, exit_code=0, framework="pytest")

    patch = cache.record_patch(
        "license-gate",
        "\n".join(
            [
                "diff --git a/src/service_00.py b/src/service_00.py",
                "--- a/src/service_00.py",
                "+++ b/src/service_00.py",
                "+def enforce_license(api_key: str) -> bool:",
                "+    return bool(api_key)",
                "-def old_gate():",
                "-    return True",
            ]
        ),
    )
    handoff = cache.compact_handoff(
        objective="finish coding-agent token-efficiency adapter",
        current_plan=("repo map", "deferred logs", "patch refs"),
        next_steps=("publish benchmark", "compare against raw transcript baseline"),
    )

    print(
        json.dumps(
            {
                "capabilities": cache.capabilities(),
                "repo_map": cache.compact_repo_map(limit=5),
                "search": cache.search_files("billing license tenant", top_k=3),
                "test": test,
                "patch": patch,
                "handoff": {
                    "catalyst": handoff["catalyst"],
                    "fileRefs": len(handoff["fileRefs"]),
                    "commandRefs": len(handoff["commandRefs"]),
                    "patchRefs": len(handoff["patchRefs"]),
                },
                "report": cache.report(),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0
