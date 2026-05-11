from catalyst_code_agent_cache import CatalystCodeAgentCache


cache = CatalystCodeAgentCache(dim=1024)
file_ref = cache.record_file(
    "src/app.py",
    "def checkout(session):\n    return issue_license(session.customer_id)\n",
    tags=("billing", "license"),
)
test_ref = cache.record_test_run("pytest -q", stdout="42 passed, 1 skipped in 3.2s\n", framework="pytest")

print(file_ref)
print(cache.search_files("checkout license", top_k=1))
print(test_ref)
print(cache.fetch_command(test_ref["result_ref"])["stdout"])
print(cache.report())
