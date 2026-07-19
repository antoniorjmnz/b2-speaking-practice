from __future__ import annotations

import json
import re
import tempfile
import urllib.request
from itertools import permutations
from pathlib import Path
from typing import Any

import modal

APP_NAME = "b2-speaking-whisperx"
MODEL_NAME = "large-v3-turbo"
CACHE_PATH = "/model-cache"
MAX_AUDIO_BYTES = 12 * 1024 * 1024

app = modal.App(APP_NAME)
model_cache = modal.Volume.from_name("b2-speaking-model-cache", create_if_missing=True)
huggingface_secret = modal.Secret.from_name("b2-speaking-huggingface")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1")
    .run_commands(
        "python -m pip install --no-cache-dir "
        "torch==2.8.0 torchaudio==2.8.0 "
        "--index-url https://download.pytorch.org/whl/cu128"
    )
    .pip_install(
        "huggingface-hub>=0.34,<2",
        "numpy>=2.0,<3",
        "pyannote.audio==4.0.7",
        "whisperx==3.8.6",
    )
)


def _cosine(left: Any, right: Any) -> float:
    import numpy as np

    left_array = np.asarray(left, dtype=np.float32)
    right_array = np.asarray(right, dtype=np.float32)
    denominator = np.linalg.norm(left_array) * np.linalg.norm(right_array)
    if denominator == 0:
        return -1.0
    return float(np.dot(left_array, right_array) / denominator)


def _reference_embedding(pipeline: Any, path: Path) -> Any:
    _, embeddings = pipeline(str(path), num_speakers=1, return_embeddings=True)
    if not embeddings or len(embeddings) != 1:
        raise RuntimeError(f"Could not obtain one embedding for {path.name}.")
    return next(iter(embeddings.values()))


def _best_mapping(
    conversation_embeddings: dict[str, Any], reference_embeddings: dict[str, Any]
) -> dict[str, str]:
    speakers = sorted(conversation_embeddings)
    candidates = sorted(reference_embeddings)
    if len(speakers) != 2:
        raise RuntimeError(f"Expected exactly two speakers; found {len(speakers)}.")
    scores = {
        speaker: {
            candidate: _cosine(
                conversation_embeddings[speaker], reference_embeddings[candidate]
            )
            for candidate in candidates
        }
        for speaker in speakers
    }
    assignment = max(
        permutations(candidates),
        key=lambda choice: sum(
            scores[speaker][candidate]
            for speaker, candidate in zip(speakers, choice, strict=True)
        ),
    )
    return dict(zip(speakers, assignment, strict=True))


def _clean_text(words: list[str]) -> str:
    text = " ".join(word.strip() for word in words if word.strip())
    return re.sub(r"\s+([.,!?;:])", r"\1", text).strip()


def _build_turns(attributed: dict[str, Any], mapping: dict[str, str]) -> list[dict[str, Any]]:
    labelled_words: list[dict[str, Any]] = []
    for segment in attributed.get("segments", []):
        segment_speaker = mapping.get(segment.get("speaker"))
        for word in segment.get("words", []):
            speaker = mapping.get(word.get("speaker")) or segment_speaker
            if speaker not in {"A", "B"} or "start" not in word:
                continue
            labelled_words.append(
                {
                    "speaker": speaker,
                    "start": float(word["start"]),
                    "end": float(word.get("end", word["start"])),
                    "word": str(word.get("word", "")),
                    "score": word.get("score"),
                }
            )

    turns: list[dict[str, Any]] = []
    for word in labelled_words:
        previous = turns[-1] if turns else None
        starts_new_turn = (
            previous is None
            or previous["speaker"] != word["speaker"]
            or word["start"] - previous["end"] > 1.5
        )
        if starts_new_turn:
            turns.append(
                {
                    "speaker": word["speaker"],
                    "start": word["start"],
                    "end": word["end"],
                    "words": [word["word"]],
                    "scores": [word["score"]] if word["score"] is not None else [],
                }
            )
            continue
        previous["end"] = max(previous["end"], word["end"])
        previous["words"].append(word["word"])
        if word["score"] is not None:
            previous["scores"].append(word["score"])

    result: list[dict[str, Any]] = []
    for turn in turns:
        text = _clean_text(turn["words"])
        if not text:
            continue
        scores = turn["scores"]
        result.append(
            {
                "start_ms": round(turn["start"] * 1_000),
                "end_ms": round(turn["end"] * 1_000),
                "text": text,
                "confidence": float(sum(scores) / len(scores)) if scores else None,
                "speaker": turn["speaker"],
            }
        )
    return result


