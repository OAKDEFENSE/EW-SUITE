FROM python:3.11-slim AS base
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml README.md ./
COPY ew_core ./ew_core
RUN uv sync --no-dev --no-cache
ENV PATH="/app/.venv/bin:$PATH" EW_HOST=0.0.0.0 EW_PORT=8000
EXPOSE 8000
CMD ["python", "-m", "ew_core"]
