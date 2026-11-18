from datetime import datetime

from sqlalchemy import LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from slidelab.core.models.base import Base, utcnow


class StoredFile(Base):
    """Копия файла с диска в базе — для облака, где диск стирается при каждом перезапуске.

    path — относительный путь с корнем: "orders/12/brief.json", "data/widgets.json".
    """

    __tablename__ = "stored_files"

    path: Mapped[str] = mapped_column(String(512), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    size: Mapped[int]
    mtime: Mapped[float]  # время изменения файла на диске (секунды)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)
