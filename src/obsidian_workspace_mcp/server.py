"""Minimal MCP server for Obsidian vault interaction."""

from __future__ import annotations

import logging
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    ErrorData,
    ListResourcesResult,
    ListToolsResult,
    ReadResourceResult,
    Resource,
    TextResourceContents,
    Tool,
)

from .models import (
    CreateFileResponse,
    CreateFromTemplateRequest,
    DeleteFileResponse,
    EditFileRequest,
    ErrorDetail,
    ListDirectoryResponse,
    ReadFileResponse,
    SearchRequest,
    SearchResponse,
    SortBy,
    SortOrder,
    VaultStats,
)
from .vault import Vault, VaultFileError, VaultSecurityError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

APP_NAME = "obsidian-workspace-mcp"
VERSION = "0.1.0"

server = Server(APP_NAME)


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

    # Check environment variable first
    env_path = Path("/root/.config/obsidian-workspace-mcp/vault_path")
    if env_path.exists():
        return Path(env_path.read_text().strip()).resolve()

    raise ValueError(
        "No vault path configured. Set the OBSIDIAN_VAULT_PATH environment "
        "variable, or pass vault_path at initialisation."
    )


# ---------------------------------------------------------------------------
# MCP Handlers
# ---------------------------------------------------------------------------


@server.list_resources()
async def list_resources() -> ListResourcesResult:
    """Advertise the vault root as a resource."""
    v = get_vault()
    return ListResourcesResult(
        resources=[
            Resource(
                uri=f"vault://{v._root.name}/",
                name=f"Obsidian Vault: {v._root.name}",
                description="Root of the Obsidian vault",
                mimeType="text/markdown",
            )
        ]
    )


@server.read_resource()
async def read_resource(uri: str) -> ReadResourceResult:
    """Handle vault:// URI reads (delegates to vault file reads)."""
    v = get_vault()
    prefix = f"vault://{v._root.name}/"
    if not uri.startswith(prefix):
        raise ValueError(f"Unknown URI scheme: {uri}")
    rel_path = uri[len(prefix):].lstrip("/")
    result = v.read_file(rel_path)
    return ReadResourceResult(
        contents=[
            TextResourceContents(
                uri=uri,
                mimeType="text/markdown",
                text=result.content,
            )
        ]
    )


@server.list_tools()
async def list_tools() -> ListToolsResult:
    """Advertise all available vault tools."""
    return ListToolsResult(
        tools=[
            Tool(
                name="vault_stats",
                description="Return aggregate statistics (file count, total size, last modified) for the vault.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="list_directory",
                description="List the contents of a vault directory, optionally sorted.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "default": "",
                            "description": "Relative path within the vault (empty = root).",
                        },
                        "sort_by": {
                            "type": "string",
                            "enum": ["name", "modified", "size"],
                            "default": "name",
                        },
                        "sort_order": {
                            "type": "string",
                            "enum": ["ascending", "descending"],
                            "default": "ascending",
                        },
                    },
                },
            ),
            Tool(
                name="read_file",
                description="Read the full contents of a single vault file.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path of the file to read.",
                        }
                    },
                    "required": ["path"],
                },
            ),
            Tool(
                name="create_file",
                description="Create a new file in the vault (or overwrite if it already exists).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path of the file to create.",
                        },
                        "content": {
                            "type": "string",
                            "default": "",
                            "description": "Initial file content (UTF-8 text).",
                        },
                    },
                    "required": ["path"],
                },
            ),
            Tool(
                name="edit_file",
                description="Perform an in-place text replacement in a vault file.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path of the file to edit.",
                        },
                        "old_text": {
                            "type": "string",
                            "description": "Exact text in the file to replace.",
                        },
                        "new_text": {
                            "type": "string",
                            "description": "Replacement text.",
                        },
                        "count": {
                            "type": "integer",
                            "default": 1,
                            "description": "Number of occurrences to replace (0 = all).",
                        },
                    },
                    "required": ["path", "old_text", "new_text"],
                },
            ),
            Tool(
                name="delete_file",
                description="Delete a single file from the vault.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path of the file to delete.",
                        }
                    },
                    "required": ["path"],
                },
            ),
            Tool(
                name="search",
                description="Search for text inside vault files.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Text to search for.",
                        },
                        "path": {
                            "type": "string",
                            "default": "",
                            "description": "Directory to search within (empty = entire vault).",
                        },
                        "case_sensitive": {
                            "type": "boolean",
                            "default": False,
                        },
                        "file_extension": {
                            "type": "string",
                            "default": None,
                            "description": "Restrict to this extension, e.g. '.md'.",
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="directory_tree",
                description="Return a tree-style view of a vault directory (like the `tree` CLI). Directories are listed first, then files, with truncation support.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "default": "",
                            "description": "Relative path within the vault (empty = root).",
                        },
                        "max_depth": {
                            "type": "integer",
                            "default": 3,
                            "description": "Maximum recursion depth (1 = only immediate children).",
                        },
                        "max_files_per_dir": {
                            "type": "integer",
                            "default": 20,
                            "description": "Maximum number of entries to show per directory (excess shown as '... N more').",
                        },
                    },
                },
            ),
            Tool(
                name="create_template",
                description="Create or update a page template. Templates define frontmatter property structures (fields with types, defaults, descriptions) that can be used to create consistently-structured notes.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Template name (unique identifier).",
                        },
                        "description": {
                            "type": "string",
                            "description": "What this template is for.",
                        },
                        "fields": {
                            "type": "array",
                            "description": "Array of field definitions, each with: name (str), type (string|number|boolean|date|list|multi-list), required (bool), default (any), description (str).",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "type": {"type": "string", "default": "string"},
                                    "required": {"type": "boolean", "default": True},
                                    "default": {},
                                    "description": {"type": "string", "default": ""},
                                },
                                "required": ["name"],
                            },
                        },
                    },
                    "required": ["name", "description", "fields"],
                },
            ),
            Tool(
                name="get_template",
                description="Retrieve a template by name, showing its fields and structure.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Template name to retrieve.",
                        },
                    },
                    "required": ["name"],
                },
            ),
            Tool(
                name="list_templates",
                description="List all available page templates with their names and descriptions.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="create_from_template",
                description="Create a new markdown file using a template's frontmatter structure. Fill in field values; omitted required fields get empty placeholders.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "template_name": {
                            "type": "string",
                            "description": "Name of the template to use.",
                        },
                        "path": {
                            "type": "string",
                            "description": "Relative path for the new file (e.g. 'papers/My Paper.md').",
                        },
                        "values": {
                            "type": "object",
                            "description": "Key-value pairs for template fields. Omitted fields use their defaults.",
                        },
                        "body": {
                            "type": "string",
                            "default": "",
                            "description": "Markdown body content below the frontmatter.",
                        },
                    },
                    "required": ["template_name", "path"],
                },
            ),
        ]
    )


