import json
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.service import run_agent
from app.ai.graph import consume_pending_tool, resume_action_graph, start_action_graph
from app.api.schemas.chat import (
    ActionCreate,
    ChatResponse,
    ConfirmationBody,
    MessageCreate,
    SessionCreate,
    SessionResponse,
)
from app.db import get_db
from app.models import (
    ChatMessage,
    ChatSession,
    ToolExecution,
    ToolExecutionStatus,
)
from app.security import optional_identity
from app.tools.executor import execute_tool

router = APIRouter(prefix="/chat", tags=["chat"])


def get_session(db: Session, session_id: str, identity: dict | None = None) -> ChatSession:
    session = db.get(ChatSession, session_id)
    if not session or session.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(404, "Conversa expirada")
    if identity and identity["tenant"] != session.tenant_id:
        raise HTTPException(403, "Tenant inválido")
    if identity and identity.get("role") == "patient" and not session.patient_id:
        session.patient_id = identity["sub"]
    return session


def save_response(db: Session, session: ChatSession, result: dict) -> dict:
    result.pop("dialog_state", None)
    assistant = ChatMessage(
        tenant_id=session.tenant_id,
        session_id=session.id,
        role="assistant",
        content=result["answer"],
        citations=result.get("citations", []),
        metadata_json=jsonable_encoder(
            {
                key: result.get(key)
                for key in (
                    "intent",
                    "tool_result",
                    "auth_required",
                    "confirmation_request",
                    "tool_call",
                    "suggestions",
                    "resolved_request",
                )
            }
        ),
    )
    db.add(assistant)
    db.commit()
    db.refresh(assistant)
    return {
        "id": assistant.id,
        "answer": assistant.content,
        "intent": result["intent"],
        "confidence": result.get("confidence", 1.0),
        "citations": assistant.citations,
        "auth_required": result.get("auth_required", False),
        "confirmation_request": result.get("confirmation_request"),
        "tool_result": result.get("tool_result"),
        "tool_call": result.get("tool_call"),
        "suggestions": result.get("suggestions", []),
        "resolved_request": result.get("resolved_request"),
    }


@router.post("/sessions", status_code=201, response_model=SessionResponse)
def create_session(
    payload: SessionCreate,
    identity: dict | None = Depends(optional_identity),
    db: Session = Depends(get_db),
):
    if identity and identity["tenant"] != payload.tenant_id:
        raise HTTPException(403, "Tenant inválido")
    item = ChatSession(
        tenant_id=payload.tenant_id,
        patient_id=identity["sub"] if identity and identity.get("role") == "patient" else None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "tenant_id": item.tenant_id, "expires_at": item.expires_at}


@router.post("/sessions/{session_id}/messages", response_model=ChatResponse)
def post_message(
    session_id: str,
    payload: MessageCreate,
    identity: dict | None = Depends(optional_identity),
    db: Session = Depends(get_db),
):
    session = get_session(db, session_id, identity)
    previous = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(10)
    ).all()
    history = [{"role": item.role, "content": item.content} for item in reversed(previous)]
    db.add(
        ChatMessage(
            tenant_id=session.tenant_id, session_id=session.id, role="user", content=payload.content
        )
    )
    result = run_agent(db, session.tenant_id, identity, payload.content, history, None, session.id)
    return save_response(db, session, result)


@router.post("/sessions/{session_id}/messages/stream")
def stream_message(
    session_id: str,
    payload: MessageCreate,
    identity: dict | None = Depends(optional_identity),
    db: Session = Depends(get_db),
):
    session = get_session(db, session_id, identity)

    def events():
        normalized = payload.content.casefold()
        stage = (
            "Consultando a agenda…"
            if any(
                term in normalized for term in ("horário", "horario", "agenda", "sexta", "agendar")
            )
            else "Buscando informações aprovadas…"
        )
        yield f"event: status\ndata: {json.dumps({'label': stage}, ensure_ascii=False)}\n\n"
        previous = db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.desc())
            .limit(10)
        ).all()
        history = [{"role": item.role, "content": item.content} for item in reversed(previous)]
        db.add(
            ChatMessage(
                tenant_id=session.tenant_id,
                session_id=session.id,
                role="user",
                content=payload.content,
            )
        )
        result = run_agent(
            db, session.tenant_id, identity, payload.content, history, None, session.id
        )
        saved = save_response(db, session, result)
        words = saved["answer"].split(" ")
        for index, word in enumerate(words):
            chunk = word if index == len(words) - 1 else f"{word} "
            yield f"event: delta\ndata: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
        yield f"event: final\ndata: {json.dumps(jsonable_encoder(saved), ensure_ascii=False)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/sessions/{session_id}/resume", response_model=ChatResponse)
