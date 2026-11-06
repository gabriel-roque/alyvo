from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import select

from app.agent.orchestration import AgentOrchestrator
from app.agent.presentation import response
from app.agent.tools import build_tool_registry
from app.modules.identity.domain import Actor
from app.shared.application import (
    AuthenticationRequiredError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.shared.infrastructure.models import (
    ChatMessage,
    ChatSession,
    ToolExecution,
    ToolExecutionStatus,
)
from app.shared.infrastructure.uow import uow_factory


class ConversationService:
    def __init__(self, factory=uow_factory):
        self._factory = factory
        self._agent = AgentOrchestrator()
        self._tools = build_tool_registry()

    def create(self, actor: Actor | None) -> dict:
        with self._factory() as uow:
            item = ChatSession(patient_id=actor.id if actor else None)
            uow.session.add(item)
            uow.flush()
            return {"id": item.id, "created_at": item.created_at, "expires_at": item.expires_at}

    def message(self, session_id: str, content: str, actor: Actor | None) -> dict:
        with self._factory() as uow:
            session = self._session(uow.session, session_id)
            if actor and not session.patient_id:
                session.patient_id = actor.id
            uow.session.add(ChatMessage(session_id=session.id, role="user", content=content))
        result = self._agent.run(content, actor)
        return self._save_response(session_id, result)

    def resume(self, session_id: str, actor: Actor | None) -> dict:
        if actor is None:
            raise AuthenticationRequiredError("Identificação necessária")
        with self._factory() as uow:
            session = self._session(uow.session, session_id)
            session.patient_id = actor.id
            last = uow.session.scalar(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id, ChatMessage.role == "assistant")
                .order_by(ChatMessage.created_at.desc())
                .limit(1)
            )
            pending = (last.metadata_json if last else {}).get("pending_tool")
        if not pending:
            raise ConflictError("Não há operação pendente")
        return self.action(session_id, pending["name"], pending.get("arguments", {}), actor)

    def action(self, session_id: str, tool_name: str, arguments: dict, actor: Actor | None) -> dict:
        with self._factory() as uow:
            self._session(uow.session, session_id)
        try:
            spec = self._tools.get(tool_name)
        except KeyError as exc:
            raise ValidationError("Ação não permitida") from exc
        if spec.requires_authentication and actor is None:
            return self._save_response(
                session_id,
                self._base(
                    "Confirme sua identidade para continuar.",
                    tool_name,
                    auth_required=True,
                    pending_tool={"name": tool_name, "arguments": arguments},
                ),
            )
        parsed = spec.handler.arguments_model.model_validate(arguments)
        if spec.requires_confirmation:
            return self._prepare_confirmation(
                session_id, spec, parsed.model_dump(mode="json"), actor
            )
        result = spec.handler.execute(parsed, actor)
        return self._save_response(session_id, AgentOrchestrator._present(tool_name, result))

    def confirm(self, session_id: str, confirmation_id: str, accepted: bool, actor: Actor) -> dict:
        with self._factory() as uow:
            execution = uow.session.scalar(
                select(ToolExecution).where(
                    ToolExecution.session_id == session_id,
                    ToolExecution.confirmation_id == confirmation_id,
                    ToolExecution.actor_id == actor.id,
                )
            )
            if not execution:
                raise NotFoundError("Confirmação expirada")
            if execution.status == ToolExecutionStatus.succeeded:
                return execution.result_json
            if execution.status != ToolExecutionStatus.pending:
                raise ConflictError("Confirmação já processada")
            if not accepted:
                execution.status = ToolExecutionStatus.cancelled
                response = self._base("Operação cancelada.", execution.tool_name)
                execution.result_json = response
                return response
            execution.status = ToolExecutionStatus.running
            tool_name, arguments = execution.tool_name, execution.arguments_json
        spec = self._tools.get(tool_name)
        result = spec.handler.execute(spec.handler.arguments_model.model_validate(arguments), actor)
        response = AgentOrchestrator._present(tool_name, result)
        with self._factory() as uow:
            execution = uow.session.scalar(
                select(ToolExecution).where(ToolExecution.confirmation_id == confirmation_id)
            )
            if execution:
                execution.status, execution.result_json = ToolExecutionStatus.succeeded, response
        return self._save_response(session_id, response)

    def _prepare_confirmation(self, session_id, spec, arguments: dict, actor: Actor | None) -> dict:
        if actor is None:
            raise AuthenticationRequiredError("Identificação necessária")
        confirmation_id = secrets.token_urlsafe(18)
        with self._factory() as uow:
            uow.session.add(
                ToolExecution(
                    session_id=session_id,
                    actor_id=actor.id,
                    confirmation_id=confirmation_id,
                    tool_name=spec.name,
                    arguments_json=arguments,
                )
            )
        response = self._base(
            "Revise os dados antes de concluir.",
            spec.name,
            confirmation_request={
                "id": confirmation_id,
                "tool": spec.name,
                "summary": "Confirme para concluir esta operação.",
            },
        )
        return self._save_response(session_id, response)

    def _save_response(self, session_id: str, result: dict) -> dict:
        with self._factory() as uow:
            self._session(uow.session, session_id)
            uow.session.add(
                ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content=result["answer"],
                    citations=result.get("citations", []),
                    metadata_json=result,
                )
            )
        return result

    @staticmethod
    def _session(db, session_id: str) -> ChatSession:
        item = db.get(ChatSession, session_id)
        now = datetime.now(timezone.utc)
        if (
            not item
            or (
                item.expires_at.replace(tzinfo=timezone.utc)
                if item.expires_at.tzinfo is None
                else item.expires_at
            )
            < now
        ):
            raise NotFoundError("Conversa expirada")
        return item

    @staticmethod
    def _base(answer: str, intent: str, **values) -> dict:
        return response(answer, intent, **values)
