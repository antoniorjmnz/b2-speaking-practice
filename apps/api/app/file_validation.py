from __future__ import annotations

import hashlib

ALLOWED_MIME_TYPES = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mp4": "mp4",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
}


def sniff_audio_type(content: bytes) -> str | None:
    if content.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    if content.startswith(b"OggS"):
        return "ogg"
    if content.startswith(b"RIFF") and content[8:12] == b"WAVE":
        return "wav"
    if len(content) >= 12 and content[4:8] == b"ftyp":
        return "mp4"
    return None


def validate_audio_content(content: bytes, claimed_mime: str, max_bytes: int) -> str:
    if not content or len(content) > max_bytes:
        raise ValueError("Audio size is outside the accepted range")
    expected = ALLOWED_MIME_TYPES.get(claimed_mime.split(";", 1)[0].strip().lower())
    actual = sniff_audio_type(content)
    if expected is None or actual is None:
        raise ValueError("Unsupported audio type")
    if expected == "m4a":
        expected = "mp4"
    if expected != actual:
        raise ValueError("Audio signature does not match the declared MIME type")
    return actual


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
