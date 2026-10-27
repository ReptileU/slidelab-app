#!/bin/bash
# SlideLab: запуск всего одним кликом — база, API для Mini App, временная ссылка, бот.
# Окно не закрывайте: Ctrl+C или закрытие окна останавливает всё.
cd "$(dirname "$0")" || exit 1
LOGS="data/logs"

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
mkdir -p data "$LOGS"
env_value() { grep -E "^$1=" .env | tail -1 | cut -d= -f2-; }

# Прежний запуск ещё работает — останавливаем, иначе два бота будут спорить за обновления Telegram
pkill -f "slidelab.bot.main" 2>/dev/null
pkill -f "slidelab.api.main" 2>/dev/null
pkill -f "cloudflared tunnel --url http://localhost:8010" 2>/dev/null
sleep 1

# PostgreSQL и Redis — только если они указаны в .env (на домашнем компьютере хватает SQLite)
if env_value DATABASE_URL | grep -q postgresql && command -v docker >/dev/null 2>&1; then
  echo "▸ База PostgreSQL и Redis (Docker)..."
  docker compose -p slidelab up -d --wait >/dev/null || echo "  Docker не ответил — запустите Docker Desktop"
fi

echo "▸ Библиотеки и база..."
uv sync --python 3.12 --no-dev -q
uv run alembic upgrade head >/dev/null
uv run python -m slidelab.core.seed

# Mini App: собираем, если сборки нет или код новее неё
if command -v npm >/dev/null 2>&1; then
  if [ ! -f webapp/dist/index.html ] || [ -n "$(find webapp/src webapp/index.html -newer webapp/dist/index.html 2>/dev/null | head -1)" ]; then
    echo "▸ Собираю Mini App..."
    (cd webapp && { [ -d node_modules ] || npm ci --silent; } && npm run build --silent >/dev/null)
  fi
fi

cleanup() {
  echo
  echo "Останавливаю SlideLab..."
  kill "$API_LOOP" "$TUNNEL_PID" 2>/dev/null
  pkill -f "slidelab.api.main" 2>/dev/null
  pkill -f "slidelab.bot.main" 2>/dev/null
}
trap cleanup EXIT

echo "▸ API для Mini App (порт 8010)..."
(while true; do
  uv run uvicorn --factory slidelab.api.main:create_app --host 127.0.0.1 --port 8010 >>"$LOGS/api.log" 2>&1
  sleep 3
done) &
API_LOOP=$!

# Временная https-ссылка, чтобы Telegram открыл Mini App с этого компьютера.
# Нужна, только если включена новая Mini App (LEGACY_WEBAPP=false) и стоит cloudflared (brew install cloudflared).
if [ "$(env_value LEGACY_WEBAPP)" = "false" ] && command -v cloudflared >/dev/null 2>&1; then
  echo "▸ Временная ссылка для Mini App..."
  : >"$LOGS/tunnel.log"
  cloudflared tunnel --url http://localhost:8010 >>"$LOGS/tunnel.log" 2>&1 &
  TUNNEL_PID=$!
  URL=""
  for _ in $(seq 1 40); do
    URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOGS/tunnel.log" | head -1)
    [ -n "$URL" ] && break
    sleep 0.5
  done
  if [ -n "$URL" ]; then
    # Новая ссылка — в .env: бот при запуске поставит её на кнопку меню
    sed -i '' -E "s#^WEBAPP_URL=.*#WEBAPP_URL=$URL/#" .env
    grep -q "^WEBAPP_URL=" .env || echo "WEBAPP_URL=$URL/" >>.env
    echo "  Mini App: $URL"
  else
    echo "  Ссылка не создалась — Mini App откроется только со старой ссылкой (см. $LOGS/tunnel.log)"
  fi
elif [ "$(env_value LEGACY_WEBAPP)" = "false" ]; then
  echo "  Для новой Mini App с этого компьютера нужен cloudflared: brew install cloudflared"
fi

echo
echo "✓ SlideLab запущен. Логи: $LOGS/. Остановить: Ctrl+C или закрыть окно."
echo
while true; do
  uv run python -m slidelab.bot.main 2>&1 | tee -a "$LOGS/bot.log"
  echo "Бот остановился — перезапускаю через 5 секунд..."
  sleep 5
done
