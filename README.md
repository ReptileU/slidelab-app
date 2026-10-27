# SlideLab

Всё в одном репозитории:

| Папка | Что это |
|---|---|
| `index.html`, `band.png` (корень) | Telegram Mini App — публикуется через GitHub Pages: https://reptileu.github.io/slidelab-app/ |
| `bot/` | Telegram-бот @slidelab_order_bot (`bot.py`) и публикация постов в канал (`publisher.py`) |
| `bot/posts/` | Посты канала @slidelab_uz (очередь на одобрение) |

## Запуск бота
1. Скопируйте папку `bot` на компьютер.
2. Рядом с `bot.py` создайте `settings.txt` со своими данными (BOT_TOKEN, ADMIN_ID, PAY_UZUM, PAY_PAYME, PAY_ZOOMRAD, PAY_NAME).
   **Этот файл в репозиторий не загружается** — он в `.gitignore`.
3. Запустите `start_bot.bat` (Windows) или `start_mac.command` (Mac).

Заказы клиентов (`orders/`, `orders.json`) и медиа тоже не хранятся здесь.
