"""CLI entry point: uv run obsidian-workspace-mcp"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from obsidian_workspace_mcp.server import init_vault, main, reconfigure_http


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian-workspace-mcp",
        description=(
            "Obsidian Workspace MCP server. Defaults to stdio transport; "
            "use --transport http to expose a streamable-HTTP endpoint."
        ),
    )
    parser.add_argument(
        "--vault",
        metavar="PATH",
        help="Path to the Obsidian vault root. "
        "Defaults to $OBSIDIAN_VAULT_PATH if set.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport to use (default: stdio).",
    )
    parser.add_argument(
        "--host",
        help="HTTP bind address (streamable-http only). "
        "Defaults to $MCP_HOST or 127.0.0.1.",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="HTTP TCP port (streamable-http only). "
        "Defaults to $MCP_PORT or 8000.",
    )
    parser.add_argument(
        "--path",
        help="Streamable-HTTP endpoint path. "
        "Defaults to $MCP_PATH or /mcp.",
    )
    return parser


def main_entrypoint() -> None:
    args = _build_parser().parse_args()

    vault_path = args.vault or os.environ.get("OBSIDIAN_VAULT_PATH")
    if vault_path is not None:
        init_vault(vault_path)
    elif args.transport == "stdio":
        # The server can lazily resolve the vault path on first tool call
        # when run over stdio, but for HTTP we want to fail fast at startup.
        pass

    if args.transport == "streamable-http":
        reconfigure_http(host=args.host, port=args.port, path=args.path)
        if vault_path is None:
            sys.stderr.write(
                "obsidian-workspace-mcp: warning — no vault path configured; "
                "tools will fail until OBSIDIAN_VAULT_PATH is set.\n"
            )

    asyncio.run(main(vault_path=vault_path, transport=args.transport))


if __name__ == "__main__":
    main_entrypoint()
