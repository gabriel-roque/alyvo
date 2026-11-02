import json
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.graph import consume_pending_tool, resume_action_graph, start_action_graph
from app.ai.workflow import execute_tool, run_workflow
from app.db import get_db
from app.models import ChatMessage, ChatSession
from app.security import optional_identity

router = APIRouter(prefix="/chat", tags=["chat"])


class SessionCreate(BaseModel):
    tenant_id: str = "clinic-alyvo"


class MessageCreate(BaseModel):
    content: str


class ActionCreate(BaseModel):
    tool: str
    arguments: dict


class ConfirmationBody(BaseModel):
    accepted: bool


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
        metadata_json=jsonable_encoder({key: result.get(key) for key in ("intent", "tool_result", "auth_required", "confirmation_request", "tool_call", "suggestions", "resolved_request")}),
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


@router.post("/sessions", status_code=201)
def create_session(payload: SessionCreate, identity: dict | None = Depends(optional_identity), db: Session = Depends(get_db)):
    if identity and identity["tenant"] != payload.tenant_id:
        raise HTTPException(403, "Tenant inválido")
    item = ChatSession(tenant_id=payload.tenant_id, patient_id=identity["sub"] if identity and identity.get("role") == "patient" else None)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "tenant_id": item.tenant_id, "expires_at": item.expires_at}


@router.post("/sessions/{session_id}/messages")
def post_message(session_id: str, payload: MessageCreate, identity: dict | None = Depends(optional_identity), db: Session = Depends(get_db)):
    session = get_session(db, session_id, identity)
    previous = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(10)
    ).all()
    history = [{"role": item.role, "content": item.content} for item in reversed(previous)]
    db.add(ChatMessage(tenant_id=session.tenant_id, session_id=session.id, role="user", content=payload.content))
    result = run_workflow(
        db, session.tenant_id, identity, payload.content, history, None, session.id
    )
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
        stage = "Consultando a agenda…" if any(term in normalized for term in ("horário", "horario", "agenda", "sexta", "agendar")) else "Buscando informações aprovadas…"
        yield f"event: status\ndata: {json.dumps({'label': stage}, ensure_ascii=False)}\n\n"
        previous = db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.desc())
            .limit(10)
        ).all()
        history = [{"role": item.role, "content": item.content} for item in reversed(previous)]
        db.add(ChatMessage(tenant_id=session.tenant_id, session_id=session.id, role="user", content=payload.content))
        result = run_workflow(
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


@router.post("/sessions/{session_id}/resume")
def resume(session_id: str, identity: dict | None = Depends(optional_identity), db: Session = Depends(get_db)):
    session = get_session(db, session_id, identity)
    if not identity or identity.get("role") != "patient":
        raise HTTPException(401, "Identificação necessária")
    pending = consume_pending_tool(session.id)
    if not pending:
        raise HTTPException(409, "Não há operação pendente")
    result = execute_tool(db, session.tenant_id, identity, pending["name"], pending.get("arguments", {}))
    return save_response(db, session, result)


@router.post("/sessions/{session_id}/actions")
def request_action(session_id: str, payload: ActionCreate, identity: dict | None = Depends(optional_identity), db: Session = Depends(get_db)):
    session = get_session(db, session_id, identity)
    if payload.tool not in {"create_appointment", "cancel_appointment"}:
        raise HTTPException(422, "Ação não permitida")
    result = start_action_graph(
        db,
        session.tenant_id,
        identity,
        payload.tool,
        payload.arguments,
        session.id,
        secrets.token_urlsafe(18),
    )
    return save_response(db, session, result)


@router.post("/sessions/{session_id}/confirmations/{confirmation_id}")
def confirm_action(session_id: str, confirmation_id: str, payload: ConfirmationBody, identity: dict | None = Depends(optional_identity), db: Session = Depends(get_db)):
    session = get_session(db, session_id, identity)
    if not identity or identity.get("role") != "patient":
        raise HTTPException(401, "Identificação necessária")
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
        raise HTTPException(404, "Confirmação expirada") from exc
    return save_response(db, session, result)
