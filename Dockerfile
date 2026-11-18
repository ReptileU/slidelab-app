# Облако (Render и т.п.): бот + API + Mini App одним процессом. См. src/slidelab/cloud.py
FROM node:20-slim AS webapp
WORKDIR /w
COPY webapp/package.json webapp/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY webapp/ ./
RUN npm run build

FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY alembic/ alembic/
COPY src/ src/
COPY content/ content/
RUN uv sync --frozen --no-dev
COPY --from=webapp /w/dist webapp/dist
# Миграции базы — при каждом запуске (быстро, если менять нечего), затем сервер
CMD ["sh", "-c", "uv run --no-dev python -m alembic upgrade head && uv run --no-dev python -m slidelab.core.seed && exec uv run --no-dev uvicorn --factory slidelab.cloud:create_app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips='*'"]
