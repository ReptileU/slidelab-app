import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from slidelab.core.filemirror import MAX_FILE, FileMirror, Root


async def test_files_survive_a_wiped_disk(session: AsyncSession, tmp_path: Path) -> None:
    sm = async_sessionmaker(session.bind, expire_on_commit=False)
    orders, data = tmp_path / "a" / "orders", tmp_path / "a" / "data"
    (orders / "12" / "review").mkdir(parents=True)
    (orders / "12" / "brief.json").write_text('{"topic": "Экономика"}', encoding="utf-8")
    (orders / "12" / "review" / "review.json").write_text("{}", encoding="utf-8")
    data.mkdir()
    (data / "widgets.json").write_text("[]", encoding="utf-8")
    (orders / "12" / "huge.pptx").write_bytes(b"0" * (MAX_FILE + 1))  # огромный — не в базу

    mirror = FileMirror(sm, [Root("orders", orders), Root("data", data)])
    assert await mirror.sync() == (3, 0)
    assert await mirror.sync() == (0, 0)  # ничего не менялось

    # Конвейер перенёс результат в архив — в базе тоже
    (orders / "12" / "sent_cover_1").mkdir()
    (orders / "12" / "review" / "review.json").rename(orders / "12" / "sent_cover_1" / "review.json")
    assert await mirror.sync() == (1, 1)

    # Новый сервер: пустой диск — всё возвращается из базы
    orders2, data2 = tmp_path / "b" / "orders", tmp_path / "b" / "data"
    fresh = FileMirror(sm, [Root("orders", orders2), Root("data", data2)])
    assert await fresh.restore() == 3
    assert (orders2 / "12" / "brief.json").read_text(encoding="utf-8") == '{"topic": "Экономика"}'
    assert (orders2 / "12" / "sent_cover_1" / "review.json").exists()
    assert not (orders2 / "12" / "review" / "review.json").exists()
    assert (data2 / "widgets.json").exists()
    assert await fresh.sync() == (0, 0)  # восстановленное заново не пишется
    # файл из новой выкладки свежее копии в базе — restore его не перезаписывает
    (data2 / "widgets.json").write_text("[1]", encoding="utf-8")
    assert await FileMirror(sm, [Root("data", data2)]).restore() == 0
    assert (data2 / "widgets.json").read_text(encoding="utf-8") == "[1]"
    os.utime(data2 / "widgets.json", (1, 1))
    assert await fresh.sync() == (1, 0)  # изменённый — снова в базу
