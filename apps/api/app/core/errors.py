from __future__ import annotations


class ApplicationError(Exception):
    """Base class for expected, user-safe application failures."""

    code = "application_error"


class RequestValidationError(ApplicationError):
    code = "validation_error"


class AuthenticationRequiredError(ApplicationError):
    code = "authentication_required"


class ConfirmationRequiredError(ApplicationError):
    code = "confirmation_required"


class ResourceNotFoundError(ApplicationError):
    code = "not_found"


class ResourceConflictError(ApplicationError):
    code = "conflict"


class ProviderUnavailableError(ApplicationError):
    code = "provider_unavailable"


class RetrievalInsufficientError(ApplicationError):
    code = "retrieval_insufficient"


class UnsafeRequestError(ApplicationError):
    code = "unsafe_request"
