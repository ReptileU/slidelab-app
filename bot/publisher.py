"""
Публикация постов в канал SlideLab с одобрением владельца.

Посты лежат в папке posts/ — по одному .txt файлу на пост:

    time: 2026-10-26 10:00             ← когда опубликовать (время компьютера)
    images: media/foto1.jpg, portfolio/01_ar-deko.png   ← необязательно, до 10 картинок
    pin: yes                           ← необязательно: закрепить после публикации
    ---
    Текст поста (можно <b>жирный</b>, <i>курсив</i>, <a href="...">ссылки</a>)

  • Одна картинка → пост с фото. Несколько → альбом.
  • Можно писать и image: (одна картинка) — старый формат тоже работает.

Владелец:
  • получает превью каждого нового/изменённого поста с кнопками
        ✅ Сейчас   🕐 По расписанию   ❌ Отклонить
  • если изменить УЖЕ опубликованный пост — бот предложит
        ✏️ Обновить в канале   (меняется текст; одиночное фото тоже можно заменить)
  • может прислать боту обычное фото или картинку — бот сохранит её в папку media/
    и ответит именем файла, чтобы вставить в пост
  • /posts — список постов и статусы
"""

import asyncio
import hashlib
import aiohttp
import json
import logging
from datetime import datetime
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InputMediaPhoto,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

BASE_DIR = Path(__file__).parent
POSTS_DIR = BASE_DIR / "posts"
MEDIA_DIR = BASE_DIR / "media"
STATE_FILE = POSTS_DIR / "state.json"
CHECK_EVERY_SEC = 60
CAPTION_LIMIT = 1024
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")

STATUS_RU = {
    "review": "⏳ ждёт одобрения",
    "queued": "📬 в очереди на одобрение",
    "scheduled": "🕐 одобрен, ждёт времени",
    "published": "✅ опубликован",
    "edit_review": "✏️ изменён, ждёт подтверждения",
    "rejected": "❌ отклонён",
    "error": "⚠️ ошибка",
}

router = Router()
_cfg: dict = {}   # admin_id, channel, publisher (Bot для канала)


# ───────────── чтение постов ─────────────
def parse_post(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8-sig")
    head, sep, body = raw.partition("\n---")
    if not sep:
        raise ValueError("нет строки --- между настройками и текстом")
    meta = {}
    for line in head.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
    if "time" not in meta:
        raise ValueError("нет строки time:")
    when = datetime.strptime(meta["time"], "%Y-%m-%d %H:%M")
    text = body.lstrip("-").strip("\n").strip()
    if not text:
        raise ValueError("пустой текст поста")

    names = []
    for key in ("images", "image"):
        if meta.get(key):
            names += [n.strip() for n in meta[key].split(",") if n.strip()]
    images, missing = [], []
    for n in names[:10]:
        p = url_cache_path(n) if n.lower().startswith("http") else (BASE_DIR / n).resolve()
        (images if p.is_file() else missing).append(p if p.is_file() else n)

    video = None
    if meta.get("video"):
        vp = (BASE_DIR / meta["video"].strip()).resolve()
        if vp.is_file():
            video = vp
        else:
            missing.append(meta["video"].strip())

    return {
        "id": path.stem,
        "video": video,
        "when": when,
        "text": text,
        "images": images,
        "missing": missing,
        "pin": meta.get("pin", "").lower() in ("yes", "да", "1", "true"),
        "hash": hashlib.md5(raw.encode("utf-8")).hexdigest(),
        "img_sig": "|".join(f"{p.name}:{p.stat().st_size}" for p in images + ([video] if video else [])),
    }


def url_cache_path(url: str) -> Path:
    """Картинки по ссылке (например, из Canva) кешируются в media/url_*.png."""
    return MEDIA_DIR / f"url_{hashlib.md5(url.encode()).hexdigest()[:12]}.png"


def header_urls(path: Path) -> list[str]:
    try:
        head = path.read_text(encoding="utf-8-sig").split("\n---", 1)[0]
    except Exception:  # noqa: BLE001
        return []
    urls = []
    for line in head.splitlines():
        k, _, v = line.partition(":")
        if k.strip().lower() in ("images", "image"):
            urls += [u.strip() for u in v.split(",") if u.strip().lower().startswith("http")]
    return urls


async def fetch_urls(path: Path) -> list[str]:
    """Скачивает картинки по ссылкам из поста (один раз). Возвращает ошибки."""
    errors = []
    for url in header_urls(path):
        dest = url_cache_path(url)
        if dest.exists():
            continue
        MEDIA_DIR.mkdir(exist_ok=True)
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=60)) as r:
                    r.raise_for_status()
                    dest.write_bytes(await r.read())
        except Exception as e:  # noqa: BLE001
            errors.append(f"{url[:60]}…: {e}")
    return errors


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def save_state(state: dict) -> None:
    POSTS_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def all_posts() -> list:
    out = []
    if not POSTS_DIR.is_dir():
        return out
    for p in sorted(POSTS_DIR.glob("*.txt")):
        if p.name.lower().startswith(("readme", "пример", "_")):
            continue
        try:
            out.append((p, parse_post(p), None))
        except Exception as e:  # noqa: BLE001
            out.append((p, None, str(e)))
    return out


