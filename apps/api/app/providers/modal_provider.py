from __future__ import annotations

import asyncio
from typing import Any

import modal

from app.config import Settings
from app.providers.base import TranscribedSegment, TranscriptionResult


class ModalDiarizationProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _invoke(
        self,
        *,
        content: bytes,
        candidate_a_reference: bytes,
        candidate_b_reference: bytes,
        content_url: str | None,
        candidate_a_reference_url: str | None,
        candidate_b_reference_url: str | None,
    ) -> dict[str, Any]:
        worker_class = modal.Cls.from_name(
            self.settings.modal_app_name,
            self.settings.modal_class_name,
            environment_name=self.settings.modal_environment_name,
        )
        worker = worker_class()
        urls = (content_url, candidate_a_reference_url, candidate_b_reference_url)
        if all(url and url.startswith("https://") for url in urls):
            return worker.transcribe_pair_urls.remote(*urls)
        return worker.transcribe_pair.remote(
            content,
            candidate_a_reference,
            candidate_b_reference,
        )

    async def transcribe_pair(
        self,
        *,
        content: bytes,
        filename: str,
        mime_type: str,
        candidate_a_reference: bytes,
        candidate_a_reference_mime: str,
        candidate_b_reference: bytes,
        candidate_b_reference_mime: str,
        content_url: str | None = None,
        candidate_a_reference_url: str | None = None,
        candidate_b_reference_url: str | None = None,
    ) -> TranscriptionResult:
        try:
            payload = await asyncio.wait_for(
                asyncio.to_thread(
                    self._invoke,
                    content=content,
                    candidate_a_reference=candidate_a_reference,
                    candidate_b_reference=candidate_b_reference,
                    content_url=content_url,
                    candidate_a_reference_url=candidate_a_reference_url,
                    candidate_b_reference_url=candidate_b_reference_url,
                ),
                timeout=self.settings.modal_timeout_seconds,
            )
        except TimeoutError as exc:
            raise RuntimeError("El worker GPU ha superado el tiempo máximo de análisis.") from exc
        except Exception as exc:
            raise RuntimeError("El worker GPU no ha podido separar las dos voces.") from exc

        segments = [
            TranscribedSegment(
                start_ms=int(segment["start_ms"]),
                end_ms=int(segment["end_ms"]),
                text=str(segment["text"]).strip(),
                confidence=(
                    float(segment["confidence"]) if segment.get("confidence") is not None else None
                ),
                speaker=str(segment["speaker"]),
            )
            for segment in payload.get("segments", [])
            if segment.get("text") and segment.get("speaker") in {"A", "B"}
        ]
        if not segments or {segment.speaker for segment in segments} != {"A", "B"}:
            raise RuntimeError("El worker GPU no ha identificado con seguridad ambas voces.")
        return TranscriptionResult(
            segments=segments,
            provider_name=str(payload.get("provider_name", "modal-whisperx-pyannote")),
            model_name=str(payload.get("model_name", self.settings.whisperx_model)),
            detected_language=str(payload.get("detected_language", "en")),
        )
