#!/bin/bash
# SlideLab: запуск бота на компьютере. Окно не закрывайте.
cd "$(dirname "$0")" || exit 1

if ! command -v uv >/dev/null 2>&1; then
  echo "Первый запуск: устанавливаю uv — он сам поставит нужный Python и библиотеки..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Создал файл .env — впишите в него BOT_TOKEN и ADMIN_ID и запустите снова."
  open -e .env
  exit 0
fi
mkdir -p data

uv sync --python 3.12 --no-dev
uv run alembic upgrade head
uv run python -m slidelab.core.seed

# Новая Mini App: собираем один раз, если на компьютере есть Node.js
if [ ! -f webapp/dist/index.html ] && command -v npm >/dev/null 2>&1; then
  (cd webapp && npm ci && npm run build)
fi

# API для Mini App — в фоне, тоже с перезапуском; закрывается вместе с окном
(while true; do
  uv run uvicorn --factory slidelab.api.main:create_app --host 127.0.0.1 --port 8010
  sleep 5
done) &
API_LOOP=$!
trap 'kill $API_LOOP 2>/dev/null; pkill -f "slidelab.api.main" 2>/dev/null' EXIT

while true; do
  echo "Бот SlideLab запущен. Остановить: Ctrl+C"
  uv run python -m slidelab.bot.main
  echo "Бот остановился — перезапускаю через 5 секунд..."
  sleep 5
done
