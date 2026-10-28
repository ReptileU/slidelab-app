from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from slidelab.core.enums import Deadline, Design, Lang, SlideTier
from slidelab.core.models.order import (
    COMMENT_MAX,
    CONTACT_MAX,
    REVISION_MAX,
    SOURCES_MAX,
    TEMPLATE_URL_MAX,
    TOPIC_MAX,
)
from slidelab.core.services.pricing import QuoteRequest

Topic = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=TOPIC_MAX)]
TemplateUrl = Annotated[str, StringConstraints(strip_whitespace=True, max_length=TEMPLATE_URL_MAX)]
Contact = Annotated[str, StringConstraints(strip_whitespace=True, max_length=CONTACT_MAX)]
Comment = Annotated[str, StringConstraints(strip_whitespace=True, max_length=COMMENT_MAX)]
Sources = Annotated[str, StringConstraints(strip_whitespace=True, max_length=SOURCES_MAX)]
RevisionText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=REVISION_MAX)]


class OrderDraft(BaseModel):
    """Заявка из Mini App или из диалога в боте — общая для обоих входов."""

    model_config = ConfigDict(frozen=True)

    topic: Topic
    slides: SlideTier
    deadline: Deadline
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
