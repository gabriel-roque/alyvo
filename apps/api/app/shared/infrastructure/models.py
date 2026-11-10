from __future__ import annotations

import enum
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Table,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.shared.domain import new_id


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Role(str, enum.Enum):
    admin = "admin"
    receptionist = "receptionist"
    patient = "patient"


class AppointmentStatus(str, enum.Enum):
    confirmed = "confirmed"
    cancelled = "cancelled"


class DocumentStatus(str, enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    review_required = "review_required"
    published = "published"
    rejected = "rejected"
    failed = "failed"


class ToolExecutionStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class ClinicProfile(Base):
    __tablename__ = "clinic_profile"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_clinic_profile_singleton"),
        CheckConstraint(
            "cancellation_notice_hours >= 0",
            name="ck_clinic_profile_cancellation_notice",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    name: Mapped[str] = mapped_column(String(160))
    timezone: Mapped[str] = mapped_column(String(64), default="America/Sao_Paulo")
    cancellation_notice_hours: Mapped[int] = mapped_column(Integer, default=0)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False))
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    cpf_hmac: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    cpf_encrypted: Mapped[str | None] = mapped_column(Text)
    birth_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


doctor_insurers = Table(
    "doctor_insurers",
    Base.metadata,
    Column("doctor_id", ForeignKey("doctors.id", ondelete="CASCADE"), primary_key=True),
    Column("insurer_id", ForeignKey("insurers.id", ondelete="RESTRICT"), primary_key=True),
)


exam_units = Table(
    "exam_units",
    Base.metadata,
    Column("exam_id", ForeignKey("exams.id", ondelete="CASCADE"), primary_key=True),
    Column("unit_id", ForeignKey("units.id", ondelete="RESTRICT"), primary_key=True),
)


