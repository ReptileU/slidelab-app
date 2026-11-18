"""Доступ сессии Claude («делать заказы») к папке конвейера — в облаке, где папки на компьютере нет.

Тот же контракт, что с папкой orders/<номер>/ на компьютере (см. core/services/pipeline.py), только через HTTP:
    GET  /pipeline/orders                       — заказы: status.json и что лежит в review/
    GET  /pipeline/orders/{id}                  — список файлов заказа
    GET  /pipeline/orders/{id}/file?path=…      — скачать файл (brief.json, notes.md, files/…, edits/…, work.json)
    PUT  /pipeline/orders/{id}/file?path=…      — положить файл: только work.json и review/… (claim, review, failed)

Ключ — заголовок X-Pipeline-Key (PIPELINE_KEY в настройках сервера). Без ключа маршрутов нет.
"""

import hmac
import json
from pathlib import Path, PurePosixPath
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse

from slidelab.api.deps import SettingsDep
from slidelab.config import Settings

MAX_UPLOAD = 25 * 1024 * 1024
WRITABLE = ("work.json", "review/")


def _check_key(settings: SettingsDep, x_pipeline_key: Annotated[str | None, Header()] = None) -> Settings:
    key = settings.pipeline_key.get_secret_value() if settings.pipeline_key else ""
    if not key or not x_pipeline_key or not hmac.compare_digest(x_pipeline_key, key):
        raise HTTPException(status_code=401, detail="Нужен ключ конвейера")
    return settings


KeyDep = Annotated[Settings, Depends(_check_key)]
router = APIRouter(prefix="/pipeline", tags=["pipeline"], include_in_schema=False)


def _order_dir(settings: Settings, order_id: int) -> Path:
    d = settings.work_dir / str(order_id)
    if not d.is_dir():
        raise HTTPException(status_code=404, detail="Заказа нет в конвейере")
    return d


def _inside(base: Path, rel: str) -> Path:
    parts = PurePosixPath(rel.replace("\\", "/")).parts
    if not parts or any(p in ("..", "") or p.startswith("/") for p in parts):
        raise HTTPException(status_code=400, detail="Плохой путь")
    return base.joinpath(*parts)


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@router.get("/orders")
async def orders(settings: KeyDep) -> list[dict[str, Any]]:
    out = []
    root = settings.work_dir
    for d in (
        sorted((p for p in root.iterdir() if p.is_dir() and p.name.isdigit()), key=lambda p: int(p.name))
        if root.is_dir()
        else []
    ):
        review = d / "review"
        out.append(
            {
                "id": int(d.name),
                "status": _json(d / "status.json"),
                "review": sorted(f.name for f in review.iterdir() if f.is_file()) if review.is_dir() else [],
                "claim": _json(review / "claim.json"),
            }
        )
    return out


@router.get("/orders/{order_id}")
async def order_files(order_id: int, settings: KeyDep) -> list[dict[str, Any]]:
    d = _order_dir(settings, order_id)
    return [
        {"path": f.relative_to(d).as_posix(), "size": f.stat().st_size} for f in sorted(d.rglob("*")) if f.is_file()
    ]


@router.get("/orders/{order_id}/file", response_model=None)
async def get_file(order_id: int, path: str, settings: KeyDep) -> FileResponse:
    target = _inside(_order_dir(settings, order_id), path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Файла нет")
    return FileResponse(target, filename=target.name)


@router.put("/orders/{order_id}/file")
async def put_file(order_id: int, path: str, request: Request, settings: KeyDep) -> dict[str, Any]:
    rel = path.replace("\\", "/")
    if not (rel == "work.json" or rel.startswith("review/")):
        raise HTTPException(status_code=403, detail="Записывать можно только work.json и review/…")
    target = _inside(_order_dir(settings, order_id), rel)
    body = await request.body()
    if len(body) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="Слишком большой файл — дайте ссылку в review.json (urls)")
    if target.suffix == ".json":
        try:
            json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise HTTPException(status_code=422, detail="Это не JSON") from None
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".part")
    tmp.write_bytes(body)
    tmp.replace(target)  # бот не увидит недописанный review.json
    return {"ok": True, "path": rel, "size": len(body)}
