from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.config import Settings
from app.providers.base import TranscribedSegment, TranscriptionResult

logger = logging.getLogger(__name__)


def _audio_suffix(mime_type: str, fallback: str = ".webm") -> str:
    normalised = mime_type.split(";", maxsplit=1)[0].strip().lower()
    return {
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/ogg": ".ogg",
        "audio/webm": ".webm",
    }.get(normalised, fallback)


class WhisperXDiarizationProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

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
        python_path = self.settings.resolve_project_path(self.settings.whisperx_python_path)
        bridge_path = self.settings.resolve_project_path(self.settings.whisperx_bridge_path)
        if not python_path.is_file() or not bridge_path.is_file():
            raise RuntimeError("El separador local de voces no está instalado.")

        with tempfile.TemporaryDirectory(prefix="b2-whisperx-") as directory:
            workdir = Path(directory)
            pair_suffix = Path(filename).suffix or _audio_suffix(mime_type)
            pair_path = workdir / f"pair{pair_suffix}"
            reference_a_path = workdir / f"candidate-a{_audio_suffix(candidate_a_reference_mime)}"
            reference_b_path = workdir / f"candidate-b{_audio_suffix(candidate_b_reference_mime)}"
            output_path = workdir / "result.json"
            pair_path.write_bytes(content)
            reference_a_path.write_bytes(candidate_a_reference)
            reference_b_path.write_bytes(candidate_b_reference)

            command = [
                str(python_path),
                str(bridge_path),
                "--audio",
                str(pair_path),
                "--candidate-a-reference",
                str(reference_a_path),
                "--candidate-b-reference",
                str(reference_b_path),
                "--output",
                str(output_path),
                "--model",
                self.settings.whisperx_model,
                "--device",
                self.settings.whisperx_device,
                "--compute-type",
                self.settings.whisperx_compute_type,
                "--batch-size",
                str(self.settings.whisperx_batch_size),
            ]
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

            def run_worker() -> subprocess.CompletedProcess[bytes]:
                return subprocess.run(  # noqa: S603 - executable and arguments are controlled
                    command,
                    capture_output=True,
                    timeout=self.settings.whisperx_timeout_seconds,
                    creationflags=creationflags,
                    check=False,
                )

            try:
                process = await asyncio.to_thread(run_worker)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    "La separación local de voces ha superado el tiempo máximo."
                ) from exc

            if process.returncode != 0 or not output_path.is_file():
                diagnostic = (process.stderr or process.stdout).decode("utf-8", errors="replace")[
                    -2_000:
                ]
                logger.error(
                    "WhisperX worker failed with code %s: %s", process.returncode, diagnostic
                )
                raise RuntimeError("WhisperX no ha podido transcribir y separar las dos voces.")

            payload: dict[str, Any] = json.loads(output_path.read_text(encoding="utf-8"))

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
            raise RuntimeError("No se han podido identificar con seguridad las dos voces.")
        return TranscriptionResult(
            segments=segments,
            provider_name=str(payload.get("provider_name", "whisperx-pyannote")),
            model_name=str(payload.get("model_name", self.settings.whisperx_model)),
            detected_language=str(payload.get("detected_language", "en")),
        )
