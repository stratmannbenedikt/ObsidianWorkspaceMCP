# syntax=docker/dockerfile:1.7
# ---- builder --------------------------------------------------------------
FROM python:3.12-slim AS builder

# The version is the single source of truth in pyproject.toml. The workflow
# passes it in explicitly via --build-arg; the local fallback reads the
# file at build time so `docker build .` from a checkout just works.
ARG APP_VERSION=""

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY docker-entrypoint.sh ./docker-entrypoint.sh

# If APP_VERSION wasn't supplied, derive it from pyproject.toml. The
# resolved value is then written to a file the runtime stage consumes
# — Dockerfile ARGs don't survive across `FROM`.
RUN set -eux; \
    if [ -z "$APP_VERSION" ]; then \
        APP_VERSION=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"); \
    fi; \
    echo "Building version $APP_VERSION"; \
    printf '%s' "$APP_VERSION" > /tmp/APP_VERSION; \
    pip install --prefix=/install .

# ---- runtime --------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Re-declare APP_VERSION so the build-arg flows into this stage as well.
# The value matches what the builder resolved (or what was passed via
# --build-arg). After the COPY, the file at /etc/obsidian-mcp/APP_VERSION
# is also the source of truth — entrypoint.sh reads it at startup.
ARG APP_VERSION="0.0.0+unknown"
COPY --from=builder /tmp/APP_VERSION /etc/obsidian-mcp/APP_VERSION
COPY --from=builder /build/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create an unprivileged user. UID 1000 matches the typical host user and
# keeps bind-mounted vault files writable without requiring root.
RUN groupadd --system --gid 1000 mcp \
    && useradd  --system --uid 1000 --gid mcp --home-dir /vault --shell /usr/sbin/nologin mcp

WORKDIR /app

# Copy the installed package from the builder stage.
COPY --from=builder /install /usr/local

# Default mount point for the Obsidian vault. Override by mounting wherever
# you like and pointing OBSIDIAN_VAULT_PATH at it.
RUN mkdir -p /vault && chown -R mcp:mcp /vault

# OCI image labels — discoverable via `docker inspect` and registry UIs.
# Re-declaring ARG before LABEL ensures the value is still in scope.
ARG APP_VERSION
LABEL org.opencontainers.image.title="obsidian-workspace-mcp" \
      org.opencontainers.image.description="Minimal MCP server for safe, agent-friendly Obsidian vault operations" \
      org.opencontainers.image.source="https://github.com/stratmannbenedikt/ObsidianWorkspaceMCP" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${APP_VERSION}"

USER mcp

EXPOSE 8000

ENV MCP_HOST=0.0.0.0 \
    MCP_PORT=8000 \
    MCP_PATH=/mcp \
    OBSIDIAN_VAULT_PATH=/vault

# Wrapper script exports APP_VERSION then execs the server.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import json, urllib.request; req = urllib.request.Request('http://127.0.0.1:8000/mcp', method='POST', headers={'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}, data=json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2024-11-05', 'capabilities': {}, 'clientInfo': {'name': 'healthcheck', 'version': '0'}}}).encode()); urllib.request.urlopen(req, timeout=3).read()" || exit 1