def find_post(pid: str):
    return next((p for f, p, e in all_posts() if f.stem == pid and p), None)


# ───────────── отправка ─────────────
async def send_post(bot: Bot, chat_id, post: dict, reply_markup=None) -> dict:
    """Отправляет пост. Возвращает {'ids': [...], 'kind': 'text'|'photo'|'album', 'text_id': id}."""
    text, imgs = post["text"], post["images"]
    fits = len(text) <= CAPTION_LIMIT

    if post.get("video"):   # видео-пост (строка video: в шапке)
        vid = FSInputFile(post["video"])
        if fits:
            m = await bot.send_video(chat_id, vid, caption=text, supports_streaming=True, reply_markup=reply_markup)
            return {"ids": [m.message_id], "kind": "video", "text_id": m.message_id}
        v = await bot.send_video(chat_id, vid, supports_streaming=True)
        m = await bot.send_message(chat_id, text, reply_markup=reply_markup)
        return {"ids": [v.message_id, m.message_id], "kind": "video+text", "text_id": m.message_id}

    if not imgs:
        m = await bot.send_message(chat_id, text, reply_markup=reply_markup)
        return {"ids": [m.message_id], "kind": "text", "text_id": m.message_id}

    if len(imgs) == 1:
        photo = FSInputFile(imgs[0])
        if fits:
            m = await bot.send_photo(chat_id, photo, caption=text, reply_markup=reply_markup)
            return {"ids": [m.message_id], "kind": "photo", "text_id": m.message_id}
        p = await bot.send_photo(chat_id, photo)
        m = await bot.send_message(chat_id, text, reply_markup=reply_markup)
        return {"ids": [p.message_id, m.message_id], "kind": "photo+text", "text_id": m.message_id}

    media = [InputMediaPhoto(media=FSInputFile(i)) for i in imgs]
    if fits:
        media[0].caption = text
    msgs = await bot.send_media_group(chat_id, media)
    ids = [m.message_id for m in msgs]
    if fits and reply_markup is None:
        return {"ids": ids, "kind": "album", "text_id": ids[0]}
    # кнопки к альбому прикрепить нельзя — отправляем текст отдельным сообщением
    m = await bot.send_message(chat_id, text if not fits else "👆 Пост выше", reply_markup=reply_markup)
    return {"ids": ids + [m.message_id], "kind": "album+text", "text_id": m.message_id if not fits else ids[0]}


def review_kb(post_id: str, ver: str = ""):
    v = f":{ver[:8]}" if ver else ""
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Сейчас", callback_data=f"pub:now:{post_id}{v}")
    kb.button(text="🕐 По расписанию", callback_data=f"pub:sched:{post_id}{v}")
    kb.button(text="❌ Отклонить", callback_data=f"pub:no:{post_id}{v}")
    kb.adjust(2, 1)
    return kb.as_markup()


