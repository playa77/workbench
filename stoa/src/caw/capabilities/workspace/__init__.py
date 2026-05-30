"""Workspace capability pillar."""

from caw.capabilities.workspace.executor import CommandExecutor, ExecutionResult
from caw.capabilities.workspace.local import FileContent, FileInfo, LocalWorkspace
from caw.capabilities.workspace.patch import PatchHunk, PatchProposal, PatchResult, WorkspacePatcher
from caw.capabilities.workspace.writes import MutationResult, WorkspaceWriter

__all__ = [
    "CommandExecutor",
    "ExecutionResult",
    "FileContent",
    "FileInfo",
    "LocalWorkspace",
    "MutationResult",
    "PatchHunk",
    "PatchProposal",
    "PatchResult",
    "WorkspacePatcher",
    "WorkspaceWriter",
]
