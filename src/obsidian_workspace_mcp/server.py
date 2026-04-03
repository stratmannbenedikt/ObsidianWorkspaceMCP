"""MCP server for Obsidian vault interaction — FastMCP implementation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP

from .models import (
    CreateTemplateRequest,
    EditFileRequest,
    SearchRequest,
    SortBy,
    SortOrder,
    TemplateField,
)
from .vault import Vault, VaultFileError, VaultSecurityError

logger = logging.getLogger(__name__)

APP_NAME = "obsidian-workspace-mcp"
VERSION = "0.1.0"

mcp = FastMCP(APP_NAME)

# ---------------------------------------------------------------------------
# Vault lifecycle
# ---------------------------------------------------------------------------

_vault: Vault | None = None


def init_vault(vault_path: str | Path | None = None) -> Vault:
    """Load (or re-load) the vault from the configured path."""
    global _vault
    path = _resolve_vault_path(vault_path)
    _vault = Vault(path)
    logger.info("Vault initialised at %s", path)
    return _vault


def get_vault() -> Vault:
    if _vault is None:
        raise RuntimeError("Vault not initialised — call init_vault() first")
    return _vault


def _resolve_vault_path(vault_path: str | Path | None = None) -> Path:
    """Determine the vault root path."""
    if vault_path is not None:
        return Path(vault_path).expanduser().resolve()

    env_path = Path("/root/.config/obsidian-workspace-mcp/vault_path")
    if env_path.exists():
        return Path(env_path.read_text().strip()).resolve()

    raise ValueError(
        "No vault path configured. Set the OBSIDIAN_VAULT_PATH environment "
        "variable, or pass vault_path at initialisation."
    )


# ---------------------------------------------------------------------------
# Tools — one decorated function per operation, schema inferred from types
# ---------------------------------------------------------------------------


@mcp.tool()
def vault_stats() -> dict:
    """Return aggregate statistics (file count, total size, last modified) for the vault."""
    return get_vault().stats().model_dump(mode="json")


@mcp.tool()
def list_directory(
    path: Annotated[str, "Relative path within the vault (empty = root)."] = "",
    sort_by: Annotated[SortBy, "Field to sort by."] = SortBy.NAME,
    sort_order: Annotated[SortOrder, "Sort direction."] = SortOrder.ASCENDING,
) -> dict:
    """List the contents of a vault directory, optionally sorted."""
    result = get_vault().list_directory(path=path, sort_by=sort_by, sort_order=sort_order)
    return result.model_dump(mode="json")


@mcp.tool()
def read_file(
    path: Annotated[str, "Relative path of the file to read."],
) -> dict:
    """Read the full contents of a single vault file."""
    return get_vault().read_file(path).model_dump(mode="json")


@mcp.tool()
def create_file(
    path: Annotated[str, "Relative path of the file to create."],
    content: Annotated[str, "Initial file content (UTF-8 text)."] = "",
) -> dict:
    """Create a new file in the vault (or overwrite if it already exists)."""
    return get_vault().create_file(path, content).model_dump(mode="json")


@mcp.tool()
def edit_file(
    path: Annotated[str, "Relative path of the file to edit."],
    old_text: Annotated[str, "Exact text in the file to replace."],
    new_text: Annotated[str, "Replacement text."],
    count: Annotated[int, "Number of occurrences to replace (0 = all)."] = 1,
) -> dict:
    """Perform an in-place text replacement in a vault file."""
    req = EditFileRequest(path=path, old_text=old_text, new_text=new_text, count=count)
    return get_vault().edit_file(req).model_dump(mode="json")


@mcp.tool()
def delete_file(
    path: Annotated[str, "Relative path of the file to delete."],
) -> dict:
    """Delete a single file from the vault."""
    return get_vault().delete_file(path).model_dump(mode="json")


@mcp.tool()
def search(
    query: Annotated[str, "Text to search for."],
    path: Annotated[str, "Directory to search within (empty = entire vault)."] = "",
    case_sensitive: Annotated[bool, "Perform a case-sensitive search."] = False,
    file_extension: Annotated[str | None, "Restrict to this extension, e.g. '.md'."] = None,
) -> dict:
    """Search for text inside vault files."""
    req = SearchRequest(
        query=query, path=path,
        case_sensitive=case_sensitive, file_extension=file_extension,
    )
    return get_vault().search(req).model_dump(mode="json")


@mcp.tool()
def directory_tree(
    path: Annotated[str, "Relative path within the vault (empty = root)."] = "",
    max_depth: Annotated[int, "Maximum recursion depth (1 = only immediate children)."] = 3,
    max_files_per_dir: Annotated[int, "Maximum entries per directory."] = 20,
) -> dict:
    """Return a tree-style view of a vault directory (like the `tree` CLI)."""
    return get_vault().directory_tree(
        path=path, max_depth=max_depth, max_files_per_dir=max_files_per_dir,
    ).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Template tools
# ---------------------------------------------------------------------------


@mcp.tool()
def create_template(
    name: Annotated[str, "Template name (unique identifier)."],
    description: Annotated[str, "What this template is for."],
    fields: Annotated[list[dict], "Array of field definitions: name, type, required, default, description."],
) -> dict:
    """Create or update a page template. Templates define frontmatter property structures for consistently-structured notes."""
    tpl_fields = [TemplateField(**f) for f in fields]
    req = CreateTemplateRequest(name=name, description=description, fields=tpl_fields)
    return get_vault().create_template(req).model_dump(mode="json")


@mcp.tool()
def get_template(
    name: Annotated[str, "Template name to retrieve."],
) -> dict:
    """Retrieve a template by name, showing its fields and structure."""
    return get_vault().get_template(name).model_dump(mode="json")


@mcp.tool()
def list_templates() -> dict:
    """List all available page templates with their names and descriptions."""
    return get_vault().list_templates().model_dump(mode="json")


@mcp.tool()
def create_from_template(
    template_name: Annotated[str, "Name of the template to use."],
    path: Annotated[str, "Relative path for the new file (e.g. 'papers/My Paper.md')."],
    values: Annotated[dict, "Key-value pairs for template fields."] = {},
    body: Annotated[str, "Markdown body content below the frontmatter."] = "",
) -> dict:
    """Create a new markdown file using a template's frontmatter structure."""
    from .models import CreateFromTemplateRequest
    req = CreateFromTemplateRequest(
        template_name=template_name, path=path, values=values, body=body,
    )
    return get_vault().create_from_template(req).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def main(vault_path: str | Path | None = None) -> None:
    """Run the MCP server."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    init_vault(vault_path)
    await mcp.run_async()
