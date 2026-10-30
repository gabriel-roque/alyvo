import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.workflow import run_workflow
from app.db import get_db
from app.models import ChatMessage, ChatSession, Ticket
from app.routers.operations import AppointmentCreate, cancel_appointment, create_appointment
from app.security import optional_identity

router = APIRouter(prefix="/chat", tags=["chat"])


class SessionCreate(BaseModel):
    tenant_id: str = "clinic-alyvo"


class MessageCreate(BaseModel):
    content: str
    confirm_ticket: bool = False
    confirmed: bool = False
    action: dict | None = None


class Citation(BaseModel):
    title: str
    source: str
    excerpt: str


class ChatResponse(BaseModel):
    id: str
    answer: str
    intent: str
    confidence: float
    citations: list[Citation]
    form_request: dict | None = None
    confirmation_request: dict | None = None
    ticket_id: str | None = None
    tool_result: dict | None = None
    graph_trace: list[str]


@router.post("/sessions", status_code=201)
def create_session(
    payload: SessionCreate,
    identity: dict | None = Depends(optional_identity),
    db: Session = Depends(get_db),
):
    if identity and identity["tenant"] != payload.tenant_id:
        raise HTTPException(403, "Tenant inválido")
    item = ChatSession(tenant_id=payload.tenant_id, patient_id=identity["sub"] if identity else None)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "tenant_id": item.tenant_id, "authenticated": bool(item.patient_id)}


@router.post("/sessions/{session_id}/messages", response_model=ChatResponse)
def post_message(
    session_id: str,
    payload: MessageCreate,
    identity: dict | None = Depends(optional_identity),
    db: Session = Depends(get_db),
):
    session = db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(404, "Conversa não encontrada")
    if identity and identity["tenant"] != session.tenant_id:
        raise HTTPException(403, "Tenant inválido")
    if identity and not session.patient_id:
        session.patient_id = identity["sub"]
    user_message = ChatMessage(tenant_id=session.tenant_id, session_id=session.id, role="user", content=payload.content)
    db.add(user_message)

    result = run_workflow(
        db,
        {
            "tenant_id": session.tenant_id,
            "patient_id": session.patient_id,
            "message": payload.content,
        },
    )
    ticket = None
    tool_result = None
    if payload.action and identity and payload.confirmed:
        action_type = payload.action.get("type")
        if action_type == "schedule":
            created = create_appointment(
                AppointmentCreate(
                    doctor_id=payload.action["doctor_id"],
                    starts_at=payload.action["starts_at"],
                    reason=payload.action.get("reason", "Consulta"),
                    confirmed=True,
                ),
                identity,
                db,
            )
            tool_result = {"type": "appointment_created", "appointment": created}
        elif action_type == "cancel":
            cancelled = cancel_appointment(payload.action["appointment_id"], True, identity, db)
            tool_result = {"type": "appointment_cancelled", "appointment": cancelled}
    if payload.confirm_ticket and (result["intent"] == "ticket" or result["confidence"] < 0.6):
        ticket = Ticket(tenant_id=session.tenant_id, patient_id=session.patient_id, subject="Solicitação pelo chat", message=payload.content)
        db.add(ticket)
        db.flush()
    assistant = ChatMessage(
        tenant_id=session.tenant_id,
        session_id=session.id,
        role="assistant",
        content=result["answer"],
        citations=result.get("citations", []),
        metadata_json={
            "intent": result["intent"],
            "confidence": result["confidence"],
            "graph_trace": result["graph_trace"],
            "form_request": result.get("form_request"),
            "confirmation_request": result.get("confirmation_request"),
            "tool_result": tool_result,
            "ticket_id": ticket.id if ticket else None,
        },
    )
    db.add(assistant)
    session.state = {"last_intent": result["intent"], "graph_trace": result["graph_trace"]}
    db.commit()
    db.refresh(assistant)
    return {
        "id": assistant.id,
        "answer": assistant.content,
        "intent": result["intent"],
        "confidence": result["confidence"],
        "citations": assistant.citations,
        "form_request": result.get("form_request"),
        "confirmation_request": result.get("confirmation_request"),
        "ticket_id": ticket.id if ticket else None,
        "tool_result": tool_result,
        "graph_trace": result["graph_trace"],
    }


@router.get("/sessions/{session_id}/events")
def stream_events(session_id: str, identity: dict | None = Depends(optional_identity), db: Session = Depends(get_db)):
    session = db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(404, "Conversa não encontrada")
    if identity and identity["tenant"] != session.tenant_id:
        raise HTTPException(403, "Tenant inválido")
    latest = db.scalar(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id, ChatMessage.role == "assistant")
        .order_by(ChatMessage.created_at.desc())
    )

    async def event_stream():
        yield "event: status\ndata: {\"status\":\"processing\"}\n\n"
        await asyncio.sleep(0)
        if latest:
            yield f"event: token\ndata: {json.dumps({'text': latest.content}, ensure_ascii=False)}\n\n"
            for citation in latest.citations:
                yield f"event: citation\ndata: {json.dumps(citation, ensure_ascii=False)}\n\n"
            for event_name in ("form_request", "confirmation_request", "tool_result"):
                value = latest.metadata_json.get(event_name)
                if value:
                    yield f"event: {event_name}\ndata: {json.dumps(value, ensure_ascii=False)}\n\n"
            if latest.metadata_json.get("ticket_id"):
                yield f"event: ticket_created\ndata: {json.dumps({'id': latest.metadata_json['ticket_id']})}\n\n"
            yield f"event: completed\ndata: {json.dumps({'id': latest.id, 'answer': latest.content}, ensure_ascii=False)}\n\n"
        else:
            yield "event: completed\ndata: {\"answer\":\"Conversa iniciada\"}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/sessions/{session_id}/attachments", status_code=202)
def attachment_handoff(session_id: str, db: Session = Depends(get_db)):
    if not db.get(ChatSession, session_id):
        raise HTTPException(404, "Conversa não encontrada")
    return {"upload_endpoint": "/api/v1/patient/documents", "requires_auth": True}

