# SlideLab — карта проекта

Telegram-бот + мини-приложение (React) для заказа презентаций. Этот файл — чтобы не перечитывать весь проект ради одной правки:
найди раздел ниже, открой только нужный файл и только нужный кусок (grep → Read с offset/limit).

## Где что лежит

### Бэкенд (Python, `src/slidelab/`)
| Что меняем | Файл |
|---|---|
| Настройки, переменные окружения | `config.py` |
| Таблицы БД | `core/models/` (user, order, billing…) + миграция в `alembic/versions/` |
| Цены, срочность, скидка первого заказа | `core/services/pricing.py` |
| Заказ: создание, отмена, статусы, быстрая обложка | `core/services/orders.py` |
| Оплата, чеки, Stars | `core/services/payments.py` |
| Пакеты презентаций | `core/services/packages.py` |
| Баллы, кейсы, призы и шансы | `core/services/points.py` |
| Пригласить друга, приветственный кейс | `core/services/referrals.py` |
| Подарки | `core/services/gifts.py` |
| Автоматическая работа над заказом (API для дизайнера) | `core/services/pipeline.py` |
| Тексты бота (ru/uz/en) | `core/i18n/` |
| API для мини-приложения | `api/routes/` (orders, me, packages, catalog, gifts, support) |
| Команды и кнопки клиента в боте | `bot/routers/` (start, order, orders, payments, support) |
| Рабочее место команды | `bot/routers/staff/`: `cards.py` — кнопки на карточке заказа; `reports.py` — /stats, /users, /subs, /grant; `chat.py` — ответы клиентам; `tools.py` — /emoji, /demo, /logo |
| Сообщения клиенту и команде, клавиатуры | `telegram/flows.py`, `telegram/keyboards.py`, `telegram/views.py`, `telegram/notifier.py` |

### Мини-приложение (`webapp/src/`)
| Что меняем | Файл |
|---|---|
| Экраны | `screens/` (Home, NewOrder — анкета, QuickCover — бесплатная обложка, OrderDetail, Orders, Packages, Profile, Invite, Styles, Done, Demo) |
| Общие кусочки интерфейса | `ui/index.tsx` (кнопки, поля, группы) |
| Анкета: блоки и выбор дизайна | `ui/FormKit.tsx` |
| Кейсы и рулетка | `ui/PointsCase.tsx`, выпадение — `ui/LuckyPack.tsx` |
| Карты: пакет / скидка / купон | `ui/PackCard.tsx`, `ui/Discount.tsx`, `ui/Coupon.tsx` |
| Запросы к API, типы | `lib/api.ts`, `lib/types.ts` |
| Переходы из бота (`?go=…`) | `main.tsx` |
| **Тексты** | `lib/i18n/`: `form.ts` (анкета), `order.ts` (экран заказа), `rewards.ts` (баллы, кейсы, рефералка), `wallet.ts` (пакеты, оплата), `common.ts` (остальное). В каждом файле ru, uz и en; ключ добавляется во все три |
| **Стили** | `styles/NN-раздел.css` (список — в `styles.css`): анкета → `15-form.css`, кейсы и баллы → `12-points-cases.css`, приглашение → `13-invite.css`, пакеты → `07-packages.css`, ПК-раскладка → `09-desktop.css`. Порядок файлов важен: чем позже, тем сильнее правило |

### Тесты (`tests/`)
По файлу на тему: test_orders, test_payments, test_points, test_referrals, test_quick_cover, test_api, test_bot_flow, test_staff_users…

## Команды
```bash
uv run ruff check --fix src tests && uv run ruff format src tests && uv run mypy src
uv run pytest -q                       # нужен TEST_DATABASE_URL для Postgres-тестов, иначе SQLite
cd webapp && npm run build             # tsc + vite; сборка лежит в webapp/dist
uv run alembic revision -m "..."       # новая миграция (render_as_batch для SQLite)
```

## Ветки и выкладка
- `main` — бот на компьютере владельца. Туда **не выкатываем**, пока владелец не скажет «переносим».
- `cloud` = main + облачные настройки (`render/`). Тестовый бот на Render собирается автоматически из `cloud`.
- После коммита в main: `git checkout cloud && git merge --no-edit main` → если `alembic heads` показывает две головы, сделать merge-ревизию → тесты → `git push origin cloud` → вернуться в main.

## Как экономить лимит
- Не читать большие файлы целиком: сначала `grep -n`, потом `Read` с offset/limit.
- Скриншоты мини-приложения (Playwright) — только когда просят или когда меняется вёрстка, а не на каждую правку текста.
- Мелкие правки — пачкой, в новом чате; эта карта даёт нужный контекст.

## Нельзя
- Коммитить токены, `.env`, `settings.txt`, ключи (PIPELINE_KEY) и данные клиентов — репозиторий публичный.
- Выводить в чат токен бота и строки подключения к БД.
