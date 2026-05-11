from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import catalyst_hdc as hdc
from catalyst_brain import CatalystTokenKernel, ToolSpec

from catalyst_code_agent_cache.license import COMMERCIAL_CONTACT, assert_research_use


_IGNORED_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
}
_IGNORED_GLOBS = (
    "*.egg-info/*",
    "*.lock",
    "*.log",
    "*.pyc",
    "*.so",
    "*.dylib",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.pdf",
    "*.zip",
    "*.tar",
    "*.gz",
)
_TEXT_EXTENSIONS = {
    "",
    ".cfg",
    ".css",
    ".go",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".py",
    ".rs",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _json_bytes(value: Any) -> int:
    return len(_canonical_json(value).encode("utf-8"))


def _estimate_tokens(byte_count: int) -> int:
    return max(1, (byte_count + 3) // 4)


def _saved_pct(compact_bytes: int, full_bytes: int) -> float:
    if full_bytes <= 0:
        return 0.0
    return round(max(0.0, 100.0 * (1.0 - compact_bytes / full_bytes)), 4)


def _digest(value: str, *, size: int = 8) -> str:
    return hashlib.blake2b(value.encode("utf-8", errors="replace"), digest_size=size).hexdigest()


def _normalise_tags(tags: Iterable[str]) -> tuple[str, ...]:
    out: list[str] = []
    for tag in tags:
        clean = str(tag).strip().lower()
        if clean and clean not in out:
            out.append(clean)
    return tuple(out)


def _terms(value: str) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in value)
    return {part for part in cleaned.split() if part}


def _language_for_path(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".go": "go",
        ".js": "javascript",
        ".jsx": "javascript",
        ".md": "markdown",
        ".py": "python",
        ".rs": "rust",
        ".sh": "shell",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".yaml": "yaml",
        ".yml": "yaml",
    }.get(suffix, suffix[1:] or "text")


def _summarise_content(content: str, *, max_chars: int = 360) -> str:
    lines: list[str] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        if len(line) > 120:
            line = line[:117] + "..."
        lines.append(line)
        if len(" ".join(lines)) >= max_chars or len(lines) == 5:
            break
    summary = " ".join(lines) or "empty file"
    return summary[:max_chars]


def _is_ignored(rel_path: Path, ignore_globs: Iterable[str]) -> bool:
    rel = rel_path.as_posix()
    if any(part in _IGNORED_DIRS for part in rel_path.parts):
        return True
    for pattern in (*_IGNORED_GLOBS, *tuple(ignore_globs)):
        if fnmatch.fnmatch(rel, pattern) or any(fnmatch.fnmatch(part, pattern) for part in rel_path.parts):
            return True
    return False


def _should_index(path: Path) -> bool:
    return path.suffix.lower() in _TEXT_EXTENSIONS


def _parse_test_summary(stdout: str, stderr: str) -> dict[str, int]:
    text = f"{stdout}\n{stderr}".lower()
    summary = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0, "warnings": 0}
    patterns = {
        "passed": r"(\d+)\s+passed",
        "failed": r"(\d+)\s+failed",
        "errors": r"(\d+)\s+errors?",
        "skipped": r"(\d+)\s+skipped",
        "warnings": r"(\d+)\s+warnings?",
    }
    for key, pattern in patterns.items():
        matches = re.findall(pattern, text)
        summary[key] = sum(int(match) for match in matches)
    return summary


def _parse_patch_stats(diff: str) -> dict[str, Any]:
    files: list[str] = []
    additions = 0
    deletions = 0
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                files.append(parts[3][2:] if parts[3].startswith("b/") else parts[3])
        elif line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return {
        "files": files,
        "file_count": len(files),
        "additions": additions,
        "deletions": deletions,
    }


@dataclass(frozen=True)
class FileSnapshot:
    path: str
    summary: str
    content: str
    digest: str
    byte_count: int
    language: str
    tags: tuple[str, ...]
    vector: list[float]
    created_at: float

    @property
    def ref(self) -> str:
        return f"hkvc://code/file/{self.digest}"

    @property
    def full_bytes(self) -> int:
        return _json_bytes(
            {
                "path": self.path,
                "summary": self.summary,
                "content": self.content,
                "language": self.language,
                "tags": self.tags,
            }
        )


