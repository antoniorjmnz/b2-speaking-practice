from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.audio_analysis import (
    analyse_audio,
    decode_audio,
    enrich_objective_metrics,
)
from app.config import Settings
from app.database import Database
from app.evaluation_schemas import Observation
from app.evidence import locate_evidence, verify_evaluation_evidence
from app.models import (
    Evaluation,
    EvaluationEvidence,
    Part3CandidateResult,
    PracticeSession,
    ProcessingJob,
    Recording,
    TranscriptSegment,
    utcnow,
)
from app.objective_checks import (
    apply_objective_task_checks,
    detect_part3_option_coverage,
    withheld_pronunciation,
)
from app.providers.base import TranscriptionResult
from app.providers.factory import create_diarization_provider, create_providers
from app.providers.mock import DEMO_REASON_ES, not_evaluable_payload
from app.storage import StorageAdapter

StageResult = TypeVar("StageResult")


class Processor:
    def __init__(self, settings: Settings, database: Database, storage: StorageAdapter) -> None:
        self.settings = settings
        self.database = database
        self.storage = storage
        self.transcriber, self.evaluator, self.pronunciation = create_providers(settings)
        self.diarizer = create_diarization_provider(settings)
        self._stopping = asyncio.Event()

    async def run_forever(self) -> None:
        await self.recover_stale_jobs()
        cleanup_counter = 0
        while not self._stopping.is_set():
            processed = await self.process_next_job()
            cleanup_counter += 1
            if cleanup_counter >= 120:
                await self.recover_stale_jobs()
                await self.cleanup_expired_sessions()
                cleanup_counter = 0
            if not processed:
                try:
                    await asyncio.wait_for(
                        self._stopping.wait(), timeout=self.settings.worker_poll_seconds
                    )
                except TimeoutError:
                    pass

    async def stop(self) -> None:
        self._stopping.set()

    async def process_next_job(self) -> bool:
        async with self.database.sessions() as db:
            statement = (
                select(ProcessingJob)
                .where(
                    ProcessingJob.status == "pending",
                    ProcessingJob.available_at <= utcnow(),
                )
                .order_by(ProcessingJob.created_at)
                .limit(1)
            )
            if not self.settings.database_url.startswith("sqlite"):
                statement = statement.with_for_update(skip_locked=True)
            job = await db.scalar(statement)
            if not job:
                return False
            job.status = "processing"
            job.attempt_count += 1
            now = utcnow()
            job.started_at = now
            job.processing_stage = "validating_audio"
            job.stage_started_at = now
            job.heartbeat_at = now
            session = await db.scalar(
                select(PracticeSession).where(PracticeSession.id == job.session_id)
            )
            if session:
                session.status = "processing"
                session.last_error_code = None
            await db.commit()
            job_id = job.id

        try:
            await self._process(job_id)
        except Exception as exc:  # noqa: BLE001 - boundary records a safe recoverable failure
            await self._mark_failed(job_id, exc)
        return True

    async def _set_stage(self, job_id: str, stage: str) -> None:
        async with self.database.sessions() as db:
            job = await db.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id))
            if not job or job.status != "processing":
                return
            now = utcnow()
            if job.processing_stage != stage:
                job.processing_stage = stage
                job.stage_started_at = now
            job.heartbeat_at = now
            await db.commit()

    async def _heartbeat(self, job_id: str) -> None:
        while not self._stopping.is_set():
            try:
                await asyncio.wait_for(
                    self._stopping.wait(), timeout=self.settings.worker_heartbeat_seconds
                )
            except TimeoutError:
                with suppress(Exception):
                    async with self.database.sessions() as db:
                        job = await db.scalar(
                            select(ProcessingJob).where(ProcessingJob.id == job_id)
                        )
                        if job and job.status == "processing":
                            job.heartbeat_at = utcnow()
                            await db.commit()

    async def _await_with_heartbeat(
        self, job_id: str, operation: Awaitable[StageResult]
    ) -> StageResult:
        heartbeat = asyncio.create_task(self._heartbeat(job_id))
        try:
            return await operation
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

    async def recover_stale_jobs(self) -> int:
        threshold = utcnow() - timedelta(seconds=self.settings.stale_job_seconds)
        recovered = 0
        async with self.database.sessions() as db:
            jobs = list(
                (
                    await db.scalars(
                        select(ProcessingJob).where(ProcessingJob.status == "processing")
                    )
                ).all()
            )
            for job in jobs:
                last_signal = job.heartbeat_at or job.started_at
                if last_signal is None:
                    continue
                if last_signal.tzinfo is None:
                    last_signal = last_signal.replace(tzinfo=UTC)
                if last_signal >= threshold:
                    continue
                session = await db.scalar(
                    select(PracticeSession).where(PracticeSession.id == job.session_id)
                )
                if job.attempt_count < self.settings.max_job_attempts:
                    job.status = "pending"
                    job.processing_stage = "queued"
                    job.available_at = utcnow()
                    job.stage_started_at = utcnow()
                    job.heartbeat_at = None
                    if session:
                        session.status = "uploaded"
                else:
                    job.status = "failed"
                    job.processing_stage = "failed"
                    job.last_error_code = "StaleProcessingJob"
                    if session:
                        session.status = "failed"
                        session.last_error_code = job.last_error_code
                recovered += 1
            if recovered:
                await db.commit()
        return recovered

    async def _process(self, job_id: str) -> None:
        async with self.database.sessions() as db:
            job = await db.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id))
            if not job:
                return
            session = await db.scalar(
                select(PracticeSession)
                .options(selectinload(PracticeSession.recordings))
                .where(PracticeSession.id == job.session_id)
            )
            if not session:
                raise RuntimeError("Session no longer exists")
            if session.task.part == 3:
                await db.commit()
                await self._process_part3(job_id)
                return
            recording = next(
                (item for item in session.recordings if item.kind == "candidate_response"), None
            )
            if not recording or recording.upload_status != "validated":
                raise RuntimeError("Validated recording is missing")
            content = await self.storage.read(recording.storage_path)
            # End the read transaction before remote calls so the heartbeat can
            # update the same SQLite database without waiting on a read lock.
            await db.commit()

            parallel_pronunciation_result: object | None = None

            async def update_evaluation_stage(stage: str) -> None:
                await self._set_stage(job_id, stage)

            await self._set_stage(job_id, "validating_audio")
            if self.settings.ai_mode == "real":
                decoded = decode_audio(content)
                wav_content = decoded.wav_bytes
                audio_metrics = analyse_audio(decoded)
            else:
                decoded = None
                wav_content = b""
                try:
                    decoded = decode_audio(content)
                    wav_content = decoded.wav_bytes
                    audio_metrics = analyse_audio(decoded)
                except Exception:  # noqa: BLE001 - demo remains honest without optional codecs
                    audio_metrics = _unavailable_demo_audio_metrics(recording.duration_ms)

            if self.settings.ai_mode != "real":
                await self._set_stage(job_id, "transcribing")
                transcription = await self._await_with_heartbeat(
                    job_id,
                    self.transcriber.transcribe(
                        content,
                        f"candidate-response.{recording.storage_path.rsplit('.', 1)[-1]}",
                        recording.mime_type or "application/octet-stream",
                        int(audio_metrics["recorded_duration_ms"]),
                    ),
                )
                metrics = _enrich_metrics(audio_metrics, transcription, session)
                evaluation, evaluation_model = await self._await_with_heartbeat(
                    job_id,
                    self.evaluator.evaluate(
                        question=session.task.question,
                        transcript=transcription.segments,
                        objective_metrics=metrics,
                        speaking_part=session.task.part,
                        questions=session.task.questions,
                        progress_callback=update_evaluation_stage,
                    ),
                )
            else:
                preflight_reason = _audio_evaluation_block_reason(audio_metrics)
                if preflight_reason:
                    transcription = TranscriptionResult(
                        segments=[],
                        provider_name="not-run",
                        model_name="deterministic-audio-preflight-v1",
                    )
                    metrics = _enrich_metrics(audio_metrics, transcription, session)
                    evaluation = not_evaluable_payload(
                        status="insufficient",
                        reason_es=preflight_reason,
                        confidence=0.05,
                        speaking_part=session.task.part,
                    )
                    evaluation_model = "deterministic-audio-preflight-v1"
                else:
                    await self._set_stage(job_id, "transcribing")
                    transcription = await self._await_with_heartbeat(
                        job_id,
                        self.transcriber.transcribe(
                            content,
                            f"candidate-response.{recording.storage_path.rsplit('.', 1)[-1]}",
                            recording.mime_type or "application/octet-stream",
                            int(audio_metrics["recorded_duration_ms"]),
                        ),
                    )
                    metrics = _enrich_metrics(audio_metrics, transcription, session)
                    transcript_reason = _transcript_evaluation_block_reason(transcription, metrics)
                    if transcript_reason:
                        evaluation = not_evaluable_payload(
                            status="insufficient",
                            reason_es=transcript_reason,
                            confidence=0.1,
                            speaking_part=session.task.part,
                        )
                        evaluation_model = "deterministic-transcript-preflight-v1"
                    else:
                        evaluation_operation = self.evaluator.evaluate(
                            question=session.task.question,
                            transcript=transcription.segments,
                            objective_metrics=metrics,
                            speaking_part=session.task.part,
                            questions=session.task.questions,
                            progress_callback=update_evaluation_stage,
                        )
                        quality = metrics.get("audio_quality", {})
                        if isinstance(quality, dict) and quality.get(
                            "sufficient_for_pronunciation"
                        ):
                            (
                                evaluation_result,
                                parallel_pronunciation_result,
                            ) = await self._await_with_heartbeat(
                                job_id,
                                asyncio.gather(
                                    evaluation_operation,
                                    self.pronunciation.analyse(
                                        wav_content=wav_content,
                                        objective_metrics=metrics,
                                    ),
                                    return_exceptions=True,
                                ),
                            )
                            if isinstance(evaluation_result, BaseException):
                                raise evaluation_result
                            evaluation, evaluation_model = evaluation_result
                        else:
                            evaluation, evaluation_model = await self._await_with_heartbeat(
                                job_id, evaluation_operation
                            )
            evaluation, rejected_count = verify_evaluation_evidence(
                evaluation, transcription.segments
            )
            evaluation = apply_objective_task_checks(evaluation, metrics)
            metrics["rejected_evidence_count"] = rejected_count
            metrics["evaluation_status"] = evaluation.evaluation_status
            metrics["evaluation_status_reason_es"] = evaluation.status_reason_es

            quality = metrics.get("audio_quality", {})
            if self.settings.ai_mode != "real":
                pronunciation_model = "demo-no-pronunciation-v1"
                pronunciation_payload = withheld_pronunciation(DEMO_REASON_ES, metrics)
            elif evaluation.evaluation_status != "evaluated":
                pronunciation_model = "withheld-not-evaluable"
                pronunciation_payload = withheld_pronunciation(
                    "La respuesta no contiene evidencia suficiente para analizar la pronunciación.",
                    metrics,
                )
            elif isinstance(quality, dict) and quality.get("sufficient_for_pronunciation"):
                if (
                    isinstance(parallel_pronunciation_result, tuple)
                    and len(parallel_pronunciation_result) == 2
                ):
                    pronunciation, pronunciation_model = parallel_pronunciation_result
                    pronunciation_payload = pronunciation.model_dump(mode="json")
                else:
                    pronunciation_model = self.settings.pronunciation_model or "unavailable"
                    pronunciation_payload = withheld_pronunciation(
                        "El proveedor experimental de pronunciación no estuvo disponible.", metrics
                    )
            else:
                pronunciation_model = self.settings.pronunciation_model or "withheld"
                pronunciation_payload = withheld_pronunciation(
                    "La calidad del audio no permite un análisis de pronunciación fiable.", metrics
                )

            await self._set_stage(job_id, "building_report")
            await db.execute(
                delete(EvaluationEvidence).where(
                    EvaluationEvidence.evaluation_id.in_(
                        select(Evaluation.id).where(Evaluation.session_id == session.id)
                    )
                )
            )
            await db.execute(delete(Evaluation).where(Evaluation.session_id == session.id))
            await db.execute(
                delete(TranscriptSegment).where(TranscriptSegment.session_id == session.id)
            )
            segment_models: list[TranscriptSegment] = []
            for position, segment in enumerate(transcription.segments):
                model = TranscriptSegment(
                    session_id=session.id,
                    position=position,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    text=segment.text,
                    confidence=segment.confidence,
                )
                db.add(model)
                segment_models.append(model)
            await db.flush()

            evaluation_model_row = Evaluation(
                session_id=session.id,
                rubric_version=f"part{session.task.part}-formative-v1",
                transcription_provider=transcription.provider_name,
                evaluation_provider=(
                    "demo-no-evaluation" if self.settings.ai_mode != "real" else "openai"
                ),
                model_snapshot={
                    "transcription": transcription.model_name,
                    "evaluation": evaluation_model,
                    "pronunciation": pronunciation_model,
                },
                strengths=[item.model_dump(mode="json") for item in evaluation.strengths],
                priority_improvements=[
                    item.model_dump(mode="json") for item in evaluation.priority_improvements
                ],
                grammar_vocabulary_result=evaluation.grammar_vocabulary.model_dump(mode="json"),
                discourse_management_result=evaluation.discourse_management.model_dump(mode="json"),
                interactive_communication_result=(
                    evaluation.interactive_communication.model_dump(mode="json")
                    if evaluation.interactive_communication
                    else None
                ),
                task_performance_result=[
                    item.model_dump(mode="json") for item in evaluation.task_performance
                ],
                pronunciation_result=pronunciation_payload,
                objective_metrics=metrics,
                suggested_exercises=evaluation.suggested_exercises,
                overall_confidence=evaluation.overall_confidence,
                status=evaluation.evaluation_status,
            )
            db.add(evaluation_model_row)
            await db.flush()
            for observation in _all_observations(evaluation):
                location = locate_evidence(observation.evidence, transcription.segments)
                if not location:
                    continue
                segment_id = next(
                    (
                        item.id
                        for item in segment_models
                        if item.start_ms <= location[0] and item.end_ms >= location[0]
                    ),
                    None,
                )
                db.add(
                    EvaluationEvidence(
                        evaluation_id=evaluation_model_row.id,
                        category=str(observation.category),
                        transcript_segment_id=segment_id,
                        start_ms=location[0],
                        end_ms=location[1],
                        excerpt=observation.evidence,
                        explanation=observation.explanation_es,
                    )
                )

            recording.duration_ms = int(metrics["recorded_duration_ms"])
            session.status = "completed"
            session.last_error_code = None
            job.status = "completed"
            completed_at = utcnow()
            job.processing_stage = "completed"
            job.stage_started_at = completed_at
            job.heartbeat_at = completed_at
            job.completed_at = completed_at
            job.last_error_code = None
            job.last_error_detail = None
            await db.commit()

    async def _process_part3(self, job_id: str) -> None:
        async with self.database.sessions() as db:
            job = await db.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id))
            if not job:
                return
            session = await db.scalar(
                select(PracticeSession)
                .options(selectinload(PracticeSession.recordings))
                .where(PracticeSession.id == job.session_id)
            )
            if not session or session.task.part != 3:
                raise RuntimeError("Part 3 session is missing")
            recordings = {item.kind: item for item in session.recordings}
            required = {
                "pair_response",
                "candidate_a_reference",
                "candidate_b_reference",
            }
            if any(
                kind not in recordings or recordings[kind].upload_status != "validated"
                for kind in required
            ):
                raise RuntimeError("Validated pair recording and voice references are required")
            pair_recording = recordings["pair_response"]
            reference_a = recordings["candidate_a_reference"]
            reference_b = recordings["candidate_b_reference"]
            pair_content, content_a, content_b = await asyncio.gather(
                self.storage.read(pair_recording.storage_path),
                self.storage.read(reference_a.storage_path),
                self.storage.read(reference_b.storage_path),
            )
            await db.commit()

            await self._set_stage(job_id, "validating_audio")
            decoded = decode_audio(pair_content)
            audio_metrics = analyse_audio(decoded)

            await self._set_stage(job_id, "separating_speakers")
            content_url = None
            reference_a_url = None
            reference_b_url = None
            if self.settings.diarization_provider == "modal":
                content_url, reference_a_url, reference_b_url = await asyncio.gather(
                    self.storage.playback_url(pair_recording.id, pair_recording.storage_path),
                    self.storage.playback_url(reference_a.id, reference_a.storage_path),
                    self.storage.playback_url(reference_b.id, reference_b.storage_path),
                )
            diarization = await self._await_with_heartbeat(
                job_id,
                self.diarizer.transcribe_pair(
                    content=pair_content,
                    filename=f"pair-response.{pair_recording.storage_path.rsplit('.', 1)[-1]}",
                    mime_type=pair_recording.mime_type or "audio/webm",
                    candidate_a_reference=content_a,
                    candidate_a_reference_mime=reference_a.mime_type or "audio/webm",
                    candidate_b_reference=content_b,
                    candidate_b_reference_mime=reference_b.mime_type or "audio/webm",
                    content_url=content_url,
                    candidate_a_reference_url=reference_a_url,
                    candidate_b_reference_url=reference_b_url,
                ),
            )
            speakers = {item.speaker for item in diarization.segments if item.speaker in {"A", "B"}}
            if speakers != {"A", "B"}:
                raise RuntimeError("The diarization did not identify both candidates reliably")

            conversation_context = [
                {
                    "speaker": item.speaker,
                    "start_ms": item.start_ms,
                    "end_ms": item.end_ms,
                    "text": item.text,
                    "confidence": item.confidence,
                }
                for item in diarization.segments
                if item.speaker in {"A", "B"}
            ]

            async def evaluate_candidate(label: str) -> dict[str, object]:
                candidate_segments = [
                    item for item in diarization.segments if item.speaker == label
                ]
                partner_label = "B" if label == "A" else "A"
                partner_segments = [
                    item for item in diarization.segments if item.speaker == partner_label
                ]
                candidate_talk_ms = sum(
                    max(0, item.end_ms - item.start_ms) for item in candidate_segments
                )
                partner_talk_ms = sum(
                    max(0, item.end_ms - item.start_ms) for item in partner_segments
                )
                metrics = {
                    **audio_metrics,
                    "speaking_part": 3,
                    "evaluation_candidate": label,
                    "candidate_turn_count": len(candidate_segments),
                    "partner_turn_count": len(partner_segments),
                    "candidate_talk_ms": candidate_talk_ms,
                    "partner_talk_ms": partner_talk_ms,
                    "candidate_word_count": sum(
                        len(item.text.split()) for item in candidate_segments
                    ),
                    "conversation_context": conversation_context,
                    "interaction_events": session.interaction_events,
                    "task_prompts": session.task.questions,
                    "decision_question": session.task.decision_question,
                    "diarization_calibrated": True,
                }
                option_coverage = detect_part3_option_coverage(metrics)
                metrics["candidate_option_mentions"] = option_coverage["candidate"]
                metrics["conversation_option_mentions"] = option_coverage["conversation"]
                metrics["candidate_option_count"] = len(option_coverage["candidate"])
                metrics["conversation_option_count"] = len(option_coverage["conversation"])

                if candidate_talk_ms < 8_000 or len(candidate_segments) < 2:
                    evaluation = not_evaluable_payload(
                        status="insufficient",
                        reason_es=(
                            f"La separacion de voz solo atribuyo {candidate_talk_ms / 1000:.1f} "
                            f"segundos y {len(candidate_segments)} turnos a Candidate {label}."
                        ),
                        confidence=0.1,
                        speaking_part=3,
                    )
                    evaluation_model = "deterministic-pair-preflight-v1"
                else:
                    evaluation, evaluation_model = await self.evaluator.evaluate(
                        question=(
                            f"Discussion: {session.task.question}\n"
                            f"Decision: {session.task.decision_question}"
                        ),
                        transcript=candidate_segments,
                        objective_metrics=metrics,
                        speaking_part=3,
                        questions=session.task.questions,
                    )
                evaluation, rejected_count = verify_evaluation_evidence(
                    evaluation, candidate_segments
                )
                evaluation = apply_objective_task_checks(evaluation, metrics)
                metrics["rejected_evidence_count"] = rejected_count
                metrics["evaluation_status"] = evaluation.evaluation_status
                pronunciation = withheld_pronunciation(
                    "La pronunciacion individual se habilitara cuando el recorte de audio por "
                    "hablante supere la validacion docente.",
                    metrics,
                )
                return {
                    "label": label,
                    "segments": candidate_segments,
                    "evaluation": evaluation,
                    "evaluation_model": evaluation_model,
                    "metrics": metrics,
                    "pronunciation": pronunciation,
                }

            await self._set_stage(job_id, "evaluating_candidates")
            # Free OpenRouter routes commonly throttle simultaneous structured-output
            # requests. Evaluate candidates independently and sequentially so one report
            # cannot consume the route capacity required by the other.
            results = []
            for candidate_label in ("A", "B"):
                results.append(
                    await self._await_with_heartbeat(
                        job_id,
                        evaluate_candidate(candidate_label),
                    )
                )

            await self._set_stage(job_id, "building_report")
            async with self.database.sessions() as write_db:
                write_job = await write_db.scalar(
                    select(ProcessingJob).where(ProcessingJob.id == job_id)
                )
                write_session = await write_db.scalar(
                    select(PracticeSession).where(PracticeSession.id == session.id)
                )
                if not write_job or not write_session:
                    raise RuntimeError("Part 3 session disappeared while building reports")
                await write_db.execute(
                    delete(Part3CandidateResult).where(
                        Part3CandidateResult.session_id == session.id
                    )
                )
                for result in results:
                    evaluation = result["evaluation"]
                    segments = result["segments"]
                    write_db.add(
                        Part3CandidateResult(
                            session_id=session.id,
                            candidate_label=str(result["label"]),
                            transcript=[
                                {
                                    "id": f"{session.id}-{result['label']}-{index}",
                                    "position": index,
                                    "start_ms": item.start_ms,
                                    "end_ms": item.end_ms,
                                    "text": item.text,
                                    "confidence": item.confidence,
                                }
                                for index, item in enumerate(segments)
                            ],
                            evaluation=evaluation.model_dump(mode="json"),
                            pronunciation=result["pronunciation"],
                            objective_metrics=result["metrics"],
                            model_snapshot={
                                "diarization": diarization.model_name,
                                "evaluation": str(result["evaluation_model"]),
                                "pronunciation": "withheld-part3-prototype",
                            },
                        )
                    )
                write_pair_recording = await write_db.scalar(
                    select(Recording).where(Recording.id == pair_recording.id)
                )
                if write_pair_recording is not None:
                    write_pair_recording.duration_ms = int(audio_metrics["recorded_duration_ms"])
                write_session.status = "completed"
                write_session.last_error_code = None
                write_job.status = "completed"
                completed_at = utcnow()
                write_job.processing_stage = "completed"
                write_job.stage_started_at = completed_at
                write_job.heartbeat_at = completed_at
                write_job.completed_at = completed_at
                write_job.last_error_code = None
                write_job.last_error_detail = None
                await write_db.commit()

    async def _mark_failed(self, job_id: str, exc: Exception) -> None:
        async with self.database.sessions() as db:
            job = await db.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id))
            if not job:
                return
            job.status = "failed"
            failed_at = utcnow()
            job.processing_stage = "failed"
            job.stage_started_at = failed_at
            job.heartbeat_at = failed_at
            job.last_error_code = type(exc).__name__[:64]
            job.last_error_detail = str(exc)[:500]
            session = await db.scalar(
                select(PracticeSession).where(PracticeSession.id == job.session_id)
            )
            if session:
                session.status = "failed"
                session.last_error_code = job.last_error_code
            await db.commit()

    async def cleanup_expired_sessions(self) -> int:
        async with self.database.sessions() as db:
            sessions = list(
                (
                    await db.scalars(
                        select(PracticeSession)
                        .options(selectinload(PracticeSession.recordings))
                        .where(PracticeSession.expires_at < datetime.now(UTC))
                    )
                ).all()
            )
            for session in sessions:
                storage_delete_failed = False
                for recording in session.recordings:
                    try:
                        await self.storage.delete(recording.storage_path)
                    except Exception:  # noqa: BLE001 - retain the path and retry cleanup later
                        storage_delete_failed = True
                if storage_delete_failed:
                    continue
                await db.delete(session)
            await db.commit()
            return len(sessions)


