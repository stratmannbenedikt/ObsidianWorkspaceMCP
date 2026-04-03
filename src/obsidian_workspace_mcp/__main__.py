"""CLI entry point: uv run obsidian-workspace-mcp"""

import os
import sys

from obsidian_workspace_mcp.server import init_vault, mcp


def main() -> None:
    vault_path = os.environ.get("OBSIDIAN_VAULT_PATH")

    args = sys.argv[1:]
    if args and args[0] == "--vault":
        vault_path = args[1] if len(args) > 1 else None
        args = args[2:]

    if args:
        sys.stderr.write(f"obsidian-workspace-mcp: unknown arguments: {args!r}\n")
        sys.stderr.write("Usage: obsidian-workspace-mcp [--vault PATH]\n")
        sys.exit(1)

    if vault_path is not None:
        init_vault(vault_path)

    mcp.run()


if __name__ == "__main__":
    main()
