"""CLI entry point: uv run obsidian-workspace-mcp"""

import asyncio
import os
import sys
from pathlib import Path

from obsidian_workspace_mcp.server import main as srv_main


def main() -> None:
    vault_path = os.environ.get("OBSIDIAN_VAULT_PATH")

    args = sys.argv[1:]
    if args and args[0] == "--vault":
        vault_path = args[1] if len(args) > 1 else None
        args = args[2:]

    # Remaining args could be future CLI options; warn on unknown ones
    if args:
        sys.stderr.write(f"obsidian-workspace-mcp: unknown arguments: {args!r}\n")
        sys.stderr.write("Usage: obsidian-workspace-mcp [--vault PATH]\n")
        sys.exit(1)

    asyncio.run(srv_main(vault_path=vault_path))


if __name__ == "__main__":
    main()
