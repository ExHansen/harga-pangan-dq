# syntax=docker/dockerfile:1
# The pipeline as a container: `docker run --rm -v "$PWD/data:/work/data" hpdq ingest`.
FROM ghcr.io/astral-sh/uv:0.13.7 AS uv

FROM python:3.12-slim
COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app
# Dependencies first (cached layer), then the project itself.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY dbt ./dbt
RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:${PATH}"
RUN useradd --create-home --uid 10001 hpdq
USER hpdq
WORKDIR /work

ENTRYPOINT ["hpdq"]
CMD ["--help"]
