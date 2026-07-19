from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class TaskResponse(ApiModel):
    id: str
    part: Literal[1, 2, 3]
    version: str
    examiner_instruction: str
    examiner_audio_path: str
    setup: str
    question: str
    questions: list[str]
    decision_question: str
    image_one_path: str
    image_two_path: str
    content_notice: str
    evaluation_available: bool = False
    diarization_available: bool = False


class SessionCreateRequest(ApiModel):
    task_id: str
    recording_consent: bool
    consent_policy_version: str = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def require_consent(self) -> SessionCreateRequest:
        if not self.recording_consent:
            raise ValueError("recording consent is required")
        return self


class SessionCreateResponse(ApiModel):
    session_id: str
    session_token: str
    status: str
    expires_at: datetime


class PartnerTurn(ApiModel):
    spoken_text: str = Field(min_length=12, max_length=320)
    interaction_move: Literal["brief_opinion", "brief_preference"]
    hands_turn_back: Literal[True]
    estimated_seconds: float = Field(ge=4, le=15)
    safety_flags: list[str] = Field(default_factory=list, max_length=0)


class PartnerTurnResponse(ApiModel):
    follow_up_question: str
    spoken_text: str
    interaction_move: Literal["brief_opinion", "brief_preference"]
    estimated_seconds: float
    model: str
    source: Literal["ai", "prepared"]
    disclaimer_es: str


class Part3ConversationEvent(ApiModel):
    sequence: int = Field(ge=0, le=80)
    phase: Literal["discussion", "decision"]
    speaker: Literal["student", "ai_partner", "examiner"]
    started_at_ms: int = Field(ge=0, le=210_000)
    ended_at_ms: int = Field(ge=0, le=210_000)
    text: str = Field(min_length=1, max_length=1_200)
    move: str | None = Field(default=None, max_length=64)
    prompt_reference: str | None = Field(default=None, max_length=160)
    latency_ms: int | None = Field(default=None, ge=0, le=90_000)

    @model_validator(mode="after")
    def validate_event_times(self) -> Part3ConversationEvent:
        if self.ended_at_ms < self.started_at_ms:
            raise ValueError("ended_at_ms must not precede started_at_ms")
        return self


class Part3EventsRequest(ApiModel):
    events: list[Part3ConversationEvent] = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def validate_sequence(self) -> Part3EventsRequest:
        sequences = [event.sequence for event in self.events]
        if sequences != sorted(sequences) or len(set(sequences)) != len(sequences):
            raise ValueError("events must use a unique ascending sequence")
        return self


class UploadAuthorizationRequest(ApiModel):
    mime_type: str = Field(min_length=1, max_length=96)
    extension: Literal["webm", "ogg", "wav", "mp4", "m4a"]
    recording_kind: Literal[
        "candidate_response",
        "candidate_a_reference",
        "candidate_b_reference",
        "pair_response",
    ] = "candidate_response"


class UploadAuthorizationResponse(ApiModel):
    provider: Literal["local", "supabase"]
    recording_id: str
    storage_path: str
    upload_url: str | None = None
    upload_token: str
    bucket: str | None = None
    expires_in_seconds: int


class RecordingCompleteRequest(ApiModel):
    recording_id: str
    mime_type: str = Field(min_length=1, max_length=96)
    size_bytes: int = Field(gt=0, le=8 * 1024 * 1024)
    duration_ms: int = Field(ge=1_000, le=210_000)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    response_started_at: datetime
    response_ended_at: datetime

    @model_validator(mode="after")
    def validate_response_times(self) -> RecordingCompleteRequest:
        if self.response_ended_at <= self.response_started_at:
            raise ValueError("response_ended_at must follow response_started_at")
        return self


class SessionStatusResponse(ApiModel):
    session_id: str
    status: str
    processing_stage: str
    stage_started_at: datetime | None
    heartbeat_at: datetime | None
    can_retry: bool
    error_message_es: str | None


class TranscriptSegmentResponse(ApiModel):
    id: str
    position: int
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None


class StudentObservation(ApiModel):
    category: str
    evidence: str
    start_ms: int
    end_ms: int
    explanation_es: str
    suggestion_es: str
    severity: str
    confidence: float


class StudentCriterion(ApiModel):
    summary_es: str
    confidence: float
    practice_band: float | None = None
    observations: list[StudentObservation]


class StudentPracticeScore(ApiModel):
    global_band: float = Field(ge=0, le=5)
    tier_key: str
    tier_label: str
    tier_caption_es: str
    tier_index: int = Field(ge=0)
    tier_count: int = Field(ge=1)
    counted_criteria: list[str]
    confidence: float = Field(ge=0, le=1)
    disclaimer_es: str


class StudentTaskCheck(ApiModel):
    key: str
    status: str
    explanation_es: str
    evidence: str
    start_ms: int | None
    end_ms: int | None
    confidence: float


class StudentPronunciationObservation(ApiModel):
    feature: str
    start_ms: int
    end_ms: int
    explanation_es: str
    suggestion_es: str
    confidence: float


class StudentPronunciation(ApiModel):
    available: bool
    withheld_reason_es: str | None
    confidence: float
    summary_es: str
    observations: list[StudentPronunciationObservation]


class StudentReportResponse(ApiModel):
    session_id: str
    candidate_label: Literal["A", "B"] | None = None
    speaking_part: Literal[1, 2, 3]
    task_question: str
    evaluation_status: Literal["evaluated", "insufficient", "demo"]
    evaluation_status_reason_es: str
    disclaimer_es: str
    strengths: list[StudentObservation]
    priority_improvements: list[StudentObservation]
    grammar_vocabulary: StudentCriterion
    discourse_management: StudentCriterion
    interactive_communication: StudentCriterion | None
    pronunciation: StudentPronunciation
    practice_score: StudentPracticeScore | None = None
    task_performance: list[StudentTaskCheck]
    suggested_exercises: list[str]
    overall_confidence: float
    transcript: list[TranscriptSegmentResponse]
    audio_playback_url: str
    expires_at: datetime


class RetryResponse(ApiModel):
    session_id: str
    status: str


class DeleteResponse(ApiModel):
    deleted: bool


class TeacherValidationResponse(ApiModel):
    session_id: str
    transcript: list[TranscriptSegmentResponse]
    objective_metrics: dict[str, Any]
    evaluation: dict[str, Any]
    pronunciation: dict[str, Any] | None
    model_snapshot: dict[str, str]


class TeacherReviewRequest(ApiModel):
    teacher_identifier: str = Field(min_length=1, max_length=128)
    feedback_accuracy: int = Field(ge=1, le=5)
    feedback_usefulness: int = Field(ge=1, le=5)
    comments: str | None = Field(default=None, max_length=5_000)
