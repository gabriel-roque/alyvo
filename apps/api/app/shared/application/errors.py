from __future__ import annotations

from typing import ClassVar


class ApplicationError(Exception):
    code: ClassVar[str] = "application_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        field_errors: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = code or type(self).code
        self.field_errors = field_errors or []

    def __str__(self) -> str:
        return self.message


class ValidationError(ApplicationError):
    code = "validation_error"


class AuthenticationRequiredError(ApplicationError):
    code = "authentication_required"


class ForbiddenError(ApplicationError):
    code = "forbidden"


class NotFoundError(ApplicationError):
    code = "not_found"


class ConflictError(ApplicationError):
    code = "conflict"


class ProviderUnavailableError(ApplicationError):
    code = "provider_unavailable"