def resume(
    session_id: str,
    identity: dict | None = Depends(optional_identity),
    db: Session = Depends(get_db),
):
    session = get_session(db, session_id, identity)
    if not identity or identity.get("role") != "patient":
        raise HTTPException(401, "Identificação necessária")
    pending = consume_pending_tool(session.id)
    if not pending:
        raise HTTPException(409, "Não há operação pendente")
    result = execute_tool(
        db, session.tenant_id, identity, pending["name"], pending.get("arguments", {})
    )
    return save_response(db, session, result)


@router.post("/sessions/{session_id}/actions", response_model=ChatResponse)
def request_action(
    session_id: str,
    payload: ActionCreate,
    identity: dict | None = Depends(optional_identity),
    db: Session = Depends(get_db),
):
    session = get_session(db, session_id, identity)
    if payload.tool not in {"create_appointment", "cancel_appointment"}:
        raise HTTPException(422, "Ação não permitida")
    confirmation_id = secrets.token_urlsafe(18)
    result = start_action_graph(
        db,
        session.tenant_id,
        identity,
        payload.tool,
        payload.arguments,
        session.id,
        confirmation_id,
    )
    confirmation = result.get("confirmation_request")
    if confirmation and identity and identity.get("role") == "patient":
        db.add(
            ToolExecution(
                tenant_id=session.tenant_id,
                session_id=session.id,
                actor_id=identity["sub"],
                confirmation_id=confirmation_id,
                tool_name=payload.tool,
                arguments_json=jsonable_encoder(payload.arguments),
            )
        )
        db.commit()
    return save_response(db, session, result)


@router.post(
    "/sessions/{session_id}/confirmations/{confirmation_id}",
    response_model=ChatResponse,
)
def confirm_action(
    session_id: str,
    confirmation_id: str,
    payload: ConfirmationBody,
    identity: dict | None = Depends(optional_identity),
    db: Session = Depends(get_db),
):
    session = get_session(db, session_id, identity)
    if not identity or identity.get("role") != "patient":
        raise HTTPException(401, "Identificação necessária")
    execution = db.scalar(
        select(ToolExecution)
        .where(
            ToolExecution.tenant_id == session.tenant_id,
            ToolExecution.session_id == session.id,
            ToolExecution.confirmation_id == confirmation_id,
        )
        .with_for_update()
    )
    if not execution or execution.actor_id != identity["sub"]:
        raise HTTPException(404, "Confirmação expirada")
    if execution.status == ToolExecutionStatus.succeeded:
        return save_response(db, session, dict(execution.result_json))
    if execution.status in {ToolExecutionStatus.running, ToolExecutionStatus.failed}:
        raise HTTPException(
            409,
            "Esta confirmação já está em processamento ou falhou; solicite uma nova confirmação.",
        )
    execution.status = ToolExecutionStatus.running
    db.commit()
    try:
        result = resume_action_graph(
            db,
            session.tenant_id,
            identity,
            session.id,
            confirmation_id,
            payload.accepted,
        )
    except ValueError as exc:
        execution.status = ToolExecutionStatus.failed
        execution.error_code = "confirmation_expired"
        db.commit()
        raise HTTPException(404, "Confirmação expirada") from exc
    except Exception as exc:
        execution.status = ToolExecutionStatus.failed
        execution.error_code = type(exc).__name__[:120]
        db.commit()
        raise
    execution.status = ToolExecutionStatus.succeeded
    execution.result_json = jsonable_encoder(result)
    db.commit()
    return save_response(db, session, result)
