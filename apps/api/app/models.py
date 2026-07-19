from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class PracticeTask(Base):
    __tablename__ = "practice_tasks"
    __table_args__ = (
        CheckConstraint("part in (1, 2, 3, 4)", name="practice_tasks_supported_parts"),
        CheckConstraint("status in ('draft','published','retired')", name="practice_tasks_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    part: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    examiner_instruction: Mapped[str] = mapped_column(Text, nullable=False)
    examiner_audio_path: Mapped[str] = mapped_column(String(255), nullable=False)
    setup: Mapped[str] = mapped_column(Text, nullable=False, default="")
    question: Mapped[str] = mapped_column(Text, nullable=False)
    questions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    decision_question: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_one_path: Mapped[str] = mapped_column(String(255), nullable=False)
    image_two_path: Mapped[str] = mapped_column(String(255), nullable=False)
    photo_one_keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    photo_two_keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    license_information: Mapped[str] = mapped_column(Text, nullable=False)
    content_notice: Mapped[str] = mapped_column(Text, nullable=False)
    teacher_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class PracticeSession(Base):
    __tablename__ = "practice_sessions"
    __table_args__ = (
        CheckConstraint(
            "status in ('created','upload_authorized','uploaded','processing','completed','failed')",
            name="practice_sessions_status",
        ),
        Index("ix_practice_sessions_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    access_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("practice_tasks.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="created")
    protocol_version: Mapped[str] = mapped_column(String(32), nullable=False, default="part2-v1")
    consent_policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    recording_consent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    response_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interaction_events: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    task: Mapped[PracticeTask] = relationship(lazy="joined")
    recordings: Mapped[list[Recording]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Recording(Base):
    __tablename__ = "recordings"
    __table_args__ = (
        CheckConstraint(
            "upload_status in ('pending','authorized','uploaded','validated','rejected')",
            name="recordings_upload_status",
        ),
        UniqueConstraint("session_id", "kind", name="uq_recording_session_kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("practice_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False, default="candidate_response")
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(96))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    upload_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    session: Mapped[PracticeSession] = relationship(back_populates="recordings")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending','processing','completed','failed')",
            name="processing_jobs_status",
        ),
        UniqueConstraint("session_id", "job_type", name="uq_job_session_type"),
        Index("ix_processing_jobs_ready", "status", "available_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("practice_sessions.id", ondelete="CASCADE"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(32), nullable=False, default="full_evaluation")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    processing_stage: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued", server_default="queued"
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_error_detail: Mapped[str | None] = mapped_column(Text)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stage_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (
        CheckConstraint("start_ms >= 0 and end_ms >= start_ms", name="transcript_valid_time"),
        Index("ix_transcript_segments_session_time", "session_id", "start_ms"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("practice_sessions.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (UniqueConstraint("session_id", name="uq_evaluation_session"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("practice_sessions.id", ondelete="CASCADE"), nullable=False
    )
    rubric_version: Mapped[str] = mapped_column(String(32), nullable=False)
    transcription_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_snapshot: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    strengths: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    priority_improvements: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    grammar_vocabulary_result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    discourse_management_result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    interactive_communication_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    task_performance_result: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    pronunciation_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    objective_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    suggested_exercises: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    overall_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="completed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class Part3CandidateResult(Base):
    __tablename__ = "part3_candidate_results"
    __table_args__ = (
        CheckConstraint("candidate_label in ('A','B')", name="part3_candidate_label"),
        UniqueConstraint("session_id", "candidate_label", name="uq_part3_result_candidate"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("practice_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_label: Mapped[str] = mapped_column(String(1), nullable=False)
    transcript: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    evaluation: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    pronunciation: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    objective_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    model_snapshot: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class EvaluationEvidence(Base):
    __tablename__ = "evaluation_evidence"
    __table_args__ = (
        CheckConstraint("start_ms >= 0 and end_ms >= start_ms", name="evidence_valid_time"),
        Index("ix_evidence_evaluation", "evaluation_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    transcript_segment_id: Mapped[str | None] = mapped_column(
        ForeignKey("transcript_segments.id", ondelete="SET NULL")
    )
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)


class TeacherReview(Base):
    __tablename__ = "teacher_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("practice_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    teacher_identifier: Mapped[str] = mapped_column(String(128), nullable=False)
    feedback_accuracy: Mapped[int] = mapped_column(Integer, nullable=False)
    feedback_usefulness: Mapped[int] = mapped_column(Integer, nullable=False)
    comments: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