def _all_observations(evaluation: Any) -> list[Observation]:
    return [
        *evaluation.strengths,
        *evaluation.priority_improvements,
        *evaluation.grammar_vocabulary.observations,
        *evaluation.discourse_management.observations,
        *(
            evaluation.interactive_communication.observations
            if evaluation.interactive_communication
            else []
        ),
    ]


def _enrich_metrics(
    audio_metrics: dict[str, object],
    transcription: TranscriptionResult,
    session: PracticeSession,
) -> dict[str, object]:
    transcript_text = " ".join(item.text for item in transcription.segments)
    metrics = enrich_objective_metrics(
        audio_metrics,
        transcript_text,
        len(transcription.segments),
        session.task.photo_one_keywords,
        session.task.photo_two_keywords,
    )
    if transcription.detected_language:
        metrics["detected_language"] = transcription.detected_language
    metrics["speaking_part"] = session.task.part
    metrics["task_questions"] = session.task.questions
    if audio_metrics.get("signal_analysis_available") is False:
        metrics["metrics_source"] = "demo_signal_analysis_unavailable"
    return metrics


def _unavailable_demo_audio_metrics(declared_duration_ms: int | None) -> dict[str, object]:
    return {
        "recorded_duration_ms": max(0, int(declared_duration_ms or 0)),
        "detected_speech_duration_ms": 0,
        "silence_duration_ms": 0,
        "long_pauses": [],
        "long_pause_count": 0,
        "largest_pause_ms": 0,
        "signal_analysis_available": False,
        "audio_quality": {
            "sufficient_for_pronunciation": False,
            "reasons_es": [
                "El modo demo no dispone del códec local necesario para analizar la señal."
            ],
        },
    }


