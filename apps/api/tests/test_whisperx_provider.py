from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app.config import Settings
from app.providers.factory import create_diarization_provider
from app.providers.whisperx_provider import WhisperXDiarizationProvider


def whisperx_settings(python_path: Path, bridge_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        diarization_provider="whisperx",
        whisperx_python_path=python_path,
        whisperx_bridge_path=bridge_path,
        whisperx_device="cpu",
        whisperx_compute_type="int8",
    )


def test_whisperx_availability_requires_both_local_executables(tmp_path: Path) -> None:
    bridge_path = tmp_path / "bridge.py"
    settings = whisperx_settings(Path(sys.executable), bridge_path)
    assert settings.diarization_available is False

    bridge_path.write_text("# test bridge", encoding="utf-8")
    assert settings.diarization_available is True
    assert isinstance(create_diarization_provider(settings), WhisperXDiarizationProvider)


@pytest.mark.asyncio
async def test_whisperx_provider_runs_isolated_bridge_and_parses_two_speakers(
    tmp_path: Path,
) -> None:
    bridge_path = tmp_path / "fake_bridge.py"
    bridge_path.write_text(
        """
import argparse
import json

parser = argparse.ArgumentParser()
parser.add_argument('--audio')
parser.add_argument('--candidate-a-reference')
parser.add_argument('--candidate-b-reference')
parser.add_argument('--output')
parser.add_argument('--model')
parser.add_argument('--device')
parser.add_argument('--compute-type')
parser.add_argument('--batch-size')
args = parser.parse_args()
payload = {
    'provider_name': 'whisperx-pyannote',
    'model_name': 'whisperx:small.en+pyannote:community-1',
    'detected_language': 'en',
    'segments': [
        {'start_ms': 100, 'end_ms': 2100, 'text': 'I agree.', 'confidence': 0.94, 'speaker': 'A'},
        {'start_ms': 2200, 'end_ms': 4300, 'text': 'What about this?', 'confidence': 0.91, 'speaker': 'B'},
    ],
}
with open(args.output, 'w', encoding='utf-8') as output:
    json.dump(payload, output)
""".strip(),
        encoding="utf-8",
    )
    provider = WhisperXDiarizationProvider(whisperx_settings(Path(sys.executable), bridge_path))

    result = await provider.transcribe_pair(
        content=b"pair",
        filename="pair.webm",
        mime_type="audio/webm;codecs=opus",
        candidate_a_reference=b"a",
        candidate_a_reference_mime="audio/webm;codecs=opus",
        candidate_b_reference=b"b",
        candidate_b_reference_mime="audio/webm;codecs=opus",
    )

    assert result.provider_name == "whisperx-pyannote"
    assert result.detected_language == "en"
    assert [segment.speaker for segment in result.segments] == ["A", "B"]
    assert result.segments[0].text == "I agree."
    assert json.loads(json.dumps(result.segments[1].confidence)) == 0.91
