from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.shared.application import (
    ApplicationError,
    AuthenticationRequiredError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.shared.infrastructure.observability import correlation_id

STATUS_BY_ERROR = {
    AuthenticationRequiredError: 401,
    ForbiddenError: 403,
    NotFoundError: 404,
    ConflictError: 409,
    ValidationError: 422,
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def request_validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
        fields = [
            {"field": ".".join(str(value) for value in issue["loc"]), "message": issue["msg"]}
            for issue in error.errors()
        ]
        return JSONResponse(
            {
                "code": "validation_error",
                "message": "Revise os campos informados.",
                "field_errors": fields,
                "correlation_id": correlation_id(),
            },
            status_code=422,
        )

    @app.exception_handler(ApplicationError)
    async def application_error(_: Request, error: ApplicationError) -> JSONResponse:
        status = next(
            (value for kind, value in STATUS_BY_ERROR.items() if isinstance(error, kind)), 400
        )
        return JSONResponse(
            {
                "code": error.error_code,
                "message": error.message,
                "field_errors": error.field_errors,
                "correlation_id": correlation_id(),
            },
            status_code=status,
        )
