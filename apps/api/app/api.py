from __future__ import annotations

import hmac
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.file_validation import ALLOWED_MIME_TYPES, sha256_hex, validate_audio_content
from app.models import (
    Evaluation,
    Part3CandidateResult,
    PracticeSession,
    PracticeTask,
    ProcessingJob,
    Recording,
    TeacherReview,
    TranscriptSegment,
    new_id,
    utcnow,
)
from app.sample_data import PART2_FOLLOW_UP_QUESTIONS
from app.schemas import (
    DeleteResponse,
    Part3EventsRequest,
    PartnerTurnResponse,
    RecordingCompleteRequest,
    RetryResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionStatusResponse,
    StudentCriterion,
    StudentObservation,
    StudentPracticeScore,
    StudentPronunciation,
    StudentPronunciationObservation,
    StudentReportResponse,
    StudentTaskCheck,
    TaskResponse,
    TeacherReviewRequest,
    TeacherValidationResponse,
    TranscriptSegmentResponse,
    UploadAuthorizationRequest,
    UploadAuthorizationResponse,
)
from app.scoring import PracticeScore, compute_practice_score
from app.security import (
    extract_bearer_token,
    generate_session_token,
    hash_session_token,
    verify_scoped_signature,
    verify_session_token,
)
from app.storage import LocalStorageAdapter, StorageAdapter

router = APIRouter(prefix="/v1")


def runtime(request: Request) -> tuple[Settings, Any, StorageAdapter]:
    return request.app.state.settings, request.app.state.database, request.app.state.storage


async def authorized_session(
    session_id: str,
    authorization: str | None,
    db: AsyncSession,
    settings: Settings,
) -> PracticeSession:
    token = extract_bearer_token(authorization)
    session = await db.scalar(
        select(PracticeSession)
        .options(selectinload(PracticeSession.recordings))
        .where(PracticeSession.id == session_id)
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not verify_session_token(token, session.access_token_hash, settings.session_token_pepper):
        raise HTTPException(status_code=403, detail="Session token does not match")
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=410, detail="Session has expired")
    return session


def require_teacher_token(authorization: str | None, settings: Settings) -> None:
    if not settings.teacher_validation_token:
        raise HTTPException(status_code=404, detail="Teacher validation is disabled")
    token = extract_bearer_token(authorization)
    if not hmac.compare_digest(token, settings.teacher_validation_token):
        raise HTTPException(status_code=403, detail="Invalid teacher token")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, request: Request) -> TaskResponse:
    settings, database, _ = runtime(request)
    async with database.sessions() as db:
        task = await db.scalar(
            select(PracticeTask).where(
                PracticeTask.id == task_id,
                PracticeTask.status == "published",
            )
        )
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return TaskResponse.model_validate(task).model_copy(
            update={
                "evaluation_available": settings.ai_mode == "real",
                "diarization_available": settings.diarization_available,
            }
        )


