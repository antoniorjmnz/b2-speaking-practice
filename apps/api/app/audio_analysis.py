from __future__ import annotations

import io
import math
import re
import wave
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DecodedAudio:
    samples: np.ndarray
    sample_rate: int
    wav_bytes: bytes


def _to_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    pcm = np.clip(samples, -1, 1)
    pcm16 = (pcm * 32767).astype("<i2")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm16.tobytes())
    return output.getvalue()


def _decode_wav(content: bytes) -> DecodedAudio:
    with wave.open(io.BytesIO(content), "rb") as wav:
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        width = wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())
    if width != 2:
        raise ValueError("Only 16-bit PCM WAV is supported without PyAV")
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return DecodedAudio(
        samples=samples, sample_rate=sample_rate, wav_bytes=_to_wav(samples, sample_rate)
    )


def decode_audio(content: bytes) -> DecodedAudio:
    if content.startswith(b"RIFF") and content[8:12] == b"WAVE":
        return _decode_wav(content)
    try:
        import av
        from av.audio.resampler import AudioResampler
    except ImportError as exc:
        raise RuntimeError("PyAV is required to analyse compressed browser audio") from exc

    container = av.open(io.BytesIO(content))
    stream = next((item for item in container.streams if item.type == "audio"), None)
    if stream is None:
        raise ValueError("The uploaded file contains no audio stream")
    resampler = AudioResampler(format="s16", layout="mono", rate=16_000)
    blocks: list[np.ndarray] = []
    for frame in container.decode(stream):
        for converted in resampler.resample(frame):
            block = converted.to_ndarray().reshape(-1).astype(np.float32) / 32768.0
            blocks.append(block)
    if not blocks:
        raise ValueError("The uploaded audio stream is empty")
    samples = np.concatenate(blocks)
    return DecodedAudio(samples=samples, sample_rate=16_000, wav_bytes=_to_wav(samples, 16_000))


def _dbfs(value: float) -> float:
    return round(20 * math.log10(max(value, 1e-8)), 2)


def analyse_audio(decoded: DecodedAudio) -> dict[str, object]:
    samples = decoded.samples
    sample_rate = decoded.sample_rate
    window_size = max(1, int(sample_rate * 0.03))
    usable = samples[: len(samples) - (len(samples) % window_size)]
    if usable.size == 0:
        raise ValueError("Audio is too short to analyse")
    windows = usable.reshape(-1, window_size)
    rms = np.sqrt(np.mean(np.square(windows), axis=1) + 1e-12)
    noise_floor = float(np.percentile(rms, 20))
    threshold = max(0.012, noise_floor * 2.8)
    speech = rms >= threshold

    # Fill very small gaps so that consonant closures are not counted as pauses.
    for index in range(1, len(speech) - 1):
        if not speech[index] and speech[index - 1] and speech[index + 1]:
            speech[index] = True

    recorded_duration = len(samples) / sample_rate
    speech_duration = float(np.count_nonzero(speech) * 0.03)
    silence_duration = max(0.0, recorded_duration - speech_duration)
    speech_indexes = np.flatnonzero(speech)
    long_pauses: list[dict[str, int]] = []
    if speech_indexes.size:
        cursor = int(speech_indexes[0])
        last = int(speech_indexes[-1])
        while cursor <= last:
            if speech[cursor]:
                cursor += 1
                continue
            start = cursor
            while cursor <= last and not speech[cursor]:
                cursor += 1
            duration_ms = (cursor - start) * 30
            if duration_ms >= 800:
                long_pauses.append(
                    {"start_ms": start * 30, "end_ms": cursor * 30, "duration_ms": duration_ms}
                )

    peak = float(np.max(np.abs(samples)))
    clipping_ratio = float(np.mean(np.abs(samples) >= 0.99))
    signal_rms = float(np.sqrt(np.mean(np.square(samples)) + 1e-12))
    estimated_snr = 20 * math.log10(max(signal_rms, 1e-8) / max(noise_floor, 1e-8))
    reasons: list[str] = []
    if recorded_duration < 5:
        reasons.append("La grabación es demasiado corta.")
    if speech_duration < 3:
        reasons.append("Se ha detectado muy poco habla.")
    if signal_rms < 0.006:
        reasons.append("El nivel de la señal es demasiado bajo.")
    if clipping_ratio > 0.04:
        reasons.append("La grabación presenta saturación.")
    if estimated_snr < 7:
        reasons.append("El ruido de fondo dificulta el análisis.")

    return {
        "recorded_duration_ms": round(recorded_duration * 1000),
        "detected_speech_duration_ms": round(speech_duration * 1000),
        "silence_duration_ms": round(silence_duration * 1000),
        "long_pauses": long_pauses,
        "long_pause_count": len(long_pauses),
        "largest_pause_ms": max((pause["duration_ms"] for pause in long_pauses), default=0),
        "audio_quality": {
            "sufficient_for_pronunciation": not reasons,
            "reasons_es": reasons,
            "signal_rms_dbfs": _dbfs(signal_rms),
            "noise_floor_dbfs": _dbfs(noise_floor),
            "estimated_snr_db": round(estimated_snr, 2),
            "peak_dbfs": _dbfs(peak),
            "clipping_ratio": round(clipping_ratio, 6),
            "sample_rate_hz": sample_rate,
        },
    }


def deterministic_mock_audio_metrics() -> dict[str, object]:
    return {
        "recorded_duration_ms": 60_000,
        "detected_speech_duration_ms": 49_800,
        "silence_duration_ms": 10_200,
        "long_pauses": [{"start_ms": 34_900, "end_ms": 36_100, "duration_ms": 1_200}],
        "long_pause_count": 1,
        "largest_pause_ms": 1_200,
        "audio_quality": {
            "sufficient_for_pronunciation": True,
            "reasons_es": [],
            "signal_rms_dbfs": -21.4,
            "noise_floor_dbfs": -43.1,
            "estimated_snr_db": 21.7,
            "peak_dbfs": -4.2,
            "clipping_ratio": 0.0001,
            "sample_rate_hz": 48_000,
        },
    }


WORD_PATTERN = re.compile(r"\b[A-Za-z]+(?:['’][A-Za-z]+)?\b")


def enrich_objective_metrics(
    audio_metrics: dict[str, object],
    transcript_text: str,
    segment_count: int,
    photo_one_keywords: list[str],
    photo_two_keywords: list[str],
) -> dict[str, object]:
    words = WORD_PATTERN.findall(transcript_text)
    duration_ms = int(audio_metrics["recorded_duration_ms"])
    normalized = transcript_text.casefold()
    photo_one = any(keyword.casefold() in normalized for keyword in photo_one_keywords)
    photo_two = any(keyword.casefold() in normalized for keyword in photo_two_keywords)
    result = dict(audio_metrics)
    result.update(
        {
            "word_count": len(words),
            "approx_words_per_minute": round(len(words) * 60_000 / max(duration_ms, 1), 1),
            "transcript_segment_count": segment_count,
            "photo_one_mentioned": photo_one,
            "photo_two_mentioned": photo_two,
            "both_photographs_mentioned": photo_one and photo_two,
            # Compact visual context for the evaluator. These are reference
            # terms, never candidate evidence.
            "photo_one_reference_terms": photo_one_keywords,
            "photo_two_reference_terms": photo_two_keywords,
            "metrics_source": "signal_analysis_and_deterministic_rules",
        }
    )
    return result