def _download_audio(url: str) -> bytes:
    if not url.startswith("https://"):
        raise ValueError("Only HTTPS audio URLs are accepted.")
    request = urllib.request.Request(  # noqa: S310 - URL is restricted to HTTPS above
        url, headers={"User-Agent": "B2-Speaking-Worker/1.0"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        content = response.read(MAX_AUDIO_BYTES + 1)
    if len(content) > MAX_AUDIO_BYTES:
        raise ValueError("Audio exceeds the worker size limit.")
    return content


@app.cls(
    image=image,
    gpu="T4",
    timeout=10 * 60,
    scaledown_window=2 * 60,
    volumes={CACHE_PATH: model_cache},
    secrets=[huggingface_secret],
)
class WhisperXWorker:
    @modal.enter()
    def load_models(self) -> None:
        import os

        os.environ["HF_HOME"] = f"{CACHE_PATH}/huggingface"
        os.environ["TORCH_HOME"] = f"{CACHE_PATH}/torch"
        os.environ["XDG_CACHE_HOME"] = CACHE_PATH
        import torch
        import whisperx
        from whisperx.diarize import DiarizationPipeline

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available in the Modal worker.")
        token = os.environ.get("HF_TOKEN")
        if not token:
            raise RuntimeError("The Hugging Face secret is missing.")

        self.whisperx = whisperx
        self.device = "cuda"
        self.asr_model = whisperx.load_model(
            MODEL_NAME,
            self.device,
            compute_type="float16",
            language="en",
            vad_method="silero",
        )
        self.align_model, self.align_metadata = whisperx.load_align_model(
            language_code="en", device=self.device
        )
        self.diarizer = DiarizationPipeline(token=token, device=self.device)

    def _process(self, pair_audio: bytes, reference_a: bytes, reference_b: bytes) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="b2-speaking-") as directory:
            root = Path(directory)
            pair_path = root / "pair.webm"
            reference_a_path = root / "candidate-a.webm"
            reference_b_path = root / "candidate-b.webm"
            pair_path.write_bytes(pair_audio)
            reference_a_path.write_bytes(reference_a)
            reference_b_path.write_bytes(reference_b)

            audio = self.whisperx.load_audio(str(pair_path))
            transcript = self.asr_model.transcribe(audio, batch_size=8, language="en")
            aligned = self.whisperx.align(
                transcript["segments"],
                self.align_model,
                self.align_metadata,
                audio,
                self.device,
                return_char_alignments=False,
            )
            diarization, embeddings = self.diarizer(
                audio, num_speakers=2, return_embeddings=True
            )
            if not embeddings:
                raise RuntimeError("No conversation speaker embeddings were returned.")
            references = {
                "A": _reference_embedding(self.diarizer, reference_a_path),
                "B": _reference_embedding(self.diarizer, reference_b_path),
            }
            mapping = _best_mapping(embeddings, references)
            attributed = self.whisperx.assign_word_speakers(
                diarization, aligned, embeddings, fill_nearest=True
            )
            turns = _build_turns(attributed, mapping)

        if {turn["speaker"] for turn in turns} != {"A", "B"}:
            raise RuntimeError("The recording does not contain two identifiable voices.")
        return {
            "provider_name": "modal-whisperx-pyannote",
            "model_name": f"whisperx:{MODEL_NAME}+pyannote:community-1",
            "detected_language": transcript.get("language", "en"),
            "segments": turns,
        }

    @modal.method()
    def transcribe_pair(
        self, pair_audio: bytes, reference_a: bytes, reference_b: bytes
    ) -> dict[str, Any]:
        return self._process(pair_audio, reference_a, reference_b)

    @modal.method()
    def transcribe_pair_urls(
        self, pair_audio_url: str, reference_a_url: str, reference_b_url: str
    ) -> dict[str, Any]:
        return self._process(
            _download_audio(pair_audio_url),
            _download_audio(reference_a_url),
            _download_audio(reference_b_url),
        )


@app.local_entrypoint()
def main(
    audio_path: str,
    candidate_a_reference_path: str,
    candidate_b_reference_path: str,
) -> None:
    worker = WhisperXWorker()
    result = worker.transcribe_pair.remote(
        Path(audio_path).read_bytes(),
        Path(candidate_a_reference_path).read_bytes(),
        Path(candidate_b_reference_path).read_bytes(),
    )
    printable = {
        "provider_name": result["provider_name"],
        "model_name": result["model_name"],
        "detected_language": result["detected_language"],
        "segment_count": len(result["segments"]),
        "speakers": sorted({segment["speaker"] for segment in result["segments"]}),
        "first_segment": result["segments"][0],
    }
    print(json.dumps(printable, ensure_ascii=False, indent=2))
