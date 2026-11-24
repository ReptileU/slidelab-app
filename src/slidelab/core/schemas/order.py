from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from slidelab.core.enums import Deadline, Design, Lang, SlideTier
from slidelab.core.models.order import (
    COMMENT_MAX,
    CONTACT_MAX,
    REVISION_MAX,
    SOURCES_MAX,
    TEMPLATE_URL_MAX,
    TITLE_GROUP_MAX,
    TITLE_NAME_MAX,
    TOPIC_MAX,
)
from slidelab.core.services.pricing import QuoteRequest

Topic = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=TOPIC_MAX)]
TemplateUrl = Annotated[str, StringConstraints(strip_whitespace=True, max_length=TEMPLATE_URL_MAX)]
Contact = Annotated[str, StringConstraints(strip_whitespace=True, max_length=CONTACT_MAX)]
Comment = Annotated[str, StringConstraints(strip_whitespace=True, max_length=COMMENT_MAX)]
Sources = Annotated[str, StringConstraints(strip_whitespace=True, max_length=SOURCES_MAX)]
TitleName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=TITLE_NAME_MAX)]
TitleGroup = Annotated[str, StringConstraints(strip_whitespace=True, max_length=TITLE_GROUP_MAX)]
RevisionText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=REVISION_MAX)]


class OrderDraft(BaseModel):
    """Заявка из Mini App или из диалога в боте — общая для обоих входов."""

    model_config = ConfigDict(frozen=True)

    topic: Topic
    slides: SlideTier
    deadline: Deadline
    due_at: datetime | None = None  # к какому сроку нужна — только для «Обычно»
    skip_cover: bool = False  # «Сразу всю презентацию» — без бесплатной обложки, оплата сразу
    pres_lang: Lang
    design: Design
    style_key: str | None = None
    template_url: TemplateUrl | None = None
    extra_text: bool = False
    extra_notes: bool = False
    contact: Contact | None = None
    comment: Comment | None = None
    sources: Sources | None = None
    has_source_files: bool = False
    need_humor: bool = False  # «С юмором»: мемы и смешные примеры по теме
    # Плашка на титульном слайде (необязательно): «Выполнил(а)», «Группа», «Принял(а)»
    title_author: TitleName | None = None
    title_group: TitleGroup | None = None
    title_teacher: TitleName | None = None

    @model_validator(mode="after")
    def _template_only_for_own(self) -> "OrderDraft":
        if self.design is not Design.OWN and self.template_url:
            raise ValueError("template_url задаётся только для дизайна по шаблону клиента")
        return self

    def quote_request(self) -> QuoteRequest:
        return QuoteRequest(
            slides=self.slides,
            deadline=self.deadline,
            extra_text=self.extra_text,
            extra_notes=self.extra_notes,
        )


class QuickCoverDraft(BaseModel):
    """Короткая заявка «бесплатная обложка»: тема, стиль, язык и (по желанию) имя на титульном слайде.

    Объём, срок, допы и оплата — потом, если обложка понравится (OrderService.complete_quick)."""

    model_config = ConfigDict(frozen=True)

    topic: Topic
    pres_lang: Lang
    design: Design = Design.OURS  # под тему / наш стиль (style_key) / шаблон клиента (template_url)
    style_key: str | None = None
    template_url: TemplateUrl | None = None
    title_author: TitleName | None = None

    def as_draft(self) -> OrderDraft:
        # объём и срок — заглушки до дооформления: обложке они не нужны, цену по ним не берём
        return OrderDraft(
            topic=self.topic,
            slides=SlideTier.S10,
            deadline=Deadline.NORMAL,
            pres_lang=self.pres_lang,
            design=self.design,
            style_key=(self.style_key or None) if self.design is Design.OURS else None,
            template_url=(self.template_url or None) if self.design is Design.OWN else None,
            title_author=self.title_author or None,
        )
