"""Local workspace read operations with sandbox path enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from caw.errors import WorkspaceError
from caw.models import TraceEvent

if TYPE_CHECKING:
    from caw.core.config import WorkspaceConfig
    from caw.traces.collector import TraceCollector


@dataclass(slots=True)
class FileInfo:
    path: str
    is_dir: bool
    size_bytes: int


@dataclass(slots=True)
class FileContent:
    path: str
    content: str


class PathPolicy:
    def __init__(self, config: WorkspaceConfig) -> None:
        self._config = config

    def validate(self, path: str | Path) -> Path:
        resolved = Path(path).expanduser().resolve()
        mode = self._config.sandbox_mode
        if mode in {"none", "permissive"}:
            return resolved
        allowed = [Path(item).expanduser().resolve() for item in self._config.allowed_paths]
        if any(resolved.is_relative_to(base) for base in allowed):
            return resolved
        raise WorkspaceError(
            message="Path outside allowed workspace",
            code="path_violation",
            details={"path": str(resolved), "allowed_paths": [str(item) for item in allowed]},
        )


class LocalWorkspace:
    def __init__(self, config: WorkspaceConfig, collector: TraceCollector) -> None:
        self._collector = collector
        self._policy = PathPolicy(config)

    async def list_files(
        self,
        path: str,
        recursive: bool = False,
        session_id: str = "workspace",
        trace_id: str = "workspace-list",
    ) -> list[FileInfo]:
        root = self._policy.validate(path)
        if not root.exists() or not root.is_dir():
            raise WorkspaceError("Path is not a readable directory", "invalid_directory")

        entries: list[FileInfo] = []
        iterator = root.rglob("*") if recursive else root.iterdir()
        for entry in iterator:
            stat = entry.stat()
            entries.append(
                FileInfo(
                    path=str(entry),
                    is_dir=entry.is_dir(),
                    size_bytes=0 if entry.is_dir() else stat.st_size,
                )
            )
        await self._collector.emit(
            TraceEvent(
                trace_id=trace_id,
                session_id=session_id,
                event_type="workspace:read",
                data={"action": "list_files", "path": str(root), "count": len(entries)},
            )
        )
        return entries

    async def read_file(
        self,
        path: str,
        session_id: str = "workspace",
        trace_id: str = "workspace-read",
    ) -> FileContent:
        target = self._policy.validate(path)
        if not target.exists() or not target.is_file():
            raise WorkspaceError("File not found", "file_not_found", details={"path": str(target)})

        content = target.read_text(encoding="utf-8")
        await self._collector.emit(
            TraceEvent(
                trace_id=trace_id,
                session_id=session_id,
                event_type="workspace:read",
                data={"action": "read_file", "path": str(target), "size": len(content)},
            )
        )
        return FileContent(path=str(target), content=content)

    async def search_files(
        self,
        pattern: str,
        path: str,
        session_id: str = "workspace",
        trace_id: str = "workspace-search",
    ) -> list[FileInfo]:
        root = self._policy.validate(path)
        if not root.exists() or not root.is_dir():
            raise WorkspaceError("Path is not a readable directory", "invalid_directory")

        matches: list[FileInfo] = []
        for entry in root.rglob(pattern):
            stat = entry.stat()
            matches.append(
                FileInfo(
                    path=str(entry),
                    is_dir=entry.is_dir(),
                    size_bytes=0 if entry.is_dir() else stat.st_size,
                )
            )
        await self._collector.emit(
            TraceEvent(
                trace_id=trace_id,
                session_id=session_id,
                event_type="workspace:read",
                data={
                    "action": "search_files",
                    "path": str(root),
                    "pattern": pattern,
                    "count": len(matches),
                },
            )
        )
        return matches
