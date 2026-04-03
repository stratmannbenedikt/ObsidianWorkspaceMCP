"""Pydantic data models for Obsidian MCP server."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class FileChangeType(str, Enum):
    """Kind of change applied to a file."""

    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"


class SortOrder(str, Enum):
    """Sort order for listing operations."""

    ASCENDING = "ascending"
    DESCENDING = "descending"


class SortBy(str, Enum):
    """Field to sort by in listing operations."""

    NAME = "name"
    MODIFIED = "modified"
    SIZE = "size"


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class VaultStats(BaseModel):
    """Statistics about the vault."""

    total_files: int = Field(description="Total number of markdown files in the vault")
    total_size_bytes: int = Field(description="Total size of all vault files in bytes")
    last_modified: datetime | None = Field(
        default=None, description="ISO-8601 timestamp of the most recently modified file"
    )


class DirectoryEntry(BaseModel):
    """A single file or directory within the vault."""

    name: str = Field(description="Basename of the entry")
    path: str = Field(description="Relative path from the vault root")
    is_dir: bool = Field(description="True if this entry is a directory")
    size_bytes: int | None = Field(default=None, description="File size in bytes (null for dirs)")
    modified: datetime | None = Field(
        default=None, description="ISO-8601 last-modified timestamp"
    )


class ListDirectoryResponse(BaseModel):
    """Result of listing a directory."""

    entries: list[DirectoryEntry] = Field(description="Files and subdirectories")
    path: str = Field(description="The directory that was listed")


class ReadFileResponse(BaseModel):
    """Result of reading a file."""

    path: str = Field(description="Relative path of the file")
    content: str = Field(description="Raw text content of the file")
    size_bytes: int = Field(description="Size of the content in bytes")
    modified: datetime | None = Field(
        default=None, description="ISO-8601 last-modified timestamp"
    )


class CreateFileResponse(BaseModel):
    """Result of creating a file."""

    path: str = Field(description="Relative path of the created file")
    change_type: FileChangeType = Field(default=FileChangeType.CREATED)
    size_bytes: int = Field(description="Size of the written content in bytes")


class EditFileRequest(BaseModel):
    """Specification for an in-place edit."""

    path: str = Field(description="Relative path of the file to edit")
    old_text: str = Field(
        description="Text in the file to replace. Must match exactly."
    )
    new_text: str = Field(description="Replacement text")
    count: int = Field(
        default=1,
        ge=0,
        le=1000,
        description="Number of occurrences to replace (0 = all, 1 = first match only)",
    )


class EditFileResponse(BaseModel):
    """Result of an edit operation."""

    path: str = Field(description="Relative path of the edited file")
    change_type: FileChangeType = Field(default=FileChangeType.MODIFIED)
    replacements_made: int = Field(
        description="How many replacements were actually performed"
    )


class DeleteFileResponse(BaseModel):
    """Result of deleting a file."""

    path: str = Field(description="Relative path of the deleted file")
    change_type: FileChangeType = Field(default=FileChangeType.DELETED)


class SearchRequest(BaseModel):
    """Specification for a content search."""

    query: str = Field(min_length=1, description="Text to search for")
    path: str = Field(
        default="",
        description="Directory (relative) to search within. Empty = entire vault.",
    )
    case_sensitive: bool = Field(
        default=False, description="Perform a case-sensitive search"
    )
    file_extension: str | None = Field(
        default=None, description="Restrict search to this file extension (e.g. '.md')"
    )


class SearchMatch(BaseModel):
    """A single match from a search result."""

    path: str = Field(description="Relative path of the file with a match")
    line_number: int = Field(description="1-based line number of the match")
    line_content: str = Field(description="Full text of the line containing the match")
    match_start: int = Field(
        description="Character offset where the match begins within the line"
    )
    match_end: int = Field(
        description="Character offset where the match ends within the line"
    )


class SearchResponse(BaseModel):
    """Result of a search operation."""

    query: str = Field(description="The search query that was executed")
    total_matches: int = Field(
        description="Total number of individual matches across all files"
    )
    files_searched: int = Field(description="Number of files that were searched")
    matches: list[SearchMatch] = Field(
        default_factory=list, description="Individual matches"
    )


class ErrorDetail(BaseModel):
    """Structured error information."""

    code: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable error description")
    path: str | None = Field(default=None, description="File path related to the error, if any")