@dataclass(frozen=True)
class CommandSnapshot:
    task_id: str
    command: str
    kind: str
    status: str
    exit_code: Optional[int]
    stdout: str
    stderr: str
    metadata: dict[str, Any]
    created_at: float

    @property
    def result_ref(self) -> str:
        return f"hkvc://task/{self.task_id}/result"

    @property
    def full_bytes(self) -> int:
        return _json_bytes(
            {
                "command": self.command,
                "stdout": self.stdout,
                "stderr": self.stderr,
                "metadata": self.metadata,
            }
        )


@dataclass(frozen=True)
class PatchSnapshot:
    task_id: str
    name: str
    summary: str
    diff: str
    stats: dict[str, Any]
    created_at: float

    @property
    def ref(self) -> str:
        return f"hkvc://code/patch/{self.task_id}"

    @property
    def full_bytes(self) -> int:
        return _json_bytes({"name": self.name, "summary": self.summary, "diff": self.diff, "stats": self.stats})


class CatalystCodeAgentCache:
    """Coding-agent context cache backed by the catalyst-brain SDK.

    The adapter stores verbose repository, command, test, and patch payloads
    behind compact handles so agent loops can pass references until full data
    is explicitly needed.
    """

    def __init__(self, *, dim: int = 4096, purpose: str = "research", preview_chars: int = 160) -> None:
        assert_research_use(purpose)
        self.dim = dim
        self.purpose = purpose
        self.kernel = CatalystTokenKernel(dim=dim, preview_chars=preview_chars)
        self._files: dict[str, FileSnapshot] = {}
        self._file_refs: dict[str, str] = {}
        self._commands: dict[str, CommandSnapshot] = {}
        self._patches: dict[str, PatchSnapshot] = {}
        self._register_builtin_tools()

    def record_file(
        self,
        path: str,
        content: str | None = None,
        *,
        summary: str | None = None,
        language: str | None = None,
        tags: Iterable[str] = (),
    ) -> dict[str, Any]:
        """Store a source file or file summary and return a compact handle."""
        if content is None and summary is None:
            raise ValueError("record_file requires content or summary")
        stored_content = content or ""
        file_summary = summary or _summarise_content(stored_content)
        file_language = language or _language_for_path(path)
        clean_tags = _normalise_tags((file_language, *tags))
        digest = _digest(f"{path}\0{stored_content}\0{file_summary}\0{clean_tags}")
        vector = hdc.hv_hash_string(f"{path} {file_summary} {' '.join(clean_tags)}", self.dim)
        snapshot = FileSnapshot(
            path=path,
            summary=file_summary,
            content=stored_content,
            digest=digest,
            byte_count=len(stored_content.encode("utf-8")),
            language=file_language,
            tags=clean_tags,
            vector=vector,
            created_at=time.time(),
        )
        self._files[path] = snapshot
        self._file_refs[snapshot.ref] = path
        return self._compact_file(snapshot)

    def scan_repo(
        self,
        root: str | Path = ".",
        *,
        max_files: int = 200,
        max_file_bytes: int = 96_000,
        ignore_globs: Iterable[str] = (),
    ) -> dict[str, Any]:
        """Index text files from a repo without sending full contents to context."""
        root_path = Path(root).resolve()
        indexed = 0
        skipped = 0
        for path in sorted(root_path.rglob("*")):
            if indexed >= max_files:
                break
            if not path.is_file():
                continue
            rel_path = path.relative_to(root_path)
            if _is_ignored(rel_path, ignore_globs) or not _should_index(path):
                skipped += 1
                continue
            try:
                if path.stat().st_size > max_file_bytes:
                    skipped += 1
                    continue
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                skipped += 1
                continue
            self.record_file(rel_path.as_posix(), content, tags=("repo-scan",))
            indexed += 1

        repo_map = self.compact_repo_map(limit=min(indexed, 50) or 1)
        return {
            "root": str(root_path),
            "indexed": indexed,
            "skipped": skipped,
            "repo_map": repo_map,
        }

    def compact_repo_map(self, *, limit: int = 50, cursor: str | None = None) -> dict[str, Any]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        start = int(cursor or 0)
        if start < 0:
            raise ValueError("cursor must be non-negative")
        snapshots = sorted(self._files.values(), key=lambda item: item.path)
        selected = snapshots[start : start + limit]
        files = [self._compact_file(snapshot) for snapshot in selected]
        next_cursor = str(start + limit) if start + limit < len(snapshots) else None
        compact_bytes = _json_bytes(files)
        full_bytes = sum(snapshot.full_bytes for snapshot in snapshots)
        return {
            "files": files,
            "nextCursor": next_cursor,
            "catalyst": {
                "compactBytes": compact_bytes,
                "fullBytes": full_bytes,
                "savedContextTokens": max(0, _estimate_tokens(full_bytes) - _estimate_tokens(compact_bytes)),
                "savedPct": _saved_pct(compact_bytes, full_bytes),
            },
        }

    def search_files(self, query: str, *, top_k: int = 5, include_content: bool = False) -> list[dict[str, Any]]:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        q_terms = _terms(query)
        q_vector = hdc.hv_hash_string(query, self.dim)
        scored: list[tuple[float, FileSnapshot]] = []
        for snapshot in self._files.values():
            haystack = " ".join((snapshot.path, snapshot.summary, snapshot.language, *snapshot.tags))
            overlap = len(q_terms & _terms(haystack)) / max(1, len(q_terms))
            phrase_bonus = 0.25 if query.lower() in haystack.lower() else 0.0
            resonance = max(0.0, hdc.resonance(q_vector, snapshot.vector)) * 0.10
            scored.append((overlap + phrase_bonus + resonance, snapshot))
        scored.sort(key=lambda item: (-item[0], item[1].path))
        return [
            self._compact_file(snapshot, score=score, include_content=include_content)
            for score, snapshot in scored[:top_k]
        ]

    def fetch_file(self, ref_or_path: str) -> dict[str, Any]:
        path = self._file_refs.get(ref_or_path, ref_or_path)
        try:
            snapshot = self._files[path]
        except KeyError as exc:
            raise KeyError(f"Unknown file reference or path: {ref_or_path}") from exc
        return {
            "path": snapshot.path,
            "summary": snapshot.summary,
            "content": snapshot.content,
            "content_digest": snapshot.digest,
            "bytes": snapshot.byte_count,
            "estimated_tokens": _estimate_tokens(snapshot.byte_count),
            "language": snapshot.language,
            "tags": list(snapshot.tags),
        }

    def record_command(
        self,
        command: str,
        *,
        stdout: str = "",
        stderr: str = "",
        status: str = "completed",
        exit_code: int | None = None,
        cwd: str | None = None,
        kind: str = "command",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Store full command output behind a compact task reference."""
        meta = {"surface": "coding-agent", "kind": kind, **(metadata or {})}
        if cwd:
            meta["cwd"] = cwd
        if exit_code is not None:
            meta["exit_code"] = exit_code
        compact = self.kernel.create_code_execution_task(
            code=command,
            stdout=stdout,
            stderr=stderr,
            status=status,
            metadata=meta,
        )
        task_id = compact["task_id"]
        snapshot = CommandSnapshot(
            task_id=task_id,
            command=command,
            kind=kind,
            status=status,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            metadata=meta,
            created_at=time.time(),
        )
        self._commands[task_id] = snapshot
        compact_bytes = _json_bytes(compact)
        compact["kind"] = kind
        compact["exit_code"] = exit_code
        compact["savedPct"] = _saved_pct(compact_bytes, snapshot.full_bytes)
        return compact

    def record_test_run(
        self,
        command: str,
        *,
        stdout: str = "",
        stderr: str = "",
        exit_code: int | None = None,
        framework: str | None = None,
    ) -> dict[str, Any]:
        summary = _parse_test_summary(stdout, stderr)
        failed = bool(summary["failed"] or summary["errors"] or (exit_code not in (None, 0)))
        compact = self.record_command(
            command,
            stdout=stdout,
            stderr=stderr,
            status="failed" if failed else "completed",
            exit_code=exit_code,
            kind="test",
            metadata={"framework": framework or "unknown", "test_summary": summary},
        )
        compact["testSummary"] = summary
        return compact

    def fetch_command(self, ref_or_task_id: str) -> dict[str, Any]:
        task_id = self._task_id_from_ref(ref_or_task_id)
        result = self.kernel.fetch_task_result(task_id)
        snapshot = self._commands.get(task_id)
        if snapshot is not None:
            result["kind"] = snapshot.kind
            result["exit_code"] = snapshot.exit_code
            result["created_at"] = snapshot.created_at
        return result

    def record_patch(self, name: str, diff: str, *, summary: str | None = None) -> dict[str, Any]:
        stats = _parse_patch_stats(diff)
        patch_summary = summary or f"{stats['file_count']} files, +{stats['additions']} -{stats['deletions']}"
        compact = self.kernel.create_code_execution_task(
            code=f"patch:{name}",
            stdout=diff,
            stderr="",
            status="completed",
            metadata={"surface": "coding-agent-patch", "name": name, "summary": patch_summary, "stats": stats},
        )
        task_id = compact["task_id"]
        snapshot = PatchSnapshot(
            task_id=task_id,
            name=name,
            summary=patch_summary,
            diff=diff,
            stats=stats,
            created_at=time.time(),
        )
        self._patches[task_id] = snapshot
        compact_bytes = _json_bytes(
            {"name": name, "summary": patch_summary, "stats": stats, "ref": snapshot.ref, "task_id": task_id}
        )
        return {
            "patch_ref": snapshot.ref,
            "task_id": task_id,
            "summary": patch_summary,
            "stats": stats,
            "saved_context_tokens": max(0, _estimate_tokens(snapshot.full_bytes) - _estimate_tokens(compact_bytes)),
            "savedPct": _saved_pct(compact_bytes, snapshot.full_bytes),
        }

    def fetch_patch(self, ref_or_task_id: str) -> dict[str, Any]:
        task_id = ref_or_task_id.removeprefix("hkvc://code/patch/")
        try:
            snapshot = self._patches[task_id]
        except KeyError as exc:
            raise KeyError(f"Unknown patch reference or task id: {ref_or_task_id}") from exc
        return {
            "patch_ref": snapshot.ref,
            "task_id": snapshot.task_id,
            "name": snapshot.name,
            "summary": snapshot.summary,
            "stats": snapshot.stats,
            "diff": snapshot.diff,
        }

    def discover_tools(self, query: str, *, limit: int = 5, include_schema: bool = False) -> list[dict[str, Any]]:
        return self.kernel.discover(query, limit=limit, include_schema=include_schema)

    def compact_handoff(
        self,
        *,
        objective: str,
        current_plan: Iterable[str] = (),
        next_steps: Iterable[str] = (),
        blockers: Iterable[str] = (),
        agent_id: str = "catalyst-code-agent-cache",
    ) -> dict[str, Any]:
        """Return compact state for handoff between coding agents."""
        rain = self.kernel.export_rain_snapshot(agent_id=agent_id)
        file_refs = [self._compact_file(snapshot) for snapshot in sorted(self._files.values(), key=lambda item: item.path)]
        command_refs = [self.kernel.compact_task_status(task_id) for task_id in self._commands]
        patch_refs = [
            {"patch_ref": patch.ref, "name": patch.name, "summary": patch.summary, "stats": patch.stats}
            for patch in self._patches.values()
        ]
        compact = {
            "objective": objective,
            "currentPlan": list(current_plan),
            "nextSteps": list(next_steps),
            "blockers": list(blockers),
            "fileRefs": file_refs,
            "commandRefs": command_refs,
            "patchRefs": patch_refs,
            "rain": rain,
        }
        full = {
            "objective": objective,
            "currentPlan": list(current_plan),
            "nextSteps": list(next_steps),
            "blockers": list(blockers),
            "files": [self.fetch_file(snapshot.ref) for snapshot in self._files.values()],
            "commands": [self.fetch_command(task_id) for task_id in self._commands],
            "patches": [self.fetch_patch(task_id) for task_id in self._patches],
            "rain": rain,
        }
        compact_bytes = _json_bytes(compact)
        full_bytes = _json_bytes(full)
        compact["catalyst"] = {
            "compactBytes": compact_bytes,
            "fullBytes": full_bytes,
            "savedContextTokens": max(0, _estimate_tokens(full_bytes) - _estimate_tokens(compact_bytes)),
            "savedPct": _saved_pct(compact_bytes, full_bytes),
        }
        return compact

    def capabilities(self) -> dict[str, Any]:
        return {
            "sdk_dependency": "catalyst-brain",
            "repo_map_compaction": True,
            "deferred_command_outputs": True,
            "test_log_triage": True,
            "patch_diff_refs": True,
            "rain_state_handoff": True,
            "commercial_contact": COMMERCIAL_CONTACT,
        }

    def report(self) -> dict[str, Any]:
        repo_map = self.compact_repo_map(limit=max(1, len(self._files)))
        command_compact = [self.kernel.compact_task_status(task_id) for task_id in self._commands]
        command_compact_bytes = _json_bytes(command_compact)
        command_full_bytes = sum(snapshot.full_bytes for snapshot in self._commands.values())
        patch_compact = [
            {"patch_ref": patch.ref, "summary": patch.summary, "stats": patch.stats}
            for patch in self._patches.values()
        ]
        patch_compact_bytes = _json_bytes(patch_compact)
        patch_full_bytes = sum(snapshot.full_bytes for snapshot in self._patches.values())
        compact_bytes = repo_map["catalyst"]["compactBytes"] + command_compact_bytes + patch_compact_bytes
        full_bytes = repo_map["catalyst"]["fullBytes"] + command_full_bytes + patch_full_bytes
        rain = self.kernel.export_rain_snapshot(agent_id="catalyst-code-agent-cache")
        return {
            "files": len(self._files),
            "commands": len(self._commands),
            "patches": len(self._patches),
            "compact_bytes": compact_bytes,
            "full_bytes": full_bytes,
            "context_saved_tokens": max(0, _estimate_tokens(full_bytes) - _estimate_tokens(compact_bytes)),
            "context_saved_pct": _saved_pct(compact_bytes, full_bytes),
            "rain_estimated_reduction_ratio": rain["estimated_reduction_ratio"],
            "commercial_contact": COMMERCIAL_CONTACT,
        }

    def _compact_file(
        self,
        snapshot: FileSnapshot,
        *,
        score: float | None = None,
        include_content: bool = False,
    ) -> dict[str, Any]:
        compact = {
            "path": snapshot.path,
            "summary": snapshot.summary[:220],
            "content_ref": snapshot.ref,
            "content_digest": snapshot.digest,
            "bytes": snapshot.byte_count,
            "estimated_tokens": _estimate_tokens(snapshot.byte_count),
            "language": snapshot.language,
            "tags": list(snapshot.tags),
        }
        if score is not None:
            compact["score"] = round(score, 6)
        if include_content:
            compact["content"] = snapshot.content
        return compact

    def _task_id_from_ref(self, ref_or_task_id: str) -> str:
        if ref_or_task_id.startswith("hkvc://task/") and ref_or_task_id.endswith("/result"):
            return ref_or_task_id[len("hkvc://task/") : -len("/result")]
        return ref_or_task_id

    def _register_builtin_tools(self) -> None:
        tools = (
            ToolSpec(
                name="code_agent.search_files",
                description="Search compact cached repository file summaries before fetching full content.",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}, "top_k": {"type": "integer", "default": 5}},
                    "required": ["query"],
                },
                tags=("coding-agent", "repo", "search"),
            ),
            ToolSpec(
                name="code_agent.fetch_file",
                description="Fetch full file content from a Catalyst file reference only when needed.",
                input_schema={
                    "type": "object",
                    "properties": {"ref_or_path": {"type": "string"}},
                    "required": ["ref_or_path"],
                },
                tags=("coding-agent", "file", "context"),
            ),
            ToolSpec(
                name="code_agent.record_command",
                description="Store verbose command stdout and stderr behind a compact deferred result reference.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "stdout": {"type": "string"},
                        "stderr": {"type": "string"},
                        "status": {"type": "string", "enum": ["queued", "running", "completed", "failed"]},
                    },
                    "required": ["command"],
                },
                tags=("coding-agent", "command", "terminal"),
            ),
            ToolSpec(
                name="code_agent.record_test_run",
                description="Compact test output and retain the full log outside the active agent context.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "stdout": {"type": "string"},
                        "stderr": {"type": "string"},
                        "framework": {"type": "string"},
                    },
                    "required": ["command"],
                },
                tags=("coding-agent", "tests", "logs"),
            ),
            ToolSpec(
                name="code_agent.record_patch",
                description="Store a full patch diff behind a compact ref with changed-file and line stats.",
                input_schema={
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "diff": {"type": "string"}},
                    "required": ["name", "diff"],
                },
                tags=("coding-agent", "patch", "diff"),
            ),
            ToolSpec(
                name="code_agent.compact_handoff",
                description="Export compact Rain-backed state for transferring coding-agent sessions.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "objective": {"type": "string"},
                        "current_plan": {"type": "array", "items": {"type": "string"}},
                        "next_steps": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["objective"],
                },
                tags=("coding-agent", "handoff", "rain"),
            ),
        )
        for spec in tools:
            self.kernel.register_tool(spec)
