from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import datetime, timezone
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.conversation import ConversationContext, ConversationTurn
from app.agent.orchestration import AgentOrchestrator
from app.agent.presentation import response
from app.agent.tools import ToolGate, ToolInvocationPolicy, build_tool_registry
from app.agent.tools.registry import ToolSpec
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
from app.shared.infrastructure.uow import SqlAlchemyUnitOfWork, uow_factory

JsonObject = dict[str, object]
UnitOfWorkFactory = Callable[[], SqlAlchemyUnitOfWork]


class ConversationService:
    def __init__(self, factory: UnitOfWorkFactory = uow_factory):
        self._factory = factory
        self._agent = AgentOrchestrator()
        self._tools = build_tool_registry()
        self._tool_policy = ToolInvocationPolicy()

    def create(self, actor: Actor | None) -> JsonObject:
        with self._factory() as uow:
            item = ChatSession(patient_id=actor.id if actor else None)
            uow.session.add(item)
            uow.flush()
            return {"id": item.id, "created_at": item.created_at, "expires_at": item.expires_at}

    def message(self, session_id: str, content: str, actor: Actor | None) -> JsonObject:
        with self._factory() as uow:
            session = self._session(uow.session, session_id)
            if actor and not session.patient_id:
                session.patient_id = actor.id
            context = ConversationContext.model_validate(session.context_json or {})
            history = self._history(uow.session, session_id)
            uow.session.add(ChatMessage(session_id=session.id, role="user", content=content))
        outcome = self._agent.run_with_context(content, actor, context, history)
        return self._save_response(session_id, outcome.response, outcome.context)

    def resume(self, session_id: str, actor: Actor | None) -> JsonObject:
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
        if not isinstance(pending, dict) or not isinstance(pending.get("name"), str):
            raise ConflictError("Não há operação pendente")
        raw_arguments = pending.get("arguments", {})
        arguments = raw_arguments if isinstance(raw_arguments, dict) else {}
        return self.action(session_id, pending["name"], arguments, actor)

    def action(
        self,
        session_id: str,
        tool_name: str,
        arguments: JsonObject,
        actor: Actor | None,
    ) -> JsonObject:
        with self._factory() as uow:
            self._session(uow.session, session_id)
        try:
            spec = self._tools.get(tool_name)
        except KeyError as exc:
            raise ValidationError("Ação não permitida") from exc
        gate = self._tool_policy.evaluate(spec, actor)
        if gate == ToolGate.AUTHENTICATE:
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
        if gate == ToolGate.CONFIRM:
            return self._prepare_confirmation(
                session_id, spec, parsed.model_dump(mode="json"), actor
            )
        result = spec.handler.execute(parsed, actor)
        return self._save_response(session_id, self._agent.present_result(tool_name, result))

    def confirm(
        self, session_id: str, confirmation_id: str, accepted: bool, actor: Actor
    ) -> JsonObject:
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
                return cast(JsonObject, execution.result_json)
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
        if self._tool_policy.evaluate(spec, actor, confirmed=True) != ToolGate.EXECUTE:
            raise ConflictError("Operação não autorizada")
        result = spec.handler.execute(spec.handler.arguments_model.model_validate(arguments), actor)
        response = self._agent.present_result(tool_name, result)
        with self._factory() as uow:
            execution = uow.session.scalar(
                select(ToolExecution).where(ToolExecution.confirmation_id == confirmation_id)
            )
            if execution:
                execution.status, execution.result_json = ToolExecutionStatus.succeeded, response
        return self._save_response(session_id, response)

    def _prepare_confirmation(
        self,
        session_id: str,
        spec: ToolSpec,
        arguments: JsonObject,
        actor: Actor | None,
    ) -> JsonObject:
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

    def _save_response(
        self,
        session_id: str,
        result: JsonObject,
        context: ConversationContext | None = None,
    ) -> JsonObject:
        with self._factory() as uow:
            session = self._session(uow.session, session_id)
            if context is not None:
                session.context_json = context.model_dump(mode="json")
            uow.session.add(
                ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content=str(result["answer"]),
                    citations=cast(list[object], result.get("citations", [])),
                    metadata_json=result,
                )
            )
        return result

    @staticmethod
    def _session(db: Session, session_id: str) -> ChatSession:
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
    def _history(db: Session, session_id: str) -> tuple[ConversationTurn, ...]:
        messages = list(
            db.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(6)
            )
        )
        return tuple(
            ConversationTurn(role=message.role, content=message.content[:2_000])
            for message in reversed(messages)
            if message.role in {"user", "assistant"} and message.content.strip()
        )

    @staticmethod
    def _base(answer: str, intent: str, **values: object) -> JsonObject:
        return response(answer, intent, **values)
