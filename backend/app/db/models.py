from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    dataset_version: Mapped[str] = mapped_column(String(128))
    source_root: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="running")
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QuarantineRow(Base):
    __tablename__ = "quarantine_rows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_path: Mapped[str] = mapped_column(Text)
    locator: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Area(Base):
    __tablename__ = "areas"

    area_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    team_id: Mapped[str] = mapped_column(String(32))
    center_lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    center_lon: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))


class Team(Base):
    __tablename__ = "teams"

    team_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    lead_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(64))
    team_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))


class Well(Base):
    __tablename__ = "wells"

    asset_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    well_type: Mapped[str] = mapped_column(String(16))
    area_id: Mapped[str] = mapped_column(String(32), index=True)
    team_id: Mapped[str] = mapped_column(String(32))
    in_charge_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lat: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    lon: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    installed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    recorded_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    source_path: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (UniqueConstraint("equipment_id", name="uq_equipment_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(String(32), index=True)
    equipment_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)


class Inspection(Base):
    __tablename__ = "inspections"
    __table_args__ = (Index("ix_inspections_asset_time", "asset_id", "inspected_at"),)

    inspection_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_id: Mapped[str] = mapped_column(String(32), index=True)
    inspected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    inspector_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ambient_temp_c: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    wellhead_temp_c: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    spill_detected: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    spill_area_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    spill_est_volume_bbl: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_images: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    source_path: Mapped[str] = mapped_column(Text)
    source_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


class Maintenance(Base):
    __tablename__ = "maintenance"
    __table_args__ = (
        Index("ix_maintenance_asset_started", "asset_id", "started_at"),
        Index("ix_maintenance_triggered", "triggered_by_inspection_id"),
    )

    maintenance_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_id: Mapped[str] = mapped_column(String(32), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    maintenance_type: Mapped[str] = mapped_column(String(32))
    equipment_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    issue: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_taken: Mapped[str | None] = mapped_column(Text, nullable=True)
    technician_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contractor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    downtime_hours: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    cost_labor: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    cost_parts: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    cost_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    triggered_by_inspection_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    report_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    source_path: Mapped[str] = mapped_column(Text)
    source_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


class RegulatoryEvent(Base):
    __tablename__ = "regulatory_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_id: Mapped[str] = mapped_column(String(32), index=True)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    agency: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    protocol_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    related_inspection_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    hours_to_report: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    fine_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    source_path: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


class SourceNote(Base):
    __tablename__ = "source_notes"

    note_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_id: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    author_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note_type: Mapped[str] = mapped_column(String(64))
    inspection_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    text: Mapped[str] = mapped_column(Text)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    source_path: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    doc_key: Mapped[str] = mapped_column(String(256), unique=True)
    path: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(64), default="manual")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    section: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    tsv: Mapped[str | None] = mapped_column(Text, nullable=True)


class DomainRule(Base):
    __tablename__ = "domain_rules"

    rule_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(64))
    well_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    equipment_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    operator: Mapped[str] = mapped_column(String(32))
    threshold: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    units: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lookback_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deadline_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_document: Mapped[str] = mapped_column(Text)
    source_section: Mapped[str | None] = mapped_column(String(256), nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(64))
    validation_status: Mapped[str] = mapped_column(String(32), default="validated")


class ExtractedFact(Base):
    __tablename__ = "extracted_facts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    fact_type: Mapped[str] = mapped_column(String(64), index=True)
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    approximate: Mapped[bool] = mapped_column(Boolean, default=False)
    asset_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    inspection_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    maintenance_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    report_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    supporting_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_version: Mapped[str] = mapped_column(String(32), default="v1")
    validation_status: Mapped[str] = mapped_column(String(32), default="extracted")


class Correction(Base):
    __tablename__ = "corrections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    target_type: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[str] = mapped_column(String(64), index=True)
    field: Mapped[str] = mapped_column(String(64))
    original_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    author_user_id: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(String(64), default="inspection")
    status: Mapped[str] = mapped_column(String(32), default="active")
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    target_version: Mapped[int] = mapped_column(Integer, default=1)


class Assertion(Base):
    __tablename__ = "assertions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(64))
    author_user_id: Mapped[str] = mapped_column(String(32))
    asset_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    well_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    confirmation_state: Mapped[str] = mapped_column(String(32), default="active")
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RuleOverride(Base):
    __tablename__ = "rule_overrides"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    well_type: Mapped[str] = mapped_column(String(16), index=True)
    equipment_kind: Mapped[str] = mapped_column(String(64))
    metric: Mapped[str] = mapped_column(String(64))
    operator: Mapped[str] = mapped_column(String(16), default=">=")
    value: Mapped[Decimal] = mapped_column(Numeric(16, 4))
    lookback_days: Mapped[int] = mapped_column(Integer, default=365)
    author_user_id: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeVersion(Base):
    __tablename__ = "knowledge_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_version: Mapped[int] = mapped_column(Integer, default=1)
    knowledge_version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_owner", "owner_user_id", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_user_id: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(256), default="New chat")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    answer_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConversationReference(Base):
    __tablename__ = "conversation_references"
    __table_args__ = (Index("ix_refs_owner_discussed", "owner_user_id", "discussed_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_user_id: Mapped[str] = mapped_column(String(32))
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    asset_ids: Mapped[list[Any]] = mapped_column(JSONB)
    query_spec: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    discussed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_user_id: Mapped[str] = mapped_column(String(32), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    query_text: Mapped[str] = mapped_column(Text)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    result_set_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    answer_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_generation: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResultSet(Base):
    __tablename__ = "result_sets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    result_set_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    locator: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DemoSession(Base):
    __tablename__ = "demo_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    session_generation: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
