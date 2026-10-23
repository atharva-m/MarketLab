FROM ghcr.io/astral-sh/uv:0.13.5 AS uv
FROM python:3.13-slim
COPY --from=uv /uv /uvx /bin/
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev \
    && useradd --uid 10001 --create-home marketlab \
    && mkdir -p /data/marketlab \
    && chown -R marketlab:marketlab /data
COPY alembic.ini ./
COPY migrations ./migrations
USER marketlab
ENV PATH="/app/.venv/bin:$PATH" MARKETLAB_STORAGE_PATH=/data/marketlab
EXPOSE 8000
# uvloop 0.23 can orphan DNS futures when a readiness timeout cancels a connection.
CMD ["uvicorn", "marketlab.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--loop", "asyncio", "--no-access-log"]
