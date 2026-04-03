"""Obsidian Workspace MCP Server.

A minimal MCP server that exposes safe, agent-friendly operations on a
predetermined Obsidian vault directory. Agents can browse, read, search,
create, edit, and delete files without any terminal-level access.

Usage:
    OBSIDIAN_VAULT_PATH=/path/to/vault uv run obsidian-workspace-mcp
    obsidian-workspace-mcp --vault /path/to/vault
"""

from .models import (
    CreateFileResponse,
    DeleteFileResponse,
    DirectoryEntry,
    EditFileRequest,
    EditFileResponse,
    ErrorDetail,
    FileChangeType,
    ListDirectoryResponse,
    ReadFileResponse,
    SearchMatch,
    SearchRequest,
    SearchResponse,
    SortBy,
    SortOrder,
    VaultStats,
)
from .server import init_vault, main, server
from .vault import Vault, VaultFileError, VaultSecurityError

__all__ = [
    # Server
    "server",
    "main",
    "init_vault",
    # Vault
    "Vault",
    "VaultFileError",
    "VaultSecurityError",
    # Models
    "VaultStats",
    "DirectoryEntry",
    "ListDirectoryResponse",
    "ReadFileResponse",
    "CreateFileResponse",
    "EditFileRequest",
    "EditFileResponse",
    "DeleteFileResponse",
    "SearchRequest",
    "SearchMatch",
    "SearchResponse",
    "FileChangeType",
    "SortOrder",
    "SortBy",
    "ErrorDetail",
]

__version__ = "0.1.0"