def edit_kb(post_id: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Обновить в канале", callback_data=f"pub:edit:{post_id}")
    kb.button(text="Оставить как было", callback_data=f"pub:keep:{post_id}")
    kb.adjust(1)
    return kb.as_markup()


def _notes(post: dict) -> str:
    n = ""
    if post["images"]:
        n += f"\n🖼 Картинок: {len(post['images'])}"
    if post.get("video"):
        n += "\n🎬 Видео"
    if post["missing"]:
        n += "\n⚠️ Не найдены: " + ", ".join(f"<code>{str(m)[:60]}</code>" for m in post["missing"])
    if post["pin"]:
        n += "\n📌 Будет закреплён"
    return n


async def send_for_review(bot: Bot, post: dict, left: int = 0) -> None:
    admin = _cfg["admin_id"]
    more = f"\n📬 Ещё в очереди: {left} — пришлю следующий после вашего ответа" if left else ""
    await bot.send_message(
        admin,
        f"📝 <b>Пост на одобрение</b>: <code>{post['id']}</code>\n"
        f"🕐 Время публикации: <b>{post['when']:%d.%m.%Y %H:%M}</b>" + _notes(post) + more)
    await send_post(bot, admin, post, reply_markup=review_kb(post["id"], post["hash"]))


async def send_edit_review(bot: Bot, post: dict, st: dict) -> None:
    admin = _cfg["admin_id"]
    warn = ""
    if post["img_sig"] != st.get("img_sig", "") and st.get("kind") not in ("photo",):
        warn = ("\n⚠️ Картинки изменились — в канале обновится только текст. "
                "Чтобы заменить картинки, удалите пост в канале и сбросьте его через /repost "
                f"{post['id']}")
    await bot.send_message(
        admin,
        f"✏️ <b>Изменён опубликованный пост</b> <code>{post['id']}</code>\n"
        f"В канале: {st.get('link', '')}{warn}\nНовая версия 👇")
    await send_post(bot, admin, post, reply_markup=edit_kb(post["id"]))


async def publish(post: dict) -> dict:
    publisher: Bot = _cfg["publisher"]
    channel = _cfg["channel"]
    res = await send_post(publisher, channel, post)
    if post["pin"]:
        try:
            await publisher.pin_chat_message(channel, res["ids"][0], disable_notification=True)
        except Exception as e:  # noqa: BLE001
            logging.warning("Не удалось закрепить пост: %s", e)
    uname = str(channel).lstrip("@")
    return {**res, "link": f"https://t.me/{uname}/{res['ids'][0]}",
            "published_at": f"{datetime.now():%Y-%m-%d %H:%M}"}


async def edit_published(post: dict, st: dict) -> None:
    publisher: Bot = _cfg["publisher"]
    channel = _cfg["channel"]
    kind, tid = st.get("kind", "text"), st.get("text_id") or st.get("ids", [None])[0]
    if kind == "photo":
        if post["img_sig"] != st.get("img_sig", "") and len(post["images"]) == 1:
            await publisher.edit_message_media(
                InputMediaPhoto(media=FSInputFile(post["images"][0]), caption=post["text"]),
                chat_id=channel, message_id=tid)
        else:
            await publisher.edit_message_caption(chat_id=channel, message_id=tid, caption=post["text"])
    elif kind in ("album", "video"):
        await publisher.edit_message_caption(chat_id=channel, message_id=tid, caption=post["text"])
    else:
        await publisher.edit_message_text(post["text"], chat_id=channel, message_id=tid)


def _published_state(post: dict, res: dict) -> dict:
    return {"hash": post["hash"], "img_sig": post["img_sig"], "status": "published", **res}


# ───────────── фоновая проверка ─────────────
async def tick(bot: Bot) -> None:
    state = load_state()
    changed = False
    admin = _cfg["admin_id"]
    for path in sorted(POSTS_DIR.glob("*.txt")) if POSTS_DIR.is_dir() else []:
        for e in await fetch_urls(path):
            logging.warning("Картинка по ссылке не скачалась (%s): %s", path.name, e)
    for path, post, err in all_posts():
        pid = path.stem
        st = state.get(pid, {})
        if err:
            if st.get("error") != err:
                await bot.send_message(admin, f"⚠️ Ошибка в посте <code>{path.name}</code>: {err}")
                state[pid] = {**st, "error": err, "status": st.get("status", "error")}
                changed = True
            continue
        if st.get("error"):
            st.pop("error"); state[pid] = st; changed = True

        status = st.get("status")
        if status in ("published", "edit_review"):
            if st.get("hash") != post["hash"] and st.get("edit_hash") != post["hash"]:
                await send_edit_review(bot, post, st)
                state[pid] = {**st, "status": "edit_review", "edit_hash": post["hash"]}
                changed = True
            continue

        if st.get("hash") != post["hash"]:
            state[pid] = {"hash": post["hash"], "status": "queued"}
            changed = True
            continue

        if status == "scheduled" and datetime.now() >= post["when"]:
            try:
                res = await publish(post)
                state[pid] = _published_state(post, res)
                await bot.send_message(admin, f"✅ Опубликовано: {res['link']}")
            except Exception as e:  # noqa: BLE001
                logging.exception("Ошибка публикации")
                state[pid] = {**st, "error": str(e)}
                await bot.send_message(admin, f"⚠️ Не удалось опубликовать <code>{pid}</code>: {e}\n"
                                              "Проверьте, что бот — админ канала с правом публикации.")
            changed = True
    # Очередь на одобрение: присылаем владельцу только ОДИН пост за раз (ближайший по времени).
    # Следующий придёт, когда ответите на текущий. Старые «review» без пометки q считаем очередью.
    posts = {path.stem: post for path, post, err in all_posts() if post and not err}
    waiting = [pid for pid, st in state.items() if st.get("status") == "review" and st.get("q") and pid in posts]
    if not waiting:
        queue = sorted((posts[pid]["when"], pid) for pid, st in state.items()
                       if pid in posts and (st.get("status") == "queued" or (st.get("status") == "review" and not st.get("q"))))
        if queue:
            _, pid = queue[0]
            await send_for_review(bot, posts[pid], left=len(queue) - 1)
            state[pid] = {**state[pid], "status": "review", "q": True}
            changed = True
    if changed:
        save_state(state)


async def loop(bot: Bot) -> None:
    POSTS_DIR.mkdir(exist_ok=True)
    MEDIA_DIR.mkdir(exist_ok=True)
    await asyncio.sleep(3)
    while True:
        try:
            await tick(bot)
        except Exception:  # noqa: BLE001
            logging.exception("Ошибка в проверке постов")
        await asyncio.sleep(CHECK_EVERY_SEC)


# ───────────── кнопки и команды владельца ─────────────
def is_admin(user_id: int) -> bool:
    return user_id == _cfg.get("admin_id")


@router.callback_query(F.data.startswith("pub:"))
async def on_review(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id):
        await cb.answer()
        return
    _, action, rest = cb.data.split(":", 2)
    pid, _, ver = rest.partition(":")   # ver — первые 8 символов хэша версии, которую вы смотрели
    state = load_state()
    st = state.get(pid, {})
    post = find_post(pid)
    if not post:
        await cb.answer("Пост не найден", show_alert=True)
        return
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass

    if action in ("edit", "keep"):
        if st.get("status") != "edit_review":
            await cb.answer("Уже обработано", show_alert=True)
            return
        if action == "keep":
            st["status"] = "published"
            await cb.message.answer(f"Ок, пост <code>{pid}</code> в канале не меняю.")
        else:
            try:
                await edit_published(post, st)
                st.update(hash=post["hash"], img_sig=post["img_sig"], status="published")
                st.pop("edit_hash", None)
                await cb.message.answer(f"✏️ Пост обновлён в канале: {st.get('link', '')}")
            except Exception as e:  # noqa: BLE001
                logging.exception("Ошибка редактирования")
                st["status"] = "published"
                await cb.message.answer(f"⚠️ Не удалось изменить пост: {e}")
        state[pid] = st
        save_state(state)
        await cb.answer()
        return

    if st.get("status") == "published":
        await cb.answer("Уже опубликован", show_alert=True)
        return
    if ver and ver != post["hash"][:8]:
        # кнопка со старой версии поста: файл с тех пор переделали — решение к новой версии не применяем
        await cb.message.answer(f"🔄 Это старая версия поста <code>{pid}</code> — он уже переделан. "
                                "Новую версию пришлю (или уже прислал) отдельным сообщением — ответьте на неё.")
        await cb.answer()
        return
    if action == "no":
        state[pid] = {"hash": post["hash"], "status": "rejected"}
        await cb.message.answer(f"❌ Пост <code>{pid}</code> отклонён.")
    elif action == "sched":
        state[pid] = {"hash": post["hash"], "status": "scheduled"}
        await cb.message.answer(f"🕐 Пост <code>{pid}</code> выйдет {post['when']:%d.%m в %H:%M}.")
    elif action == "now":
        try:
            res = await publish(post)
            state[pid] = _published_state(post, res)
            await cb.message.answer(f"✅ Опубликовано: {res['link']}")
        except Exception as e:  # noqa: BLE001
            logging.exception("Ошибка публикации")
            await cb.message.answer(f"⚠️ Не удалось опубликовать: {e}\n"
                                    "Проверьте, что бот — админ канала с правом публикации.")
    save_state(state)
    await cb.answer()


@router.message(Command("posts"))
async def cmd_posts(message: Message):
    if not is_admin(message.from_user.id):
        return
    state = load_state()
    lines = ["🗂 <b>Посты</b>"]
    items = all_posts()
    if not items:
        lines.append("Папка posts пуста.")
    for path, post, err in items:
        st = state.get(path.stem, {})
        status = STATUS_RU.get(st.get("status"), "🆕 новый")
        when = f"{post['when']:%d.%m %H:%M}" if post else "—"
        link = f" — {st['link']}" if st.get("link") else ""
        lines.append(f"• <code>{path.stem}</code> — {when} — {status}{link}")
    await message.answer("\n".join(lines), disable_web_page_preview=True)


@router.message(Command("repost"))
async def cmd_repost(message: Message):
    """/repost <id> — забыть, что пост опубликован (после ручного удаления в канале)."""
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Напишите: /repost имя_поста (например /repost 01_znakomstvo)")
        return
    pid = parts[1].strip()
    state = load_state()
    if pid in state:
        state.pop(pid)
        save_state(state)
        await message.answer(f"Ок. Пост <code>{pid}</code> снова придёт на одобрение в течение минуты.")
    else:
        await message.answer("Такого поста нет в списке /posts.")


# Владелец присылает фото → сохраняем в media/
@router.message(StateFilter(None), lambda m: m.from_user and is_admin(m.from_user.id),
                F.photo | (F.document & F.document.mime_type.startswith("image/")))
async def save_admin_photo(message: Message, bot: Bot):
    MEDIA_DIR.mkdir(exist_ok=True)
    if message.photo:
        file_id, ext = message.photo[-1].file_id, ".jpg"
    else:
        file_id = message.document.file_id
        ext = Path(message.document.file_name or "img.jpg").suffix.lower() or ".jpg"
        if ext not in IMAGE_EXT:
            ext = ".jpg"
    name = f"{datetime.now():%Y-%m-%d_%H%M%S}{ext}"
    dest = MEDIA_DIR / name
    await bot.download(file_id, destination=dest)
    note = f"\n📝 Подпись: {message.caption}" if message.caption else ""
    await message.answer(
        f"📥 Сохранил: <code>media/{name}</code>{note}\n"
        "Скажите Claude, в какой пост её поставить, — или впишите в пост строкой\n"
        f"<code>images: media/{name}</code>")
    with (MEDIA_DIR / "captions.txt").open("a", encoding="utf-8") as f:
        f.write(f"{name}\t{message.caption or ''}\n")


def setup(admin_id: int, channel: str, publisher: Bot) -> Router:
    _cfg.update(admin_id=admin_id, channel=channel, publisher=publisher)
    return router
