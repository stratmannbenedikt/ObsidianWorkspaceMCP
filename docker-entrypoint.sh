#!/bin/sh
# Entrypoint wrapper: exports APP_VERSION from the file baked into the
# image at build time, then execs the MCP server with the requested
# streamable-HTTP configuration. Using `exec` ensures the server becomes
# PID 1 inside the container (correct signal handling).
set -eu

if [ -f /etc/obsidian-mcp/APP_VERSION ]; then
    export APP_VERSION=$(cat /etc/obsidian-mcp/APP_VERSION)
fi

exec obsidian-workspace-mcp \
    --transport streamable-http \
    --host 0.0.0.0 \
    --port 8000 \
    --path /mcp \
    --vault /vault \
    "$@"
