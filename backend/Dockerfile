FROM python:3.12-slim AS python-base
FROM ghcr.io/astral-sh/uv:0.13.0 AS uv-bin

FROM python-base AS dependencies
COPY --from=uv-bin /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

FROM python-base AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    APP_ENV=production \
    DATA_STORAGE_PATH=/data/papertrail.sqlite3

WORKDIR /app
RUN groupadd --system --gid 10001 papertrail \
    && useradd --system --uid 10001 --gid papertrail --home-dir /app papertrail \
    && mkdir -p /data \
    && chown papertrail:papertrail /data

COPY --from=dependencies --chown=papertrail:papertrail /app/.venv /app/.venv
COPY --chown=papertrail:papertrail app ./app

USER papertrail
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/ready', timeout=3)"

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
