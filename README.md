# Obsidian Workspace MCP Server

**Purpose:** Enable AI agents to interact safely with an Obsidian vault — browsing, reading, searching, creating, editing, and deleting notes — without granting terminal-level filesystem access.

## What is this?

This is a minimal [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server. It wraps a set of structured file operations around a **single, predetermined vault directory** and enforces a hard boundary: operations cannot escape that directory. This makes it safe to expose to agents that need to work with your notes without letting them run arbitrary shell commands.

## Use Case

You have an Obsidian vault. You want an AI agent (or any MCP-compatible AI client) to:

- Search across your notes
- Read specific files
- Create meeting notes, daily notes, or project files
- Edit existing notes with surgical text replacements
- Delete files

…without giving that agent a shell prompt, SSH access, or any other way to run system commands.

The agent sees the vault as a set of tools (`vault_stats`, `list_directory`, `read_file`, `create_file`, `edit_file`, `delete_file`, `search`) — not as a general-purpose terminal.

## Architecture

```
┌─────────────────┐     MCP (stdio)     ┌──────────────────────────────┐
│  AI Agent /     │◄──────────────────►│  obsidian-workspace-mcp      │
│  MCP Client     │                     │                              │
└─────────────────┘                     │  Vault ──────► vault root    │
                                         │    ├─ vault.py (operations)  │
                                         │    └─ models.py (schemas)   │
                                         └──────────────────────────────┘
```

**Security:** All file paths are resolved relative to the configured vault root. Path traversal (`..`) is explicitly blocked. The server performs no shell execution and opens no network sockets beyond stdio.

## Installation

```bash
# Install from source
cd ObsidianWorkspaceMCP
uv sync

# Or install globally
uv pip install .
```

## Configuration

Set the vault path via environment variable:

```bash
export OBSIDIAN_VAULT_PATH=/home/user/vaults/main-vault
```

Or pass it on the command line:

```bash
obsidian-workspace-mcp --vault /home/user/vaults/main-vault
```

## Running

```bash
# Via uv (recommended)
OBSIDIAN_VAULT_PATH=/path/to/vault uv run obsidian-workspace-mcp

# Or after installation
obsidian-workspace-mcp

# With Claude Desktop / other MCP clients:
# configure the server path in your MCP client config, e.g.:
# {
#   "mcpServers": {
#     "obsidian-vault": {
#       "command": "uv",
#       "args": ["run", "obsidian-workspace-mcp"],
#       "env": { "OBSIDIAN_VAULT_PATH": "/path/to/vault" }
#     }
#   }
# }
```

## Available Tools

| Tool | Description |
|------|-------------|
| `vault_stats` | Returns file count, total size, and last-modified timestamp for the vault |
| `list_directory` | Lists files and subdirectories, with optional sorting by name / modified / size |
| `read_file` | Reads the full contents of a single file |
| `create_file` | Creates a new file (or overwrites an existing one) with optional content |
| `edit_file` | Performs an in-place text replacement (`old_text → new_text`), supports single or global replace |
| `delete_file` | Deletes a single file |
| `search` | Full-text search with relevance ranking, context snippets, and pagination |
| `query_properties` | DataView-like frontmatter query — filter by properties (eq, neq, contains, gt/gte/lt/lte, exists/not_exists), sort, select fields, paginate |
| `tag_index` | Build a tag/keyword index from frontmatter list properties with occurrence counts |
| `directory_tree` | Tree-style view of a vault directory |
| `create_template` | Create or update a page template (frontmatter structure) |
| `get_template` | Retrieve a template by name |
| `list_templates` | List all available page templates |
| `create_from_template` | Create a new note from a template with field values |

## Tool Details

### `query_properties` — DataView-style Frontmatter Queries

Filter and retrieve files based on their YAML frontmatter properties, similar to Obsidian's DataView plugin.

**Parameters:**
- `filters` — List of filter conditions (`{field, op, value}`). Operators: `eq`, `neq`, `contains`, `gt`, `gte`, `lt`, `lte`, `exists`, `not_exists`. Multiple filters are ANDed.
- `sort` — Sort by any frontmatter field, or `path` / `modified`. Direction: `ascending` or `descending`.
- `select` — Properties to include in results (projection). Reduces token usage by only returning fields you need.
- `limit` / `offset` — Pagination.
- `path` — Restrict search to a subdirectory.

**Example:** Find all active projects with priority ≥ 3:
```json
{
  "filters": [
    {"field": "status", "op": "eq", "value": "active"},
    {"field": "priority", "op": "gte", "value": 3}
  ],
  "sort": {"field": "priority", "order": "descending"},
  "select": ["title", "priority", "tags"]
}
```

### `search` — Full-text Search with Context

**New features** beyond basic search:
- **Relevance ranking** — Files with more hits are ranked first.
- **Context snippets** — Set `context_lines` (0–10) to get surrounding lines per match.
- **Pagination** — Use `limit` and `offset` for large result sets.

### `tag_index` — Tag/Keyword Index

Build an index of tag or keyword values from any frontmatter list property.

**Parameters:**
- `properties` — Frontmatter fields to index (default: `["tags"]`).
- `min_count` — Minimum occurrence count to include.
- `path` — Restrict to a subdirectory.

**Example:** Index both tags and keywords, only show tags used 3+ times:
```json
{
  "properties": ["tags", "keywords"],
  "min_count": 3
}
```

## Project Structure

```
ObsidianWorkspaceMCP/
├── pyproject.toml              # Package + tool configuration
├── README.md                   # This file
├── LICENSE
├── .gitignore
├── .agent/                     # Agent working notes (gitignored)
│   ├── TODO.md
│   ├── DECISIONS.md
│   └── KNOWN_ISSUES.md
└── src/obsidian_workspace_mcp/
    ├── __init__.py             # Public API / exports
       ├── __main__.py             # CLI entry point
    ├── models.py               # Pydantic request/response schemas
    ├── vault.py                # Core vault operations
    ├── server.py               # MCP server + protocol handlers
    └── frontmatter.py          # YAML frontmatter parser
```

## Design Decisions

- **pydantic models for all wire types** — All request and response shapes are defined as Pydantic models, making the API self-documenting and machine-readable.
- **No external Obsidian dependencies** — The server operates on plain Markdown files and directories. It does not use the Obsidian API or require Obsidian to be running.
- **Path traversal protection** — The vault root is resolved once at startup. All relative paths are validated against it; `..` components are rejected.
- **UTF-8 only** — Files are read and written as UTF-8. Binary files are not supported (this is a note-taking tool).
- **Single vault per server instance** — One server process serves one vault. Run multiple instances for multiple vaults.

## OpenClaw Skill

To use this MCP server with [OpenClaw](https://openclaw.ai), create a skill that registers the server as an MCP tool provider. Here's an example `SKILL.md`:

```markdown
---
name: obsidian-vault
description: Interact with an Obsidian vault via the ObsidianWorkspaceMCP server.
metadata:
  openclaw:
    emoji: "💎"
    requires:
      mcpServers:
        obsidian-vault:
          command: uv
          args: ["run", "obsidian-workspace-mcp"]
          env:
            OBSIDIAN_VAULT_PATH: /path/to/your/vault
---

# Obsidian Vault

Use the `obsidian-vault` MCP tools to browse, search, and modify notes in the configured Obsidian vault.

## Key Tools

- **`query_properties`** — Find notes by frontmatter (status, tags, priority, etc.). Use `select` to reduce token usage.
- **`search`** — Full-text search with context snippets and pagination.
- **`tag_index`** — Discover what tags/keywords exist in the vault.
- **`read_file` / `create_file` / `edit_file`** — Read, create, and edit notes.
- **`directory_tree` / `list_directory`** — Navigate the vault structure.

## Tips

- Always use `query_properties` with `select` when you only need specific fields — it saves tokens.
- Use `search` with `context_lines` to get surrounding context for matches.
- Use `tag_index` to discover the taxonomy before querying.
```

Place this file in your OpenClaw skills directory or reference it in your agent configuration.
