"""Контракт с сессией Claude: формат папки orders/<id>/ должен совпадать с прежним ботом."""

import json
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from conftest import FakeClock
from slidelab.core.enums import Design, Stage
from slidelab.core.models import Order
from slidelab.core.services.orders import OrderService
from slidelab.core.services.pipeline import Pipeline, formats_of
from test_orders import draft

BRIEF_KEYS = {
    "id",
    "client_lang",
    "topic",
    "slides",
    "deadline",
    "presentation_lang",
    "design",
    "template_link",
    "need_text",
    "need_notes",
    "need_humor",
    "comment",
    "sources",
    "client_will_send_files",
    "client",
    "created",
}


async def new_order(session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any], **kw: Any) -> Order:
    user = await make_user()
    return await OrderService(session, clock).create(user.id, draft(**kw))


async def test_brief_and_status_match_old_format(
    tmp_path: Path, session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]
) -> None:
    order = await new_order(
        session, clock, make_user, design=Design.OWN, template_url="https://canva.com/t", need_humor=True
    )
    pipe = Pipeline(tmp_path)
    pipe.write_brief(order, "Аня @anya", style_name=None)

    brief = json.loads((tmp_path / str(order.id) / "brief.json").read_text(encoding="utf-8"))
    assert set(brief) == BRIEF_KEYS
    assert brief["slides"] == "11–20"
    assert brief["design"] == "свой шаблон клиента"
    assert brief["template_link"] == "https://canva.com/t"
    assert brief["need_humor"] is True

    status = json.loads((tmp_path / str(order.id) / "status.json").read_text(encoding="utf-8"))
    assert status == {"stage": "cover_todo", "paid": False, "status": "new"}


def put_review(root: Path, order_id: int, kind: str, files: list[str], **extra: Any) -> None:
    rv = root / str(order_id) / "review"
    rv.mkdir(parents=True, exist_ok=True)
    for name in files:
        (rv / name).write_bytes(b"x")
    (rv / "review.json").write_text(json.dumps({"kind": kind, "files": files, **extra}), encoding="utf-8")


async def test_review_detected_only_for_todo_stage(
    tmp_path: Path, session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]
) -> None:
    order = await new_order(session, clock, make_user)
    pipe = Pipeline(tmp_path)
    put_review(tmp_path, order.id, "cover", ["cover.png"], message="Сделал в стиле ар-деко")

    ready = pipe.ready_reviews({order.id: order})
    assert [(r.order_id, r.kind, [f.name for f in r.files], r.message) for r in ready] == [
        (order.id, "cover", ["cover.png"], "Сделал в стиле ар-деко")
    ]

    pipe.mark_review_sent(order.id)
    order.stage = Stage.COVER_REVIEW
    assert pipe.ready_reviews({order.id: order}) == []
    assert [f.name for f in pipe.review_files(order.id)] == ["cover.png"]

    folder = pipe.archive_review(order.id, "cover")
    assert folder.name.startswith("sent_cover_") and (folder / "cover.png").exists()
    assert pipe.latest_cover(order.id) == folder / "cover.png"
    assert not (tmp_path / str(order.id) / "review").exists()


async def test_review_links_survive_until_archive(
    tmp_path: Path, session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]
) -> None:
    order = await new_order(session, clock, make_user)
    pipe = Pipeline(tmp_path)
    put_review(tmp_path, order.id, "deck", ["deck.pptx"], links={"gslides": "https://docs.google.com/x", "bad": "x"})
    pipe.mark_review_sent(order.id)
    pipe.set_review_link(order.id, "view", "https://canva.com/d/view")
    assert pipe.review_links(order.id) == {
        "gslides": "https://docs.google.com/x",
        "view": "https://canva.com/d/view",
    }


async def test_stuck_reasons(
    tmp_path: Path, session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]
) -> None:
    order = await new_order(session, clock, make_user)
    pipe = Pipeline(tmp_path)
    now = clock()
    assert pipe.stuck_reason(order, now, stuck_hours=3) is None

    late = pipe.stuck_reason(order, now + timedelta(hours=4), stuck_hours=3)
    assert late is not None and late[0] == "cover_todo|late"

    rv = tmp_path / str(order.id) / "review"
    rv.mkdir(parents=True)
    (rv / "failed.json").write_text('{"reason": "нет фото по теме"}', encoding="utf-8")
    failed = pipe.stuck_reason(order, now, stuck_hours=3)
    assert failed == ("cover_todo|failed", "Claude не смог сделать обложку: нет фото по теме")

    pipe.reset_attempt(order.id)
    order.stage = None
    legacy = pipe.stuck_reason(order, now, stuck_hours=3)
    assert legacy is not None and legacy[0] == "legacy"

    order.no_alert = True
    assert pipe.stuck_reason(order, now, stuck_hours=3) is None


def test_formats() -> None:
    files = [Path("a.pdf"), Path("b.PPTX"), Path("c.jpg"), Path("notes.docx"), Path("x.key")]
    assert formats_of(files) == ["pptx", "pdf", "png", "docx", "key"]
