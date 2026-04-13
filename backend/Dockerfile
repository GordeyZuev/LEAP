FROM python:3.14-slim-bookworm

# uv (официальная схема: /uv и /uvx из distroless-образа).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups

COPY . .

RUN mkdir -p storage && chmod +x /app/entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
