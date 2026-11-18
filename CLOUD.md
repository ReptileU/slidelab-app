# SlideLab в облаке (без компьютера)

Бот, API и Mini App работают одним процессом на **Render** (бесплатно), данные — в **Neon** (Postgres, бесплатно).
Компьютер для работы бота не нужен. Код облака — ветка `cloud`, запуск — `src/slidelab/cloud.py`.

| Что | Где |
|---|---|
| Бот + API + Mini App | Render, бесплатный тариф (Docker, `render.yaml`) |
| База | Neon, бесплатно (1 ГБ) |
| Папка заказов `orders/`, `data/`, `content/media` | копия в базе (таблица `stored_files`), на диск сервера — при запуске |
| Большие готовые файлы (>15 МБ) | только в Telegram (уже отправлены клиенту) |
| Чтобы сервис не засыпал | cron-job.org: каждые 10 минут открывает `https://<сервис>.onrender.com/api/health` |
| Сессия Claude «делать заказы» | берёт заказы и сдаёт работу через `https://<сервис>.onrender.com/pipeline/…` с ключом `PIPELINE_KEY` |

## Запуск

1. Render → New → Blueprint → репозиторий `ReptileU/slidelab-app`, ветка `cloud`.
2. Заполнить переменные: `BOT_TOKEN`, `DATABASE_URL` (строка подключения из Neon), `ADMIN_ID`, `BOT_USERNAME`,
   реквизиты `PAY_*`. Адрес сервиса (webhook и Mini App) Render подставляет сам.
3. Перенести данные с компьютера: на компьютере в `.env` добавить строку
   `CLOUD_DATABASE_URL=<строка подключения из Neon>` и запустить `cloud_push.bat`.
   **Перед этим остановить бота на компьютере** — иначе новые заказы останутся только на компьютере.
4. В Render нажать Manual Deploy → Deploy latest commit (бот при запуске забирает файлы из базы).
5. cron-job.org: задача на `https://<сервис>.onrender.com/api/health` каждые 10 минут.
6. В BotFather у бота: Main App / кнопка меню — `https://<сервис>.onrender.com/`.

## Откат на компьютер

1. Render → сервис → Settings → **Suspend** (бот в облаке остановлен).
2. На компьютере запустить `cloud_pull.bat` — он создаст `data\slidelab_from_cloud.db`,
   папки `orders_from_cloud\` и `content_from_cloud\`.
3. Переименовать: `data\slidelab.db` → `data\slidelab_before_rollback.db`,
   `data\slidelab_from_cloud.db` → `data\slidelab.db`; содержимое `orders_from_cloud\` скопировать в `orders\`.
4. Запустить `restart_bot.bat` — бот снова работает на компьютере (webhook он снимает сам при запуске).
