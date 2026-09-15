FROM python:3.14-slim-bookworm

# uv (официальная схема: /uv и /uvx из distroless-образа).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    ffmpeg \
    procps \
    && rm -rf /var/lib/apt/lists/*

# yt-dlp YouTube JS challenges (nsig). Without a runtime on PATH, googlevideo
# returns HTTP 403. Deno is yt-dlp's default (min 2.3.0); pin the official binary image.
# EJS solver scripts come from the yt-dlp[default] extra (yt-dlp-ejs), not from Deno.
COPY --from=denoland/deno:bin-2.9.6 /deno /usr/local/bin/deno

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups

COPY . .

RUN mkdir -p storage && chmod +x /app/entrypoint.sh /app/migrate.sh

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
