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
    context_lines: int = Field(
        default=0, ge=0, le=10,
        description="Number of surrounding lines to include per match for context",
    )
    limit: int = Field(
        default=50, ge=1, le=500,
        description="Maximum number of matches to return",
    )
    offset: int = Field(
        default=0, ge=0,
        description="Offset for pagination (skip this many matches)",
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
    context_before: list[str] = Field(
        default_factory=list,
        description="Lines before the match (up to context_lines)",
    )
    context_after: list[str] = Field(
        default_factory=list,
        description="Lines after the match (up to context_lines)",
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


# ---------------------------------------------------------------------------
# Directory Tree
# ---------------------------------------------------------------------------


class DirectoryTreeNode(BaseModel):
    """A single node in the directory tree."""

    name: str = Field(description="Name of the file or directory")
    path: str = Field(description="Relative path from the vault root")
    is_dir: bool = Field(description="True if this is a directory")
    children: list[DirectoryTreeNode] = Field(
        default_factory=list, description="Child entries (directories first, then files)"
    )
    truncated: bool = Field(
        default=False, description="True if entries were truncated due to max_files_per_dir"
    )


class DirectoryTreeResponse(BaseModel):
    """Result of a directory tree operation."""

    tree: DirectoryTreeNode = Field(description="Root node of the tree")
    text: str = Field(description="Human-readable tree string (like the `tree` CLI)")


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


class TemplateField(BaseModel):
    """A single field in a page template (frontmatter property)."""

    name: str = Field(description="Property name")
    type: str = Field(
        default="string",
        description="Value type: string, number, boolean, date, list, or multi-list",
    )
    required: bool = Field(default=True, description="Whether this field is required")
    default: Any = Field(default=None, description="Default value if not provided")
    description: str = Field(default="", description="Human-readable description of the field")


class Template(BaseModel):
    """A page template defining frontmatter structure."""

    name: str = Field(description="Template name (unique identifier)")
    description: str = Field(description="What this template is for")
    fields: list[TemplateField] = Field(description="Frontmatter fields in order")


class CreateTemplateRequest(BaseModel):
    """Request to create or update a template."""

    name: str = Field(min_length=1, description="Template name (unique identifier)")
    description: str = Field(min_length=1, description="What this template is for")
    fields: list[TemplateField] = Field(
        min_length=1, description="Frontmatter fields in order"
    )


class CreateTemplateResponse(BaseModel):
    """Result of creating/updating a template."""

    name: str
    message: str = "Template saved"


class GetTemplateResponse(BaseModel):
    """Result of retrieving a template."""

    template: Template


class ListTemplatesResponse(BaseModel):
    """Result of listing all templates."""

    templates: list[Template] = Field(description="All available templates")


class CreateFromTemplateRequest(BaseModel):
    """Request to create a new file from a template."""

    template_name: str = Field(min_length=1, description="Name of the template to use")
    path: str = Field(min_length=1, description="Relative path for the new file")
    values: dict[str, Any] = Field(
        default_factory=dict, description="Values for template fields (keyed by field name)"
    )
    body: str = Field(default="", description="Markdown body content below the frontmatter")


class CreateFromTemplateResponse(BaseModel):
    """Result of creating a file from a template."""

    path: str
    template_name: str
    content: str = Field(description="Full content that was written")


# ---------------------------------------------------------------------------
# Property Query (DataView-like)
# ---------------------------------------------------------------------------


class PropertyFilter(BaseModel):
    """A single property filter condition."""

    field: str = Field(description="Frontmatter property name to filter on")
    op: str = Field(
        default="eq",
        description=(
            "Comparison operator: eq (equal), neq (not equal), contains, "
            "gt, gte, lt, lte (for numbers/dates), exists, not_exists"
        ),
    )
    value: Any = Field(
        default=None,
        description="Value to compare against (not needed for exists/not_exists)",
    )


class PropertySort(BaseModel):
    """Sort specification for property queries."""

    field: str = Field(
        description="Frontmatter property name to sort by (use 'path' or 'modified' for file metadata)"
    )
    order: SortOrder = Field(default=SortOrder.ASCENDING, description="Sort direction")


class PropertyMatch(BaseModel):
    """A single file that matched a property query."""

    path: str = Field(description="Relative path of the file")
    properties: dict[str, Any] = Field(description="Matched frontmatter properties")


class QueryPropertiesRequest(BaseModel):
    """Request for a DataView-like property query."""

    filters: list[PropertyFilter] = Field(
        default_factory=list,
        description="Conditions to filter files by. Multiple filters are ANDed together.",
    )
    sort: PropertySort | None = Field(
        default=None,
        description="Sort results by a property field (default: unsorted)",
    )
    path: str = Field(
        default="",
        description="Directory to search within (empty = entire vault)",
    )
    limit: int = Field(
        default=50, ge=1, le=500,
        description="Maximum number of results to return",
    )
    offset: int = Field(
        default=0, ge=0,
        description="Offset for pagination (skip this many results)",
    )
    select: list[str] | None = Field(
        default=None,
        description=(
            "Properties to include in results. None = all properties. "
            "Token-saving: only return the fields you need."
        ),
    )


class QueryPropertiesResponse(BaseModel):
    """Result of a property query."""

    total_files_scanned: int = Field(description="Total markdown files scanned")
    total_matches: int = Field(description="Files matching all filters")
    matches: list[PropertyMatch] = Field(description="Matching files with their properties")


# ---------------------------------------------------------------------------
# Tag Index
# ---------------------------------------------------------------------------


class TagEntry(BaseModel):
    """A single tag/keyword with its occurrence count."""

    value: str = Field(description="Tag or keyword value")
    count: int = Field(description="Number of files containing this tag")


class TagIndexRequest(BaseModel):
    """Request for a tag/keyword index."""

    path: str = Field(
        default="",
        description="Directory to index (empty = entire vault)",
    )
    properties: list[str] = Field(
        default=["tags"],
        description="Frontmatter fields to index as tags",
    )
    min_count: int = Field(
        default=1, ge=1,
        description="Minimum occurrence count to include in results",
    )


class TagIndexResponse(BaseModel):
    """Result of a tag index operation."""

    properties_indexed: list[str] = Field(description="Properties that were indexed")
    total_tags: int = Field(description="Total unique tag values found")
    total_files_scanned: int = Field(description="Total markdown files scanned")
    tags: list[TagEntry] = Field(description="Tags sorted by count (descending)")


class ErrorDetail(BaseModel):
    """Structured error information."""

    code: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable error description")
    path: str | None = Field(default=None, description="File path related to the error, if any")
