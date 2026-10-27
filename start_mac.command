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

while true; do
  echo "Бот SlideLab запущен. Остановить: Ctrl+C"
  uv run python -m slidelab.bot.main
  echo "Бот остановился — перезапускаю через 5 секунд..."
  sleep 5
done