@router.post(
    "/practice-sessions/{session_id}/ai-partner-turn",
    response_model=PartnerTurnResponse,
)
async def create_ai_partner_turn(
    session_id: str,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> PartnerTurnResponse:
    settings, database, _ = runtime(request)
    async with database.sessions() as db:
        session = await authorized_session(session_id, authorization, db, settings)
        task = await db.scalar(select(PracticeTask).where(PracticeTask.id == session.task_id))
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        follow_up_question = PART2_FOLLOW_UP_QUESTIONS.get(task.id)
        if not follow_up_question:
            raise HTTPException(status_code=409, detail="AI partner is not ready for this task")

    cache_key = (task.id, settings.partner_model, request.app.state.partner_source)
    cached = request.app.state.partner_turn_cache.get(cache_key)
    if cached is None:
        try:
            turn, model = await request.app.state.partner_provider.respond(
                task_question=task.question,
                follow_up_question=follow_up_question,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail="El candidato IA no ha podido preparar su turno. Puedes reintentarlo.",
            ) from exc
        cached = (turn, model)
        request.app.state.partner_turn_cache[cache_key] = cached
    turn, model = cached
    source = request.app.state.partner_source
    return PartnerTurnResponse(
        follow_up_question=follow_up_question,
        spoken_text=turn.spoken_text,
        interaction_move=turn.interaction_move,
        estimated_seconds=turn.estimated_seconds,
        model=model,
        source=source,
        disclaimer_es=(
            "Intervenci\u00f3n experimental generada como candidato B2. No se usa para evaluar "
            "tu lenguaje."
            if source == "ai"
            else "Respuesta preparada de demostraciÃ³n; no ha sido generada por IA en vivo."
        ),
    )


@router.post(
    "/practice-sessions",
    response_model=SessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(payload: SessionCreateRequest, request: Request) -> SessionCreateResponse:
    settings, database, _ = runtime(request)
    async with database.sessions() as db:
        task = await db.scalar(
            select(PracticeTask).where(
                PracticeTask.id == payload.task_id,
                PracticeTask.status == "published",
            )
        )
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        token = generate_session_token()
        expires_at = datetime.now(UTC) + timedelta(minutes=settings.session_retention_minutes)
        session = PracticeSession(
            access_token_hash=hash_session_token(token, settings.session_token_pepper),
            task_id=task.id,
            status="created",
            protocol_version={
                1: "part1-individual-interview-v1",
                2: "part2-long-turn-v1",
                3: "part3-pair-discussion-v1",
            }.get(task.part, "speaking-practice-v1"),
            consent_policy_version=payload.consent_policy_version,
            recording_consent=payload.recording_consent,
            expires_at=expires_at,
        )
        db.add(session)
        await db.commit()
        return SessionCreateResponse(
            session_id=session.id,
            session_token=token,
            status=session.status,
            expires_at=expires_at,
        )


@router.post(
    "/practice-sessions/{session_id}/upload-url",
    response_model=UploadAuthorizationResponse,
)
async def create_upload_url(
    session_id: str,
    payload: UploadAuthorizationRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> UploadAuthorizationResponse:
    settings, database, storage = runtime(request)
    canonical_mime = payload.mime_type.split(";", 1)[0].lower()
    expected_extension = ALLOWED_MIME_TYPES.get(canonical_mime)
    if expected_extension is None or (
        expected_extension != payload.extension
        and not {expected_extension, payload.extension} <= {"mp4", "m4a"}
    ):
        raise HTTPException(status_code=422, detail="Unsupported audio format")
    async with database.sessions() as db:
        session = await authorized_session(session_id, authorization, db, settings)
        allowed_kinds = (
            {"candidate_a_reference", "candidate_b_reference", "pair_response"}
            if session.task.part == 3
            else {"candidate_response"}
        )
        if payload.recording_kind not in allowed_kinds:
            raise HTTPException(status_code=422, detail="Recording kind is not valid for this task")
        if session.status not in {"created", "upload_authorized"}:
            raise HTTPException(
                status_code=409,
                detail="This session no longer accepts a replacement recording",
            )
        recording = next(
            (item for item in session.recordings if item.kind == payload.recording_kind), None
        )
        if recording is None:
            recording_id = new_id()
            storage_path = f"sessions/{session.id}/{recording_id}.{payload.extension}"
            recording = Recording(
                id=recording_id,
                session_id=session.id,
                kind=payload.recording_kind,
                storage_path=storage_path,
                mime_type=canonical_mime,
                upload_status="authorized",
            )
            db.add(recording)
        else:
            recording.upload_status = "authorized"
            recording.mime_type = canonical_mime
        session.status = "upload_authorized"
        await db.commit()
        grant = await storage.create_upload_grant(recording.id, recording.storage_path)
        return UploadAuthorizationResponse(
            provider=grant.provider,
            recording_id=recording.id,
            storage_path=grant.storage_path,
            upload_url=grant.upload_url,
            upload_token=grant.upload_token,
            bucket=grant.bucket,
            expires_in_seconds=grant.expires_in_seconds,
        )


@router.put("/uploads/{recording_id}", status_code=status.HTTP_204_NO_CONTENT)
async def local_upload(
    recording_id: str,
    request: Request,
    x_upload_token: Annotated[str | None, Header()] = None,
) -> Response:
    settings, database, storage = runtime(request)
    if not isinstance(storage, LocalStorageAdapter):
        raise HTTPException(status_code=404, detail="Local uploads are disabled")
    if not x_upload_token or not storage.verify_upload_token(recording_id, x_upload_token):
        raise HTTPException(status_code=403, detail="Invalid upload grant")
    declared_length = request.headers.get("content-length")
    if declared_length and int(declared_length) > settings.max_audio_bytes:
        raise HTTPException(status_code=413, detail="Audio file is too large")
    chunks = bytearray()
    async for chunk in request.stream():
        chunks.extend(chunk)
        if len(chunks) > settings.max_audio_bytes:
            raise HTTPException(status_code=413, detail="Audio file is too large")
    content = bytes(chunks)
    async with database.sessions() as db:
        recording = await db.scalar(select(Recording).where(Recording.id == recording_id))
        if not recording or recording.upload_status != "authorized":
            raise HTTPException(status_code=404, detail="Recording not found")
        try:
            validate_audio_content(content, recording.mime_type or "", settings.max_audio_bytes)
        except ValueError as exc:
            recording.upload_status = "rejected"
            await db.commit()
            raise HTTPException(status_code=422, detail="Invalid audio content") from exc
        await storage.save_local_upload(recording.storage_path, content)
        recording.size_bytes = len(content)
        recording.sha256 = sha256_hex(content)
        recording.upload_status = "uploaded"
        await db.commit()
    return Response(status_code=204)


@router.post(
    "/practice-sessions/{session_id}/recording-complete",
    response_model=SessionStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def recording_complete(
    session_id: str,
    payload: RecordingCompleteRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> SessionStatusResponse:
    settings, database, storage = runtime(request)
    async with database.sessions() as db:
        session = await authorized_session(session_id, authorization, db, settings)
        recording = next(
            (item for item in session.recordings if item.id == payload.recording_id), None
        )
        if not recording:
            raise HTTPException(status_code=404, detail="Recording not found")
        if not await storage.exists(recording.storage_path):
            raise HTTPException(status_code=409, detail="Recording upload is not available")
        content = await storage.read(recording.storage_path)
        try:
            validate_audio_content(content, payload.mime_type, settings.max_audio_bytes)
        except ValueError as exc:
            recording.upload_status = "rejected"
            await db.commit()
            raise HTTPException(status_code=422, detail="Invalid audio content") from exc
        if len(content) != payload.size_bytes or sha256_hex(content) != payload.sha256:
            recording.upload_status = "rejected"
            await db.commit()
            raise HTTPException(status_code=422, detail="Audio metadata does not match upload")
        recording.mime_type = payload.mime_type.split(";", 1)[0].lower()
        recording.size_bytes = len(content)
        recording.duration_ms = payload.duration_ms
        recording.sha256 = payload.sha256
        recording.upload_status = "validated"
        if recording.kind in {"candidate_a_reference", "candidate_b_reference"}:
            session.status = "created"
            await db.commit()
            return status_response(session, "voice_calibration", False, None)
        if recording.kind == "pair_response":
            reference_kinds = {
                item.kind for item in session.recordings if item.upload_status == "validated"
            }
            if not {"candidate_a_reference", "candidate_b_reference"} <= reference_kinds:
                raise HTTPException(
                    status_code=409,
                    detail="Both candidate voice references are required before processing",
                )
        session.response_started_at = payload.response_started_at
        session.response_ended_at = payload.response_ended_at
        job = await db.scalar(
            select(ProcessingJob).where(
                ProcessingJob.session_id == session.id,
                ProcessingJob.job_type == "full_evaluation",
            )
        )
        if job:
            await db.commit()
            can_retry = job.status == "failed" and job.attempt_count < settings.max_job_attempts
            return status_response(
                session,
                job.processing_stage,
                can_retry,
                _processing_failure_message(can_retry) if job.status == "failed" else None,
                stage_started_at=job.stage_started_at,
                heartbeat_at=job.heartbeat_at,
            )

        session.status = "uploaded"
        db.add(ProcessingJob(session_id=session.id, job_type="full_evaluation"))
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
        return status_response(session, "queued", False, None)


@router.post(
    "/practice-sessions/{session_id}/part3-events",
    response_model=SessionStatusResponse,
)
async def save_part3_events(
    session_id: str,
    payload: Part3EventsRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> SessionStatusResponse:
    settings, database, _ = runtime(request)
    async with database.sessions() as db:
        session = await authorized_session(session_id, authorization, db, settings)
        if session.task.part != 3:
            raise HTTPException(status_code=409, detail="Interaction events only apply to Part 3")
        if session.status not in {"created", "upload_authorized"}:
            raise HTTPException(status_code=409, detail="This session no longer accepts events")
        session.interaction_events = [item.model_dump(mode="json") for item in payload.events]
        await db.commit()
        return status_response(session, "conversation_recorded", False, None)


@router.get(
    "/practice-sessions/{session_id}",
    response_model=SessionStatusResponse,
)
async def get_session_status(
    session_id: str,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> SessionStatusResponse:
    settings, database, _ = runtime(request)
    async with database.sessions() as db:
        session = await authorized_session(session_id, authorization, db, settings)
        job = await db.scalar(select(ProcessingJob).where(ProcessingJob.session_id == session.id))
        stage = job.processing_stage if job else session.status
        can_retry = bool(
            job and job.status == "failed" and job.attempt_count < settings.max_job_attempts
        )
        message = None
        if session.status == "failed":
            detail = (job.last_error_detail or "") if job else ""
            if detail.startswith("LIMITE_IA: "):
                message = detail.removeprefix("LIMITE_IA: ")
            else:
                message = _processing_failure_message(can_retry)
        return status_response(
            session,
            stage,
            can_retry,
            message,
            stage_started_at=job.stage_started_at if job else None,
            heartbeat_at=job.heartbeat_at if job else None,
        )


@router.post(
    "/practice-sessions/{session_id}/retry",
    response_model=RetryResponse,
)
async def retry_processing(
    session_id: str,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> RetryResponse:
    settings, database, _ = runtime(request)
    async with database.sessions() as db:
        session = await authorized_session(session_id, authorization, db, settings)
        job = await db.scalar(select(ProcessingJob).where(ProcessingJob.session_id == session.id))
        if job and job.status == "completed" and session.status == "completed":
            return RetryResponse(session_id=session.id, status="completed")
        if not job or job.status != "failed":
            raise HTTPException(status_code=409, detail="No failed job is available to retry")
        if job.attempt_count >= settings.max_job_attempts:
            raise HTTPException(status_code=409, detail="Retry limit reached")
        job.status = "pending"
        job.processing_stage = "queued"
        job.stage_started_at = utcnow()
        job.heartbeat_at = None
        job.available_at = utcnow()
        job.last_error_code = None
        job.last_error_detail = None
        session.status = "uploaded"
        session.last_error_code = None
        await db.commit()
        return RetryResponse(session_id=session.id, status="pending")


@router.get(
    "/practice-sessions/{session_id}/report",
    response_model=StudentReportResponse,
    response_model_exclude_none=True,
)
async def get_report(
    session_id: str,
    request: Request,
    candidate: Annotated[Literal["A", "B"] | None, Query()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> StudentReportResponse:
    settings, database, storage = runtime(request)
    async with database.sessions() as db:
        session = await authorized_session(session_id, authorization, db, settings)
        if session.status != "completed":
            raise HTTPException(status_code=409, detail="Report is not ready")
        if session.task.part == 3:
            label = candidate or "A"
            result = await db.scalar(
                select(Part3CandidateResult).where(
                    Part3CandidateResult.session_id == session.id,
                    Part3CandidateResult.candidate_label == label,
                )
            )
            recording = next(
                (item for item in session.recordings if item.kind == "pair_response"), None
            )
            if not result or not recording:
                raise HTTPException(status_code=409, detail="Candidate report data is incomplete")
            playback = await storage.playback_url(recording.id, recording.storage_path)
            return build_part3_student_report(session, result, playback)
        evaluation = await db.scalar(select(Evaluation).where(Evaluation.session_id == session.id))
        segments = list(
            (
                await db.scalars(
                    select(TranscriptSegment)
                    .where(TranscriptSegment.session_id == session.id)
                    .order_by(TranscriptSegment.position)
                )
            ).all()
        )
        recording = next(
            (item for item in session.recordings if item.kind == "candidate_response"), None
        )
        if not evaluation or not recording:
            raise HTTPException(status_code=409, detail="Report data is incomplete")
        playback = await storage.playback_url(recording.id, recording.storage_path)
        return build_student_report(session, evaluation, segments, playback)


@router.delete(
    "/practice-sessions/{session_id}",
    response_model=DeleteResponse,
)
async def delete_session(
    session_id: str,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> DeleteResponse:
    settings, database, storage = runtime(request)
    async with database.sessions() as db:
        session = await authorized_session(session_id, authorization, db, settings)
        for recording in session.recordings:
            # Keep the database reference if object deletion fails so a later
            # retry can still locate and remove the temporary audio.
            await storage.delete(recording.storage_path)
        await db.delete(session)
        await db.commit()
        return DeleteResponse(deleted=True)


@router.get("/playback/{recording_id}")
async def local_playback(
    recording_id: str,
    request: Request,
    expires: Annotated[int, Query()],
    signature: Annotated[str, Query(min_length=20, max_length=128)],
) -> Response:
    settings, database, storage = runtime(request)
    if not isinstance(storage, LocalStorageAdapter):
        raise HTTPException(status_code=404, detail="Local playback is disabled")
    if not verify_scoped_signature(
        recording_id, signature, expires, settings.upload_signing_secret
    ):
        raise HTTPException(status_code=403, detail="Playback link is invalid or expired")
    async with database.sessions() as db:
        recording = await db.scalar(select(Recording).where(Recording.id == recording_id))
        if not recording:
            raise HTTPException(status_code=404, detail="Recording not found")
        content = await storage.read(recording.storage_path)
        return Response(
            content=content,
            media_type=recording.mime_type or "application/octet-stream",
            headers={
                "Cache-Control": "private, no-store",
                "Content-Disposition": 'inline; filename="practice-response"',
                "X-Content-Type-Options": "nosniff",
            },
        )


@router.get(
    "/internal/practice-sessions/{session_id}/validation",
    response_model=TeacherValidationResponse,
)
async def teacher_validation(
    session_id: str,
    request: Request,
    candidate_label: Annotated[Literal["A", "B"] | None, Query()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> TeacherValidationResponse:
    settings, database, _ = runtime(request)
    require_teacher_token(authorization, settings)
    async with database.sessions() as db:
        evaluation = await db.scalar(select(Evaluation).where(Evaluation.session_id == session_id))
        if not evaluation:
            if candidate_label is None:
                raise HTTPException(
                    status_code=422,
                    detail="candidate_label A or B is required for a Part 3 validation",
                )
            candidate_result = await db.scalar(
                select(Part3CandidateResult).where(
                    Part3CandidateResult.session_id == session_id,
                    Part3CandidateResult.candidate_label == candidate_label,
                )
            )
            if not candidate_result:
                raise HTTPException(status_code=404, detail="Candidate evaluation not found")
            return TeacherValidationResponse(
                session_id=session_id,
                transcript=[
                    TranscriptSegmentResponse(**item) for item in candidate_result.transcript
                ],
                objective_metrics=candidate_result.objective_metrics,
                evaluation=candidate_result.evaluation,
                pronunciation=candidate_result.pronunciation,
                model_snapshot=candidate_result.model_snapshot,
            )
        segments = list(
            (
                await db.scalars(
                    select(TranscriptSegment)
                    .where(TranscriptSegment.session_id == session_id)
                    .order_by(TranscriptSegment.position)
                )
            ).all()
        )
        return TeacherValidationResponse(
            session_id=session_id,
            transcript=[TranscriptSegmentResponse.model_validate(item) for item in segments],
            objective_metrics=evaluation.objective_metrics,
            evaluation={
                "evaluation_status": evaluation.status,
                "evaluation_status_reason_es": evaluation.objective_metrics.get(
                    "evaluation_status_reason_es", ""
                ),
                "strengths": evaluation.strengths,
                "priority_improvements": evaluation.priority_improvements,
                "grammar_vocabulary": evaluation.grammar_vocabulary_result,
                "discourse_management": evaluation.discourse_management_result,
                "task_performance": evaluation.task_performance_result,
                "suggested_exercises": evaluation.suggested_exercises,
                "overall_confidence": evaluation.overall_confidence,
            },
            pronunciation=evaluation.pronunciation_result,
            model_snapshot=evaluation.model_snapshot,
        )


@router.post("/internal/practice-sessions/{session_id}/teacher-reviews", status_code=201)
async def create_teacher_review(
    session_id: str,
    payload: TeacherReviewRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    settings, database, _ = runtime(request)
    require_teacher_token(authorization, settings)
    async with database.sessions() as db:
        session = await db.scalar(select(PracticeSession).where(PracticeSession.id == session_id))
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        review = TeacherReview(session_id=session_id, **payload.model_dump())
        db.add(review)
        await db.commit()
        return {"review_id": review.id}


def status_response(
    session: PracticeSession,
    stage: str,
    can_retry: bool,
    message: str | None,
    *,
    stage_started_at: datetime | None = None,
    heartbeat_at: datetime | None = None,
) -> SessionStatusResponse:
    return SessionStatusResponse(
        session_id=session.id,
        status=session.status,
        processing_stage=stage,
        stage_started_at=stage_started_at,
        heartbeat_at=heartbeat_at,
        can_retry=can_retry,
        error_message_es=message,
    )


def _processing_failure_message(can_retry: bool) -> str:
    if can_retry:
        return (
            "No hemos podido completar el análisis. La grabación se conserva y puedes reintentarlo."
        )
    return (
        "El análisis no ha podido completarse tras varios intentos. Para evitar un bucle, "
        "empieza una práctica nueva."
    )


def _to_student_score(score: PracticeScore | None) -> StudentPracticeScore | None:
    if score is None:
        return None
    return StudentPracticeScore(
        global_band=score.global_band,
        tier_key=score.tier_key,
        tier_label=score.tier_label,
        tier_caption_es=score.tier_caption_es,
        tier_index=score.tier_index,
        tier_count=score.tier_count,
        counted_criteria=score.counted_criteria,
        confidence=score.confidence,
        disclaimer_es=score.disclaimer_es,
    )


def _build_practice_score(
    *,
    speaking_part: int,
    evaluation_status: str,
    overall_confidence: float,
    grammar_vocabulary: dict[str, Any] | None,
    discourse_management: dict[str, Any] | None,
    interactive_communication: dict[str, Any] | None,
) -> StudentPracticeScore | None:
    bands = {
        "grammar_vocabulary": (grammar_vocabulary or {}).get("practice_band"),
        "discourse_management": (discourse_management or {}).get("practice_band"),
        "interactive_communication": (interactive_communication or {}).get("practice_band"),
    }
    score = compute_practice_score(
        speaking_part=speaking_part,
        evaluation_status=evaluation_status,
        overall_confidence=overall_confidence,
        criterion_bands=bands,
    )
    return _to_student_score(score)


def build_student_report(
    session: PracticeSession,
    evaluation: Evaluation,
    segments: list[TranscriptSegment],
    playback_url: str,
) -> StudentReportResponse:
    def observation(item: dict[str, Any]) -> StudentObservation:
        return StudentObservation(**item)

    def criterion(data: dict[str, Any]) -> StudentCriterion:
        return StudentCriterion(
            summary_es=data["summary_es"],
            confidence=data["confidence"],
            practice_band=data.get("practice_band"),
            observations=[observation(item) for item in data.get("observations", [])],
        )

    report_status = _evaluation_status(evaluation)
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        # SQLite drops timezone metadata. Restore the UTC contract before
        # serialising so browsers convert the expiry to the user's local time.
        expires_at = expires_at.replace(tzinfo=UTC)
    task_checks = (
        [
            StudentTaskCheck(
                key=item["key"],
                status=item["status"],
                explanation_es=item["explanation_es"],
                evidence=item.get("evidence", ""),
                start_ms=item.get("start_ms"),
                end_ms=item.get("end_ms"),
                confidence=item["confidence"],
            )
            for item in evaluation.task_performance_result
        ]
        if report_status == "evaluated"
        else []
    )
    pronunciation_data = evaluation.pronunciation_result or {}
    pronunciation = StudentPronunciation(
        available=bool(pronunciation_data.get("available", False)),
        withheld_reason_es=pronunciation_data.get("withheld_reason_es"),
        confidence=float(pronunciation_data.get("confidence", 0.0)),
        summary_es=str(
            pronunciation_data.get(
                "pronunciation_summary_es", "No hay un análisis de pronunciación disponible."
            )
        ),
        observations=[
            StudentPronunciationObservation(**item)
            for item in pronunciation_data.get("pronunciation_observations", [])
        ],
    )
    practice_score = _build_practice_score(
        speaking_part=session.task.part,
        evaluation_status=report_status,
        overall_confidence=evaluation.overall_confidence,
        grammar_vocabulary=evaluation.grammar_vocabulary_result,
        discourse_management=evaluation.discourse_management_result,
        interactive_communication=evaluation.interactive_communication_result,
    )
    return StudentReportResponse(
        session_id=session.id,
        speaking_part=session.task.part,
        task_question=session.task.question,
        evaluation_status=report_status,
        evaluation_status_reason_es=evaluation.objective_metrics.get(
            "evaluation_status_reason_es", ""
        ),
        disclaimer_es=_report_disclaimer(evaluation),
        strengths=[observation(item) for item in evaluation.strengths],
        priority_improvements=[observation(item) for item in evaluation.priority_improvements],
        grammar_vocabulary=criterion(evaluation.grammar_vocabulary_result),
        discourse_management=criterion(evaluation.discourse_management_result),
        interactive_communication=(
            criterion(evaluation.interactive_communication_result)
            if evaluation.interactive_communication_result
            else None
        ),
        pronunciation=pronunciation,
        practice_score=practice_score,
        task_performance=task_checks,
        suggested_exercises=evaluation.suggested_exercises,
        overall_confidence=evaluation.overall_confidence,
        transcript=[TranscriptSegmentResponse.model_validate(item) for item in segments],
        audio_playback_url=playback_url,
        expires_at=expires_at,
    )


def build_part3_student_report(
    session: PracticeSession,
    result: Part3CandidateResult,
    playback_url: str,
) -> StudentReportResponse:
    payload = result.evaluation

    def observation(item: dict[str, Any]) -> StudentObservation:
        return StudentObservation(**item)

    def criterion(data: dict[str, Any]) -> StudentCriterion:
        return StudentCriterion(
            summary_es=data["summary_es"],
            confidence=data["confidence"],
            practice_band=data.get("practice_band"),
            observations=[observation(item) for item in data.get("observations", [])],
        )

    pronunciation_data = result.pronunciation or {}
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    status_value = str(payload.get("evaluation_status", "insufficient"))
    if status_value not in {"evaluated", "insufficient", "demo"}:
        status_value = "insufficient"
    practice_score = _build_practice_score(
        speaking_part=3,
        evaluation_status=status_value,
        overall_confidence=float(payload.get("overall_confidence", 0.0)),
        grammar_vocabulary=payload.get("grammar_vocabulary"),
        discourse_management=payload.get("discourse_management"),
        interactive_communication=payload.get("interactive_communication"),
    )
    return StudentReportResponse(
        session_id=session.id,
        candidate_label=result.candidate_label,
        speaking_part=3,
        task_question=(f"{session.task.question} / Decision: {session.task.decision_question}"),
        evaluation_status=status_value,
        evaluation_status_reason_es=str(payload.get("status_reason_es", "")),
        disclaimer_es=(
            "Evaluacion formativa no oficial. La atribucion a Candidate "
            f"{result.candidate_label} procede de diarizacion calibrada y debe revisarse si "
            "las voces se solapan o suenan muy parecidas."
        ),
        strengths=[observation(item) for item in payload.get("strengths", [])],
        priority_improvements=[
            observation(item) for item in payload.get("priority_improvements", [])
        ],
        grammar_vocabulary=criterion(payload["grammar_vocabulary"]),
        discourse_management=criterion(payload["discourse_management"]),
        interactive_communication=(
            criterion(payload["interactive_communication"])
            if payload.get("interactive_communication")
            else None
        ),
        pronunciation=StudentPronunciation(
            available=bool(pronunciation_data.get("available", False)),
            withheld_reason_es=pronunciation_data.get("withheld_reason_es"),
            confidence=float(pronunciation_data.get("confidence", 0.0)),
            summary_es=str(
                pronunciation_data.get(
                    "pronunciation_summary_es",
                    "No hay un analisis de pronunciacion individual disponible.",
                )
            ),
            observations=[
                StudentPronunciationObservation(**item)
                for item in pronunciation_data.get("pronunciation_observations", [])
            ],
        ),
        practice_score=practice_score,
        task_performance=[
            StudentTaskCheck(
                key=item["key"],
                status=item["status"],
                explanation_es=item["explanation_es"],
                evidence=item.get("evidence", ""),
                start_ms=item.get("start_ms"),
                end_ms=item.get("end_ms"),
                confidence=item["confidence"],
            )
            for item in payload.get("task_performance", [])
        ],
        suggested_exercises=list(payload.get("suggested_exercises", [])),
        overall_confidence=float(payload.get("overall_confidence", 0.0)),
        transcript=[TranscriptSegmentResponse(**item) for item in result.transcript],
        audio_playback_url=playback_url,
        expires_at=expires_at,
    )


def _report_disclaimer(evaluation: Evaluation) -> str:
    reason = evaluation.objective_metrics.get("evaluation_status_reason_es", "").strip()
    status = _evaluation_status(evaluation)
    if status == "demo":
        return (
            "Intento guardado sin evaluación. Este resultado no contiene feedback sobre tu nivel."
        )
    if status == "insufficient":
        return (
            f"RESPUESTA NO EVALUABLE. {reason} "
            "No se asignan fortalezas ni puntuaciones sin evidencia suficiente. "
            "No es una calificación oficial de Cambridge English."
        ).strip()
    return (
        "Esta evaluación ha sido generada automáticamente con fines formativos. "
        "No es una calificación oficial de Cambridge English."
    )


def _evaluation_status(evaluation: Evaluation) -> str:
    # Rows created before explicit status support used "completed".
    return (
        evaluation.status
        if evaluation.status in {"evaluated", "insufficient", "demo"}
        else "evaluated"
    )
