from __future__ import annotations

import argparse
import gc
import json
import os
import re
import time
from itertools import permutations
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def add_windows_dll_directories() -> list[object]:
    if os.name != "nt":
        return []

    candidates: list[Path] = []
    configured = os.environ.get("WHISPERX_FFMPEG_BIN")
    if configured:
        candidates.append(Path(configured))
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        candidates.extend(
            sorted(packages.glob("Gyan.FFmpeg.Shared_*/*7.1.1*full_build-shared/bin"))
        )
    ffmpeg_bin = next((path for path in candidates if path.is_dir()), None)
    if ffmpeg_bin is None:
        raise RuntimeError("FFmpeg shared libraries were not found.")

    torch_lib = PROJECT_ROOT / ".whisperx-venv" / "Lib" / "site-packages" / "torch" / "lib"
    if not torch_lib.is_dir():
        raise RuntimeError("WhisperX torch libraries were not found.")
    os.environ["PATH"] = f"{ffmpeg_bin}{os.pathsep}{os.environ.get('PATH', '')}"
    return [os.add_dll_directory(str(ffmpeg_bin)), os.add_dll_directory(str(torch_lib))]


DLL_HANDLES = add_windows_dll_directories()

import numpy as np  # noqa: E402
import torch  # noqa: E402
import whisperx  # noqa: E402
from huggingface_hub import get_token  # noqa: E402
from whisperx.diarize import DiarizationPipeline  # noqa: E402


def cosine(left: Any, right: Any) -> float:
    left_array = np.asarray(left, dtype=np.float32)
    right_array = np.asarray(right, dtype=np.float32)
    denominator = np.linalg.norm(left_array) * np.linalg.norm(right_array)
    if denominator == 0:
        return -1.0
    return float(np.dot(left_array, right_array) / denominator)


def reference_embedding(pipeline: DiarizationPipeline, path: Path) -> Any:
    _, embeddings = pipeline(str(path), num_speakers=1, return_embeddings=True)
    if not embeddings or len(embeddings) != 1:
        raise RuntimeError(f"Could not obtain one voice embedding for {path.name}.")
    return next(iter(embeddings.values()))


def best_mapping(
    conversation_embeddings: dict[str, Any], reference_embeddings: dict[str, Any]
) -> dict[str, str]:
    speakers = sorted(conversation_embeddings)
    candidates = sorted(reference_embeddings)
    if len(speakers) != 2:
        raise RuntimeError(f"Expected two speakers; found {len(speakers)}.")
    scores = {
        speaker: {
            candidate: cosine(conversation_embeddings[speaker], reference_embeddings[candidate])
            for candidate in candidates
        }
        for speaker in speakers
    }
    assignment = max(
        permutations(candidates),
        key=lambda choice: sum(
            scores[speaker][candidate] for speaker, candidate in zip(speakers, choice, strict=True)
        ),
    )
    return dict(zip(speakers, assignment, strict=True))


def clean_text(words: list[str]) -> str:
    text = " ".join(word.strip() for word in words if word.strip())
    return re.sub(r"\s+([.,!?;:])", r"\1", text).strip()


def build_turns(attributed: dict[str, Any], mapping: dict[str, str]) -> list[dict[str, Any]]:
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
        text = clean_text(turn["words"])
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--candidate-a-reference", type=Path, required=True)
    parser.add_argument("--candidate-b-reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="small.en")
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--compute-type", default="float16")
    parser.add_argument("--batch-size", type=int, default=8)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    token = os.environ.get("HF_TOKEN") or get_token()
    if not token:
        raise RuntimeError("Hugging Face authorization is missing from the local credential store.")
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available to the local WhisperX worker.")

    timings: dict[str, float] = {}
    started = time.perf_counter()
    audio = whisperx.load_audio(str(args.audio))
    asr_model = whisperx.load_model(
        args.model,
        args.device,
        compute_type=args.compute_type,
        language="en",
        vad_method="silero",
    )
    transcript = asr_model.transcribe(audio, batch_size=args.batch_size, language="en")
    timings["transcription_seconds"] = time.perf_counter() - started
    del asr_model
    gc.collect()
    if args.device == "cuda":
        torch.cuda.empty_cache()

    started = time.perf_counter()
    align_model, metadata = whisperx.load_align_model(language_code="en", device=args.device)
    aligned = whisperx.align(
        transcript["segments"],
        align_model,
        metadata,
        audio,
        args.device,
        return_char_alignments=False,
    )
    timings["alignment_seconds"] = time.perf_counter() - started
    del align_model
    gc.collect()
    if args.device == "cuda":
        torch.cuda.empty_cache()

    started = time.perf_counter()
    diarizer = DiarizationPipeline(token=token, device=args.device)
    diarization, embeddings = diarizer(audio, num_speakers=2, return_embeddings=True)
    if not embeddings:
        raise RuntimeError("No conversation voice embeddings were returned.")
    references = {
        "A": reference_embedding(diarizer, args.candidate_a_reference),
        "B": reference_embedding(diarizer, args.candidate_b_reference),
    }
    mapping = best_mapping(embeddings, references)
    attributed = whisperx.assign_word_speakers(diarization, aligned, embeddings, fill_nearest=True)
    turns = build_turns(attributed, mapping)
    timings["diarization_seconds"] = time.perf_counter() - started
    if {turn["speaker"] for turn in turns} != {"A", "B"}:
        raise RuntimeError("The recording does not contain two identifiable candidate voices.")

    args.output.write_text(
        json.dumps(
            {
                "provider_name": "whisperx-pyannote",
                "model_name": f"whisperx:{args.model}+pyannote:community-1",
                "detected_language": transcript.get("language", "en"),
                "segments": turns,
                "timings": timings,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
