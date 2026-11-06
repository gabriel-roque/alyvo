from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.modules.identity.domain import Actor, UserRole
from app.modules.identity.infrastructure.security import actor_from_token
from app.shared.application import AuthenticationRequiredError, ForbiddenError

bearer = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    description="Access token sintético emitido pelos fluxos de autenticação Alyvo.",
)


def optional_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Actor | None:
    if not credentials:
        return None
    if credentials.scheme.casefold() != "bearer":
        raise AuthenticationRequiredError("Autenticação inválida")
    return actor_from_token(credentials.credentials)


def current_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Actor:
    actor = optional_actor(credentials)
    if actor is None:
        raise AuthenticationRequiredError("Autenticação necessária")
    return actor


def staff_actor(actor: Actor = Depends(current_actor)) -> Actor:
    if not actor.is_staff:
        raise ForbiddenError("Acesso restrito à equipe")
    return actor


def admin_actor(actor: Actor = Depends(current_actor)) -> Actor:
    if actor.role != UserRole.ADMIN:
        raise ForbiddenError("Acesso restrito à administração")
    return actor
