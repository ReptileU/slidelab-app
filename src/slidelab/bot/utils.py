from dataclasses import dataclass

from aiogram.types import Message


@dataclass(frozen=True, slots=True)
class FileRef:
    file_id: str
    name: str  # имя для папки заказа: исходное или photo_<id>.jpg, video_<id>.mp4…
    mime: str | None


def file_of(message: Message) -> FileRef | None:
    """Файл из сообщения: документ, фото (самое крупное), видео, аудио, голос, кружок, гифка."""
    mid = message.message_id
    if message.document:
        d = message.document
        return FileRef(d.file_id, d.file_name or f"file_{mid}", d.mime_type)
    if message.photo:
        return FileRef(message.photo[-1].file_id, f"photo_{mid}.jpg", "image/jpeg")
    for kind, ext in (
        ("video", "mp4"),
        ("audio", "mp3"),
        ("voice", "ogg"),
        ("video_note", "mp4"),
        ("animation", "mp4"),
    ):
        media = getattr(message, kind)
        if media is not None:
            name = getattr(media, "file_name", None) or f"{kind}_{mid}.{ext}"
            return FileRef(media.file_id, name, getattr(media, "mime_type", None))
    return None
