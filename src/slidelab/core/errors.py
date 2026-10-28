class DomainError(Exception):
    """Ошибка бизнес-правила. `code` уходит клиенту, текст — для логов и менеджера."""

    code = "domain_error"


class NotFoundError(DomainError):
    code = "not_found"


class ForbiddenError(DomainError):
    code = "forbidden"


class InvalidTransitionError(DomainError):
    code = "invalid_transition"


class InsufficientPackageError(DomainError):
    code = "insufficient_package"


class ParallelLimitError(DomainError):
    code = "parallel_limit"


class PaymentRequiredError(DomainError):
    code = "payment_required"
