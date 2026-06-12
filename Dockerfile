FROM python:3.14.4-slim-trixie

# Keeps Python from generating .pyc files and forces stdout/stderr to be unbuffered
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

ARG VERSION
ENV VERSION=${VERSION}

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install external dependencies first (cacheable layer — only invalidated when
# pyproject.toml / uv.lock change, not on every source change).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application files and install the sealman package itself
COPY --chmod=555 --chown=nobody:nogroup . /app
RUN uv sync --frozen --no-dev

# Create logs directory with correct ownership for the nobody user
RUN mkdir -p /app/logs && chown -R nobody:nogroup /app/logs

USER nobody

CMD ["sh", "-c", "/app/.venv/bin/uvicorn main:app --host 0.0.0.0 --port ${PORT:-5000}"]
