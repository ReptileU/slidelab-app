# SlideLab

Презентации на заказ в Telegram: бот, Mini App и конвейер, в котором Claude делает обложки и презентации,
а владелец проверяет их перед отправкой клиенту.

## Как устроено

```text
src/slidelab/
├── core/          бизнес-логика — общая для бота, API и фоновых задач
│   ├── models/    заказы, клиенты, пакеты, оплаты, витрина
│   ├── services/  цены · заказы · пакеты · оплата · конвейер Claude
│   └── i18n/      тексты для клиента: ru, uz, en
├── telegram/      клавиатуры, сообщения, сценарии (flows), совместимость со старой витриной
├── bot/           бот на aiogram 3: роутеры, фоновые задачи, публикация постов
├── api/           API для Mini App (FastAPI) + раздача её статики
└── tools/         перенос данных из прежнего бота
webapp/            Mini App: React + TypeScript, чёрно-белый дизайн в стиле Apple
content/           посты канала (posts/), картинки (media/), портфолио (portfolio/)
orders/            папки заказов для конвейера Claude (не в git)
tests/             111 тестов: правила, конвейер, API, сквозные сценарии бота
```

### Путь заказа

1. Клиент оформляет заказ — в чате (7 шагов), в Mini App или просто пересылает файл.
2. Бот пишет `orders/<номер>/brief.json` — Claude начинает бесплатную обложку.
3. Claude кладёт результат в `review/` → владелец получает его с кнопками «Отправить клиенту» / «Доработать».
4. Клиент видит обложку: «Нравится» → оплата (звёзды или карта с чеком). Заплатить можно и заранее.
5. Claude делает презентацию → проверка владельцем → клиент выбирает формат: PowerPoint, PDF, картинки, Google Slides, Canva.
6. Две правки бесплатно. После сдачи — предложение пакета с зачётом этого заказа.

Сторож напоминает владельцу о заказах, по которым Claude не прислал результат за `STUCK_HOURS` часов.

### Контракт с сессией Claude

Формат папки `orders/<номер>/` совпадает с прежним ботом — сессия Claude работает без изменений:
`brief.json` (задание), `status.json` (`stage`, `paid`, `status`), `notes.md`, `files/`, `edits/`,
`review/review.json` (`kind`, `files`, `message`, `urls`, `canva`, `links`), `review/failed.json`.
Подробно — в `src/slidelab/core/services/pipeline.py`.

## Запуск на компьютере (как раньше)

Windows — двойной клик по `start_windows.bat`, Mac — по `start_mac.command`.
При первом запуске скрипт создаст `.env` и откроет его: впишите `BOT_TOKEN` и `ADMIN_ID` (узнать — команда `/id`).
Данные хранятся в `data/slidelab.db`, Docker не нужен. Если бот упадёт, скрипт перезапустит его сам.

### Перенос данных из прежнего бота

```bash
uv run python -m slidelab.tools.import_legacy "путь/к/папке/старого/бота"
```

Переносит `orders.json` и `subs.json` с сохранением номеров заказов. Папку `orders/` старого бота
скопируйте рядом — конвейер подхватит заказы как есть. Посты канала уже лежат в `content/posts/`.
Строки из старого `settings.txt` можно перенести в `.env` без изменений.

## Запуск на сервере

```bash
cp .env.example .env    # DATABASE_URL и REDIS_URL — на PostgreSQL и Redis, WEBHOOK_URL — адрес бота
uv sync --python 3.12
docker compose -p slidelab up -d
uv run alembic upgrade head && uv run python -m slidelab.core.seed
cd webapp && npm ci && npm run build && cd ..
uv run uvicorn --factory slidelab.api.main:create_app --port 8010   # API + Mini App
uv run python -m slidelab.bot.main                                    # бот
```

Новая Mini App: `MINIAPP_URL` — https-адрес API, `LEGACY_WEBAPP=false`.
Пока она не на сервере, бот работает со старой витриной на GitHub Pages и понимает все её заявки.

## Команды

Клиент: `/start` `/new` `/orders` `/prices` `/packages` `/help` `/language` `/paysupport`.
Владелец (в личке с ботом): `/stats` `/subs` `/grant ID тариф` `/refund номер` `/posts` `/repost` `/id`.
Ответ клиенту — реплай на любое сообщение бота со строкой «ID: …».

## Проверки

```bash
uv run pytest                             # SQLite в памяти
TEST_DATABASE_URL=postgresql+asyncpg://slidelab:slidelab@localhost:5433/slidelab_test uv run pytest
uv run ruff check src tests && uv run mypy src && uv run alembic check
cd webapp && npm run build
```