class Specialty(Base):
    __tablename__ = "specialties"
    __table_args__ = (UniqueConstraint("name", name="uq_specialties_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Unit(Base):
    __tablename__ = "units"
    __table_args__ = (UniqueConstraint("name", name="uq_units_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(255), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Insurer(Base):
    __tablename__ = "insurers"
    __table_args__ = (UniqueConstraint("name", name="uq_insurers_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Doctor(Base):
    __tablename__ = "doctors"
    __table_args__ = (UniqueConstraint("crm", name="uq_doctors_crm"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    crm: Mapped[str] = mapped_column(String(40))
    specialty_id: Mapped[str] = mapped_column(ForeignKey("specialties.id", ondelete="RESTRICT"))
    unit_id: Mapped[str] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    specialty: Mapped[Specialty] = relationship(lazy="joined")
    unit: Mapped[Unit] = relationship(lazy="joined")
    insurers: Mapped[list[Insurer]] = relationship(secondary=doctor_insurers, lazy="selectin")


class Exam(Base):
    __tablename__ = "exams"
    __table_args__ = (UniqueConstraint("name", name="uq_exams_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    preparation: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    units: Mapped[list[Unit]] = relationship(secondary=exam_units, lazy="selectin")


class AvailabilityRule(Base):
    __tablename__ = "availability_rules"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_rule_weekday"),
        CheckConstraint("starts_at < ends_at", name="ck_rule_interval"),
        CheckConstraint("slot_minutes BETWEEN 10 AND 240", name="ck_rule_slot_minutes"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"), index=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey("units.id"))
    weekday: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)
    slot_minutes: Mapped[int] = mapped_column(Integer, default=30)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AvailabilityBlock(Base):
    __tablename__ = "availability_blocks"
    __table_args__ = (CheckConstraint("starts_at < ends_at", name="ck_block_interval"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(200), default="Bloqueio administrativo")


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (CheckConstraint("starts_at < ends_at", name="ck_appointment_interval"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"), index=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey("units.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, native_enum=False), default=AppointmentStatus.confirmed
    )
    reason: Mapped[str] = mapped_column(String(200), default="Consulta")
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppointmentHistory(Base):
    __tablename__ = "appointment_history"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    appointment_id: Mapped[str] = mapped_column(ForeignKey("appointments.id"), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36))
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, default="")
    filename: Mapped[str] = mapped_column(String(255), default="")
    storage_key: Mapped[str] = mapped_column(String(512), default="")
    content_type: Mapped[str] = mapped_column(String(120), default="text/plain")
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, native_enum=False), default=DocumentStatus.review_required
    )
    source: Mapped[str] = mapped_column(String(255), default="Base institucional")
    version: Mapped[int] = mapped_column(default=1)
    entities: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (UniqueConstraint("document_id", "position", name="uq_chunk_position"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list] = mapped_column(JSON, default=list)
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    section: Mapped[str] = mapped_column(String(255), default="")
    page: Mapped[int | None] = mapped_column(Integer)
    parent_id: Mapped[str | None] = mapped_column(String(64), index=True)
    parser_version: Mapped[str] = mapped_column(String(40), default="structural-v1")
    embedding_model: Mapped[str] = mapped_column(String(120), default="BAAI/bge-m3")
    index_version: Mapped[str] = mapped_column(String(40), default="v1", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeIndexVersion(Base):
    __tablename__ = "knowledge_index_versions"
    __table_args__ = (UniqueConstraint("version", name="uq_knowledge_index_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version: Mapped[str] = mapped_column(String(40))
    parser_version: Mapped[str] = mapped_column(String(40))
    embedding_model: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    aggregate_type: Mapped[str] = mapped_column(String(80), index=True)
    aggregate_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(120))
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(36))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    context_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: utcnow() + timedelta(hours=2)
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ToolExecution(Base):
    __tablename__ = "tool_executions"
    __table_args__ = (UniqueConstraint("confirmation_id", name="uq_tool_confirmation"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(36), index=True)
    confirmation_id: Mapped[str] = mapped_column(String(64), index=True)
    tool_name: Mapped[str] = mapped_column(String(80))
    arguments_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[ToolExecutionStatus] = mapped_column(
        Enum(ToolExecutionStatus, native_enum=False), default=ToolExecutionStatus.pending
    )
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_code: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


checkpoint_json_type = JSON().with_variant(JSONB(), "postgresql")


class CheckpointMigration(Base):
    """Migration ledger required by langgraph-checkpoint-postgres."""

    __tablename__ = "checkpoint_migrations"
    v: Mapped[int] = mapped_column(Integer, primary_key=True)


class AgentCheckpoint(Base):
    """Durable graph state without authenticated identity in its payload."""

    __tablename__ = "checkpoints"
    thread_id: Mapped[str] = mapped_column(Text, primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(Text, primary_key=True, default="")
    checkpoint_id: Mapped[str] = mapped_column(Text, primary_key=True)
    parent_checkpoint_id: Mapped[str | None] = mapped_column(Text)
    checkpoint_type: Mapped[str | None] = mapped_column("type", Text)
    checkpoint: Mapped[dict] = mapped_column(checkpoint_json_type)
    metadata_json: Mapped[dict] = mapped_column("metadata", checkpoint_json_type, default=dict)


class AgentCheckpointBlob(Base):
    __tablename__ = "checkpoint_blobs"
    thread_id: Mapped[str] = mapped_column(Text, primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(Text, primary_key=True, default="")
    channel: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[str] = mapped_column(Text, primary_key=True)
    blob_type: Mapped[str] = mapped_column("type", Text)
    blob: Mapped[bytes | None] = mapped_column(LargeBinary)


class AgentCheckpointWrite(Base):
    __tablename__ = "checkpoint_writes"
    thread_id: Mapped[str] = mapped_column(Text, primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(Text, primary_key=True, default="")
    checkpoint_id: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str] = mapped_column(Text, primary_key=True)
    idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(Text)
    write_type: Mapped[str | None] = mapped_column("type", Text)
    blob: Mapped[bytes] = mapped_column(LargeBinary)
    task_path: Mapped[str] = mapped_column(Text, default="")


Index(
    "ix_appointments_doctor_interval",
    Appointment.doctor_id,
    Appointment.starts_at,
    Appointment.ends_at,
)
