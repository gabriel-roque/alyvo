import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.dependencies import current_actor, optional_actor
from app.api.schemas.chat import (
    ActionCreate,
    ChatResponse,
    ConfirmationBody,
    MessageCreate,
    SessionResponse,
)
from app.modules.conversations.application import ConversationService
from app.modules.identity.domain import Actor
from app.shared.application import ApplicationError

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/sessions", response_model=SessionResponse, status_code=201)
def create_session(actor: Actor | None = Depends(optional_actor)):
    return ConversationService().create(actor)


@router.post("/sessions/{session_id}/messages", response_model=ChatResponse)
def post_message(
    session_id: str, payload: MessageCreate, actor: Actor | None = Depends(optional_actor)
):
    return ConversationService().message(session_id, payload.content, actor)


@router.post(
    "/sessions/{session_id}/messages/stream",
    response_class=StreamingResponse,
    response_model=None,
    responses={
        200: {
            "description": "Eventos SSE status, delta, final ou error",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
def stream_message(
    session_id: str, payload: MessageCreate, actor: Actor | None = Depends(optional_actor)
):
    def events():
        yield (
            "event: status\ndata: "
            + json.dumps({"label": "Entendendo seu pedido…"}, ensure_ascii=False)
            + "\n\n"
        )
        try:
            result = ConversationService().message(session_id, payload.content, actor)
            yield (
                "event: delta\ndata: "
                + json.dumps({"text": result["answer"]}, ensure_ascii=False)
                + "\n\n"
            )
            yield (
                "event: final\ndata: "
                + json.dumps(result, ensure_ascii=False, default=str)
                + "\n\n"
            )
        except ApplicationError as error:
            yield (
                "event: error\ndata: "
                + json.dumps(
                    {"code": error.error_code, "message": error.message}, ensure_ascii=False
                )
                + "\n\n"
            )

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/sessions/{session_id}/resume", response_model=ChatResponse)
def resume(session_id: str, actor: Actor | None = Depends(optional_actor)):
    return ConversationService().resume(session_id, actor)


@router.post("/sessions/{session_id}/actions", response_model=ChatResponse)
def action(session_id: str, payload: ActionCreate, actor: Actor | None = Depends(optional_actor)):
    return ConversationService().action(
        session_id,
        payload.tool,
        payload.arguments.model_dump(mode="json"),
        actor,
    )


@router.post("/sessions/{session_id}/confirmations/{confirmation_id}", response_model=ChatResponse)
def confirm(
    session_id: str,
    confirmation_id: str,
    body: ConfirmationBody,
    actor: Actor = Depends(current_actor),
):
    return ConversationService().confirm(session_id, confirmation_id, body.accepted, actor)