@server.call_tool()
async def call_tool(
    name: str, arguments: dict | None
) -> list[dict]:
    """Dispatch a tool call to the appropriate vault method."""
    v = get_vault()
    try:
        if name == "vault_stats":
            result: VaultStats = v.stats()
            return [_model_to_dict(result)]

        elif name == "list_directory":
            result = v.list_directory(
                path=(arguments or {}).get("path", ""),
                sort_by=SortBy((arguments or {}).get("sort_by", "name")),
                sort_order=SortOrder((arguments or {}).get("sort_order", "ascending")),
            )
            return [_model_to_dict(result)]

        elif name == "read_file":
            path = _required(arguments, "path")
            result = v.read_file(path)
            return [_model_to_dict(result)]

        elif name == "create_file":
            path = _required(arguments, "path")
            content = (arguments or {}).get("content", "")
            result = v.create_file(path, content)
            return [_model_to_dict(result)]

        elif name == "edit_file":
            req = EditFileRequest(
                path=_required(arguments, "path"),
                old_text=_required(arguments, "old_text"),
                new_text=_required(arguments, "new_text"),
                count=(arguments or {}).get("count", 1),
            )
            result = v.edit_file(req)
            return [_model_to_dict(result)]

        elif name == "delete_file":
            path = _required(arguments, "path")
            result = v.delete_file(path)
            return [_model_to_dict(result)]

        elif name == "search":
            req = SearchRequest(
                query=_required(arguments, "query"),
                path=(arguments or {}).get("path", ""),
                case_sensitive=(arguments or {}).get("case_sensitive", False),
                file_extension=(arguments or {}).get("file_extension"),
            )
            result = v.search(req)
            return [_model_to_dict(result)]

        elif name == "directory_tree":
            result = v.directory_tree(
                path=(arguments or {}).get("path", ""),
                max_depth=(arguments or {}).get("max_depth", 3),
                max_files_per_dir=(arguments or {}).get("max_files_per_dir", 20),
            )
            return [_model_to_dict(result)]

        elif name == "create_template":
            from .models import CreateTemplateRequest as CTR, TemplateField
            fields = [
                TemplateField(**f) for f in (arguments or {}).get("fields", [])
            ]
            req = CTR(
                name=_required(arguments, "name"),
                description=_required(arguments, "description"),
                fields=fields,
            )
            result = v.create_template(req)
            return [_model_to_dict(result)]

        elif name == "get_template":
            result = v.get_template(_required(arguments, "name"))
            return [_model_to_dict(result)]

        elif name == "list_templates":
            result = v.list_templates()
            return [_model_to_dict(result)]

        elif name == "create_from_template":
            req = CreateFromTemplateRequest(
                template_name=_required(arguments, "template_name"),
                path=_required(arguments, "path"),
                values=(arguments or {}).get("values", {}),
                body=(arguments or {}).get("body", ""),
            )
            result = v.create_from_template(req)
            return [_model_to_dict(result)]

        else:
            raise ValueError(f"Unknown tool: {name!r}")

    except VaultSecurityError as exc:
        raise ErrorData(code="SECURITY_ERROR", message=str(exc)) from exc
    except VaultFileError as exc:
        raise ErrorData(code="FILE_ERROR", message=str(exc)) from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _required(args: dict, key: str) -> str:
    val = args.get(key)
    if val is None:
        raise ErrorData(
            code=INVALID_PARAMS,
            message=f"Missing required parameter: {key!r}",
        )
    return val  # type: ignore[return-value]


def _model_to_dict(model) -> dict:
    """Serialise a Pydantic model to a JSON-compatible dict."""
    return {
        "type": "text",
        "text": model.model_dump_json(serialize_as_unknown=True),
    }


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def main(vault_path: str | Path | None = None) -> None:
    """Run the MCP server."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    init_vault(vault_path)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
