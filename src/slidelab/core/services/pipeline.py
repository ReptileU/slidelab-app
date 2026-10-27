"""Конвейер: Claude делает → владелец проверяет → бот отправляет клиенту.

Контракт с сессией Claude — папка orders/<номер>/ (формат прежнего бота, менять нельзя):

    brief.json        задание: тема, объём, язык, дизайн, пожелания
    status.json       {"stage": "cover_todo" | "deck_todo" | "edit_todo" | …, "paid": bool, "status": "new" | …}
    notes.md          ход заказа: правки клиента, замечания владельца, оплата
    files/, edits/    материалы клиента и скриншоты к правкам
    review/           Claude кладёт сюда результат и review.json:
                      {"kind": "cover" | "deck" | "edit", "files": [...], "message": "...",
                       "urls": [{"name", "url"}], "canva": "...", "links": {"gslides", "canva", "view"}}
                      или failed.json {"reason": "..."}; claim.json — «взял в работу»
    sent_<kind>_<время>/      отправленное клиенту
    rejected_<kind>_<время>/  отклонённое владельцем
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from slidelab.core.enums import Deadline, Design, OrderStatus, SlideTier, Stage
from slidelab.core.models import Order
from slidelab.core.models.base import as_utc

TODO: dict[Stage, str] = {Stage.COVER_TODO: "cover", Stage.DECK_TODO: "deck", Stage.EDIT_TODO: "edit"}
REVIEW_OF: dict[str, Stage] = {
    "cover": Stage.COVER_REVIEW,
    "deck": Stage.DECK_REVIEW,
    "edit": Stage.EDIT_REVIEW,
}
TODO_OF: dict[str, Stage] = {kind: stage for stage, kind in TODO.items()}
KIND_RU = {"cover": "Обложка", "deck": "Презентация", "edit": "Исправленная презентация"}
KIND_ACC = {"cover": "обложку", "deck": "презентацию", "edit": "правки"}

# Значения brief.json — по-русски, как их ждёт сессия Claude
SLIDES_RU = {SlideTier.S10: "до 10", SlideTier.S20: "11–20", SlideTier.S30: "21–30"}
DEADLINE_RU = {
    Deadline.URGENT: "⚡ Срочно (+50%)",
    Deadline.NORMAL: "📅 Обычно — срок обсудим в чате",
    Deadline.RELAXED: "🐢 Не спешу",
}
# status.json хранит статус в словаре прежнего бота
LEGACY_STATUS = {
    OrderStatus.NEW: "new",
    OrderStatus.COVER: "cover",
    OrderStatus.AWAITING_PAYMENT: "cover",
    OrderStatus.WORK: "work",
    OrderStatus.REVISION: "edit",
    OrderStatus.DONE: "done",
    OrderStatus.CANCELLED: "cancel",
}

FORMAT_ORDER = ["pptx", "pdf", "png", "docx"]
_UNSAFE = re.compile(r'[\\/:*?"<>|]')


@dataclass(frozen=True, slots=True)
class ReadyReview:
    order_id: int
    kind: str
    files: list[Path]
    message: str = ""
    canva: str = ""
    urls: list[dict[str, str]] = field(default_factory=list)


def safe_name(name: str) -> str:
    return _UNSAFE.sub("_", name)[:120] or "file"


def fmt_of(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    return {"ppt": "pptx", "jpg": "png", "jpeg": "png", "doc": "docx"}.get(ext, ext)


def formats_of(files: list[Path]) -> list[str]:
    found = {fmt_of(f) for f in files}
    return [x for x in FORMAT_ORDER if x in found] + sorted(found - set(FORMAT_ORDER))


class Pipeline:
    def __init__(self, work_dir: Path) -> None:
        self.root = work_dir

    def dir(self, order_id: int) -> Path:
        d = self.root / str(order_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    # --- задание ---

    def write_brief(self, order: Order, client_name: str, style_name: str | None = None) -> None:
        comment = order.comment or ""
        if style_name:
            comment = f"Стиль из витрины: {style_name}. {comment}".strip()
        brief = {
            "id": order.id,
            "client_lang": order.ui_lang.value,
            "topic": order.topic,
            "slides": SLIDES_RU[order.slides],
            "deadline": DEADLINE_RU[order.deadline],
            "presentation_lang": order.pres_lang.value,
            "design": "свой шаблон клиента" if order.design is Design.OWN else "дизайн делаем мы по теме",
            "template_link": order.template_url or "",
            "need_text": order.extra_text,
            "need_notes": order.extra_notes,
            "need_humor": order.need_humor,  # стиль и база мемов — bot/memes.md на GitHub
            "comment": comment,
            "sources": order.sources or "",
            "client_will_send_files": order.has_source_files,
            "client": client_name,
            "created": as_utc(order.created_at).strftime("%Y-%m-%d %H:%M"),
        }
        self._write_json(self.dir(order.id) / "brief.json", brief, indent=1)
        self.sync_status(order)

    def sync_status(self, order: Order) -> None:
        """status.json — что сейчас нужно делать по заказу (его читает Claude)."""
        self._write_json(
            self.dir(order.id) / "status.json",
            {
                "stage": order.stage.value if order.stage else None,
                "paid": order.is_paid,
                "status": LEGACY_STATUS[order.status],
            },
        )

    def add_note(self, order_id: int, who: str, text: str) -> None:
        with (self.dir(order_id) / "notes.md").open("a", encoding="utf-8") as f:
            f.write(f"\n## {datetime.now():%Y-%m-%d %H:%M} — {who}\n{text.strip()}\n")

    def material_path(self, order_id: int, name: str, sub: str = "files") -> Path:
        d = self.dir(order_id) / sub
        d.mkdir(exist_ok=True)
        return d / safe_name(name)

    # --- результат от Claude ---

    def ready_reviews(self, orders: dict[int, Order]) -> list[ReadyReview]:
        """Заказы, по которым Claude положил результат (review/review.json), пока стадия «сделать»."""
        found = []
        for manifest in sorted(self.root.glob("*/review/review.json")):
            name = manifest.parent.parent.name
            if not name.isdigit():
                continue
            order = orders.get(int(name))
            if order is None or order.stage not in TODO:
                continue
            data = self._read_json(manifest)
            found.append(
                ReadyReview(
                    order_id=order.id,
                    kind=str(data.get("kind") or TODO[order.stage]),
                    files=[manifest.parent / f for f in data.get("files", []) if (manifest.parent / f).exists()],
                    message=str(data.get("message", "")),
                    canva=str(data.get("canva", "")),
                    urls=[u for u in data.get("urls", []) if isinstance(u, dict) and u.get("url")],
                )
            )
        return found

    def add_downloaded(self, order_id: int, name: str) -> None:
        """Файл по ссылке из review.json скачан — дописать его в список файлов."""
        manifest = self.dir(order_id) / "review" / "review.json"
        data = self._read_json(manifest)
        files = data.setdefault("files", [])
        if name not in files:
            files.append(name)
        self._write_json(manifest, data)

    def review_files_pending(self, order_id: int) -> list[Path]:
        """Файлы из review.json — после докачки ссылок."""
        rv = self.dir(order_id) / "review"
        names = self._read_json(rv / "review.json").get("files", [])
        return [rv / n for n in names if (rv / n).exists()]

    def mark_review_sent(self, order_id: int) -> None:
        """Результат показан владельцу: review.json → review.sent.json, «взял в работу» снимаем."""
        rv = self.dir(order_id) / "review"
        manifest = rv / "review.json"
        if manifest.exists():
            manifest.rename(rv / "review.sent.json")
        (rv / "claim.json").unlink(missing_ok=True)

    def review_files(self, order_id: int) -> list[Path]:
        rv = self.dir(order_id) / "review"
        names = self._read_json(rv / "review.sent.json").get("files", [])
        files = [rv / n for n in names if (rv / n).exists()]
        if files:
            return files
        return sorted(p for p in rv.iterdir() if p.is_file() and not p.name.endswith(".json")) if rv.exists() else []

    def review_links(self, order_id: int) -> dict[str, str]:
        links = self._read_json(self.dir(order_id) / "review" / "review.sent.json").get("links", {})
        return {
            k: str(v) for k, v in links.items() if k in ("gslides", "canva", "view") and str(v).startswith("https://")
        }

    def set_review_link(self, order_id: int, key: str, url: str) -> None:
        manifest = self.dir(order_id) / "review" / "review.sent.json"
        data = self._read_json(manifest)
        data.setdefault("links", {})[key] = url
        self._write_json(manifest, data)

    def archive_review(self, order_id: int, kind: str, *, rejected: bool = False) -> Path:
        """review/ → sent_<kind>_<время>/ (или rejected_…), чтобы следующий этап начинался с чистой папки."""
        rv = self.dir(order_id) / "review"
        target = self.dir(order_id) / f"{'rejected' if rejected else 'sent'}_{kind}_{datetime.now():%m%d_%H%M%S}"
        if rv.exists():
            rv.rename(target)
        else:
            target.mkdir()
        return target

    def reset_attempt(self, order_id: int) -> None:
        rv = self.dir(order_id) / "review"
        for name in ("failed.json", "claim.json"):
            (rv / name).unlink(missing_ok=True)

    def latest_cover(self, order_id: int) -> Path | None:
        """Последняя отправленная клиенту обложка из конвейера (картинка)."""
        folders = sorted((self.root / str(order_id)).glob("sent_cover_*"))
        for folder in reversed(folders):
            images = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
            if images:
                return images[0]
        return None

    def delivered_files(self, order: Order) -> list[Path]:
        if not order.deliver_dir:
            return []
        d = self.root / order.deliver_dir
        return [d / n for n in (order.deliver_files or []) if (d / n).exists()]

    # --- сторож ---

    def stuck_reason(self, order: Order, now: datetime, stuck_hours: float) -> tuple[str, str] | None:
        """(ключ, описание) — что не так с заказом, или None, если всё идёт как надо."""
        if order.hidden or order.no_alert or order.status in (OrderStatus.DONE, OrderStatus.CANCELLED):
            return None
        if order.stage is None:
            return ("legacy", "заказ не попал в конвейер — задания (brief.json) нет, Claude его не видит")
        if order.stage not in TODO:
            return None
        kind = TODO[order.stage]
        rv = self.root / str(order.id) / "review"
        if (rv / "failed.json").exists():
            why = str(self._read_json(rv / "failed.json").get("reason", "")) or "причина не указана"
            return (f"{order.stage.value}|failed", f"Claude не смог сделать {KIND_ACC[kind]}: {why}")
        if (rv / "review.json").exists():
            return None
        since = as_utc(order.stage_at) if order.stage_at else None
        hours = (now - since).total_seconds() / 3600 if since else 0.0
        if hours >= stuck_hours:
            return (f"{order.stage.value}|late", f"{KIND_RU[kind]}: результата нет уже {hours:.0f} ч")
        return None

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any], indent: int | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
