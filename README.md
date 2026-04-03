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
| `search` | Full-text search across vault files, supports case-sensitivity and extension filtering |

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
    └── server.py               # MCP server + protocol handlers
```

## Design Decisions

- **pydantic models for all wire types** — All request and response shapes are defined as Pydantic models, making the API self-documenting and machine-readable.
- **No external Obsidian dependencies** — The server operates on plain Markdown files and directories. It does not use the Obsidian API or require Obsidian to be running.
- **Path traversal protection** — The vault root is resolved once at startup. All relative paths are validated against it; `..` components are rejected.
- **UTF-8 only** — Files are read and written as UTF-8. Binary files are not supported (this is a note-taking tool).
- **Single vault per server instance** — One server process serves one vault. Run multiple instances for multiple vaults.