def _audio_evaluation_block_reason(audio_metrics: dict[str, object]) -> str | None:
    duration = int(audio_metrics.get("recorded_duration_ms", 0))
    speech = int(audio_metrics.get("detected_speech_duration_ms", 0))
    if duration < 5_000:
        return (
            "RESPUESTA NO EVALUABLE: la grabación es demasiado corta para emitir un análisis "
            "lingüístico responsable."
        )
    if speech < 3_000:
        return "RESPUESTA NO EVALUABLE: se ha detectado silencio o menos de tres segundos de habla."
    quality = audio_metrics.get("audio_quality", {})
    if not isinstance(quality, dict):
        return "RESPUESTA NO EVALUABLE: no se pudo comprobar la calidad de la señal."
    signal_dbfs = float(quality.get("signal_rms_dbfs", 0.0))
    snr_db = float(quality.get("estimated_snr_db", 100.0))
    clipping_ratio = float(quality.get("clipping_ratio", 0.0))
    if signal_dbfs < -55 or snr_db < 3 or clipping_ratio > 0.2:
        return (
            "RESPUESTA NO EVALUABLE: la señal es demasiado débil, ruidosa o saturada para "
            "sostener una evaluación fiable."
        )
    return None


def _transcript_evaluation_block_reason(
    transcription: TranscriptionResult, metrics: dict[str, object]
) -> str | None:
    language = (transcription.detected_language or "").strip().casefold()
    if language and language != "english" and not language.startswith("en"):
        return f"RESPUESTA NO EVALUABLE: el idioma principal detectado no es inglés ({language})."
    if int(metrics.get("word_count", 0)) < 3:
        return (
            "RESPUESTA NO EVALUABLE: la transcripción contiene menos de tres palabras inglesas "
            "utilizables."
        )
    return None
