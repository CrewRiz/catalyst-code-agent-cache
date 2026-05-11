from __future__ import annotations

import pytest


def test_file_refs_search_and_fetch_do_not_expand_content_by_default():
    from catalyst_code_agent_cache import CatalystCodeAgentCache

    cache = CatalystCodeAgentCache(dim=512)
    compact = cache.record_file(
        "src/billing.py",
        "def webhook(event):\n    return issue_api_key(event['tenant'])\n",
        tags=("stripe", "api-key"),
    )

    hits = cache.search_files("stripe webhook api key")

    assert compact["content_ref"].startswith("hkvc://code/file/")
    assert hits[0]["path"] == "src/billing.py"
    assert "content" not in hits[0]
    assert "issue_api_key" in cache.fetch_file(hits[0]["content_ref"])["content"]


def test_command_and_test_logs_are_deferred_with_savings():
    from catalyst_code_agent_cache import CatalystCodeAgentCache

    cache = CatalystCodeAgentCache(dim=512)
    stdout = "\n".join(f"tests/test_{i}.py::test_case PASSED" for i in range(200))
    stdout += "\n200 passed, 3 skipped in 11.20s\n"

    compact = cache.record_test_run("pytest -q", stdout=stdout, exit_code=0, framework="pytest")
    fetched = cache.fetch_command(compact["result_ref"])

    assert compact["testSummary"]["passed"] == 200
    assert compact["saved_context_tokens"] > 1000
    assert compact["savedPct"] > 90.0
    assert fetched["stdout"] == stdout
    assert fetched["metadata"]["test_summary"]["skipped"] == 3


def test_patch_refs_and_handoff_report_compact_state():
    from catalyst_code_agent_cache import CatalystCodeAgentCache

    cache = CatalystCodeAgentCache(dim=512)
    cache.record_file("src/app.py", "def app():\n    return 'ok'\n")
    patch = cache.record_patch(
        "app-change",
        "\n".join(
            [
                "diff --git a/src/app.py b/src/app.py",
                "--- a/src/app.py",
                "+++ b/src/app.py",
                "+def health():",
                "+    return 'healthy'",
                "-def legacy():",
                "-    return 'old'",
            ]
        ),
    )
    handoff = cache.compact_handoff(objective="ship adapter", current_plan=("tests",), next_steps=("publish",))

    assert patch["stats"]["file_count"] == 1
    assert patch["savedPct"] > 0
    assert cache.fetch_patch(patch["patch_ref"])["stats"]["additions"] == 2
    assert handoff["rain"]["agent_id"] == "catalyst-code-agent-cache"
    assert handoff["catalyst"]["savedPct"] > 0
    assert cache.report()["patches"] == 1


def test_scan_repo_ignores_generated_files(tmp_path):
    from catalyst_code_agent_cache import CatalystCodeAgentCache

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def checkout():\n    return 'paid'\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "app.pyc").write_bytes(b"ignored")

    cache = CatalystCodeAgentCache(dim=512)
    scan = cache.scan_repo(tmp_path)

    assert scan["indexed"] == 1
    assert cache.search_files("checkout")[0]["path"] == "src/app.py"
    assert scan["repo_map"]["catalyst"]["savedPct"] >= 0


def test_builtin_tool_discovery_and_license_boundary():
    from catalyst_code_agent_cache import CatalystCodeAgentCache, LicenseError

    cache = CatalystCodeAgentCache(dim=512)
    matches = cache.discover_tools("store pytest output logs", limit=1)

    assert matches[0]["name"] == "code_agent.record_test_run"
    assert cache.capabilities()["commercial_contact"] == "hello@strategic-innovations.ai"
    with pytest.raises(LicenseError):
        CatalystCodeAgentCache(purpose="enterprise production")
