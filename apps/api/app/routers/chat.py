import json
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.workflow import execute_tool, run_workflow
from app.db import get_db
from app.models import ChatMessage, ChatSession
from app.routers.operations import (
    AppointmentCreate,
    cancel_patient_appointment,
    create_patient_appointment,
)
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
    state = dict(session.state or {})
    if result.get("dialog_state"):
        state["dialog"] = result.pop("dialog_state")
    if result.get("pending_tool"):
        state["pending_tool"] = result["pending_tool"]
    confirmation = result.get("confirmation_request")
    if confirmation:
        confirmation_id = secrets.token_urlsafe(18)
        state["confirmation"] = {"id": confirmation_id, **confirmation}
        result["confirmation_request"] = {
            "id": confirmation_id,
            "tool": confirmation["tool"],
            "summary": confirmation.get("summary", "Confirme para concluir esta operação."),
        }
    session.state = state
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
    result = run_workflow(db, session.tenant_id, identity, payload.content, history, session.state)
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
        result = run_workflow(db, session.tenant_id, identity, payload.content, history, session.state)
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
    pending = dict(session.state or {}).get("pending_tool")
    if not pending:
        raise HTTPException(409, "Não há operação pendente")
    if not identity or identity.get("role") != "patient":
        raise HTTPException(401, "Identificação necessária")
    state = dict(session.state or {})
    state.pop("pending_tool", None)
    session.state = state
    result = execute_tool(db, session.tenant_id, identity, pending["name"], pending.get("arguments", {}))
    return save_response(db, session, result)


@router.post("/sessions/{session_id}/actions")
def request_action(session_id: str, payload: ActionCreate, identity: dict | None = Depends(optional_identity), db: Session = Depends(get_db)):
    session = get_session(db, session_id, identity)
    if payload.tool not in {"create_appointment", "cancel_appointment"}:
        raise HTTPException(422, "Ação não permitida")
    result = execute_tool(db, session.tenant_id, identity, payload.tool, payload.arguments)
    return save_response(db, session, result)


@router.post("/sessions/{session_id}/confirmations/{confirmation_id}")
def confirm_action(session_id: str, confirmation_id: str, payload: ConfirmationBody, identity: dict | None = Depends(optional_identity), db: Session = Depends(get_db)):
    session = get_session(db, session_id, identity)
    confirmation = dict(session.state or {}).get("confirmation")
    if not confirmation or confirmation.get("id") != confirmation_id:
        raise HTTPException(404, "Confirmação expirada")
    state = dict(session.state or {})
    state.pop("confirmation", None)
    session.state = state
    if not payload.accepted:
        answer = (
            "O cancelamento foi interrompido. Sua consulta continua confirmada."
            if confirmation["tool"] == "cancel_appointment"
            else "O agendamento não foi concluído."
        )
        return save_response(db, session, {"answer": answer, "intent": confirmation["tool"], "confidence": 1.0, "citations": [], "tool_result": None, "tool_call": {"name": confirmation["tool"]}})
    if not identity or identity.get("role") != "patient":
        raise HTTPException(401, "Identificação necessária")
    if confirmation["tool"] == "create_appointment":
        args = confirmation["arguments"]
        result = create_patient_appointment(AppointmentCreate(doctor_id=args["doctor_id"], starts_at=args["starts_at"], reason=args.get("reason", "Consulta"), confirmed=True), identity, db)
        tool_result = {"type": "appointment_created", "appointment": result}
        answer = "Consulta agendada com sucesso."
    else:
        result = cancel_patient_appointment(confirmation["arguments"]["appointment_id"], identity, db)
        tool_result = {"type": "appointment_cancelled", "appointment": result}
        answer = "Consulta cancelada com sucesso."
    return save_response(db, session, {"answer": answer, "intent": confirmation["tool"], "confidence": 1.0, "citations": [], "tool_result": tool_result, "tool_call": {"name": confirmation["tool"]}})
