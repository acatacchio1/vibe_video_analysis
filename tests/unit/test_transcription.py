"""
Unit tests for src/worker/transcription

Tests cover:
- extract_audio: ffmpeg command structure, success, no audio, timeout, errors
- transcribe_audio: device, compute types, language validation, transcribe params
- load_preexisting_transcript: suffix strip, path resolution, error handling
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.worker.transcription import (
    extract_audio,
    transcribe_audio,
    load_preexisting_transcript,
)


@pytest.mark.unit
class TestExtractAudio:
    """Tests for extract_audio function"""

    @patch("src.worker.transcription.subprocess.run")
    def test_happy_path(self, mock_run, tmp_path):
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        video = tmp_path / "video.mp4"
        audio = job_dir / "audio.wav"
        audio.write_bytes(b"fake_wav_data")

        mock_run.return_value = MagicMock(
            returncode=0, stderr="", stdout=""
        )

        result = extract_audio(str(video), str(job_dir))
        assert result == str(audio)
        # Verify ffmpeg command structure
        args = mock_run.call_args[0][0]
        assert "-vn" in args
        assert "-acodec" in args
        assert "pcm_s16le" in args
        assert "-ar" in args
        assert "16000" in args
        assert "-ac" in args
        assert "1" in args

    @patch("src.worker.transcription.subprocess.run")
    def test_no_audio_stream(self, mock_run, tmp_path):
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        video = tmp_path / "video.mp4"

        mock_run.return_value = MagicMock(
            returncode=2,
            stderr="Error: Video does not contain any stream",
        )

        result = extract_audio(str(video), str(job_dir))
        assert result == ""

    @patch("src.worker.transcription.subprocess.run")
    def test_no_audio_lowercase(self, mock_run, tmp_path):
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        video = tmp_path / "video.mp4"

        mock_run.return_value = MagicMock(
            returncode=2,
            stderr="Warning: no audio tracks found",
        )

        result = extract_audio(str(video), str(job_dir))
        assert result == ""

    @patch("src.worker.transcription.subprocess.run")
    def test_empty_output(self, mock_run, tmp_path):
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        video = tmp_path / "video.mp4"
        audio = job_dir / "audio.wav"
        audio.write_bytes(b"")  # 0 bytes

        mock_run.return_value = MagicMock(returncode=0, stderr="")

        result = extract_audio(str(video), str(job_dir))
        assert result == ""

    def test_timeout_with_partial_file(self, tmp_path):
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        video = tmp_path / "video.mp4"
        audio = job_dir / "audio.wav"
        audio.write_bytes(b"partial")

        with patch("src.worker.transcription.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("ffmpeg", 120)
            result = extract_audio(str(video), str(job_dir))

        assert result == str(audio)

    def test_timeout_no_partial_file(self, tmp_path):
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        video = tmp_path / "video.mp4"
        # No audio.wav created

        with patch("src.worker.transcription.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("ffmpeg", 120)
            result = extract_audio(str(video), str(job_dir))

        assert result == ""

    @patch("src.worker.transcription.subprocess.run")
    def test_ffmpeg_error_non_audio(self, mock_run, tmp_path):
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        video = tmp_path / "video.mp4"

        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="Unknown decoder error occurred",
        )

        result = extract_audio(str(video), str(job_dir))
        assert result == ""


@pytest.fixture
def mock_faster_whisper(monkeypatch):
    """Create a mock faster_whisper module with WhisperModel."""
    mock_fw = MagicMock()
    monkeypatch.setitem(sys.modules, "faster_whisper", mock_fw)
    monkeypatch.setitem(sys.modules, "faster_whisper.transcribe", MagicMock())
    return mock_fw


@pytest.mark.unit
class TestTranscribeAudio:
    """Tests for transcribe_audio function"""

    def test_happy_path(self, mock_faster_whisper, tmp_path):
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"fake_wav")

        seg1 = MagicMock(text="Hello world", start=0.0, end=1.5)
        seg2 = MagicMock(text="Goodbye", start=2.0, end=3.5)
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([seg1, seg2]), mock_info)
        mock_faster_whisper.WhisperModel.return_value = mock_model

        result = transcribe_audio(str(wav), whisper_model="large", language="en", device="cuda")

        mock_faster_whisper.WhisperModel.assert_called_once_with(
            model_size_or_path="large",
            device="cuda",
            compute_type="float16",
        )
        call_kwargs = mock_model.transcribe.call_args[1]
        assert call_kwargs["beam_size"] == 5
        assert call_kwargs["vad_filter"] is True
        assert call_kwargs["vad_parameters"] == {"min_silence_duration_ms": 500}
        assert call_kwargs["word_timestamps"] is False
        assert call_kwargs["language"] == "en"
        assert result["text"] == "Hello world Goodbye"
        assert len(result["segments"]) == 2
        assert result["segments"][0]["text"] == "Hello world"
        assert result["segments"][0]["start"] == 0.0
        assert result["segments"][0]["end"] == 1.5
        assert result["language"] == "en"
        assert result["whisper_model"] == "large"

    def test_gpu_device_converts_to_cuda(self, mock_faster_whisper, tmp_path):
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"fake")

        seg = MagicMock(text="Hi", start=0.0, end=1.0)
        mock_info = MagicMock()
        mock_info.language = "en"

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([seg]), mock_info)
        mock_faster_whisper.WhisperModel.return_value = mock_model

        transcribe_audio(str(wav), whisper_model="base", language="en", device="gpu")

        mock_faster_whisper.WhisperModel.assert_called_once_with(
            model_size_or_path="base",
            device="cuda",
            compute_type="float16",
        )

    def test_cpu_device_uses_int8(self, mock_faster_whisper, tmp_path):
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"fake")

        seg = MagicMock(text="Hi", start=0.0, end=1.0)
        mock_info = MagicMock()
        mock_info.language = "en"

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([seg]), mock_info)
        mock_faster_whisper.WhisperModel.return_value = mock_model

        transcribe_audio(str(wav), whisper_model="base", language="en", device="cpu")

        mock_faster_whisper.WhisperModel.assert_called_once_with(
            model_size_or_path="base",
            device="cpu",
            compute_type="int8",
        )

    def test_accepted_language_passed(self, mock_faster_whisper, tmp_path):
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"fake")

        seg = MagicMock(text="Hola", start=0.0, end=1.0)
        mock_info = MagicMock()
        mock_info.language = "es"

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([seg]), mock_info)
        mock_faster_whisper.WhisperModel.return_value = mock_model

        transcribe_audio(str(wav), whisper_model="large", language="es")

        kwargs = mock_model.transcribe.call_args[1]
        assert kwargs["language"] == "es"

    def test_unaccepted_language_auto_detect(self, mock_faster_whisper, tmp_path):
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"fake")

        seg = MagicMock(text="text", start=0.0, end=1.0)
        mock_info = MagicMock()
        mock_info.language = "en"

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([seg]), mock_info)
        mock_faster_whisper.WhisperModel.return_value = mock_model

        transcribe_audio(str(wav), whisper_model="large", language="xx")

        kwargs = mock_model.transcribe.call_args[1]
        assert kwargs["language"] is None

    def test_none_language_auto_detect(self, mock_faster_whisper, tmp_path):
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"fake")

        seg = MagicMock(text="text", start=0.0, end=1.0)
        mock_info = MagicMock()
        mock_info.language = "ja"

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([seg]), mock_info)
        mock_faster_whisper.WhisperModel.return_value = mock_model

        result = transcribe_audio(str(wav), whisper_model="large", language=None)

        call_kwargs = mock_model.transcribe.call_args[1]
        assert call_kwargs["language"] is None
        assert result["language"] == "ja"

    def test_transcribe_error_raises_runtime_error(self, mock_faster_whisper, tmp_path):
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"fake")

        mock_model = MagicMock()
        mock_model.transcribe.side_effect = ValueError("GPU out of memory")
        mock_faster_whisper.WhisperModel.return_value = mock_model

        with pytest.raises(RuntimeError, match="Whisper transcription failed"):
            transcribe_audio(str(wav), whisper_model="large")


@pytest.mark.unit
class TestLoadPreexistingTranscript:
    """Tests for load_preexisting_transcript function"""

    def test_happy_path(self, tmp_path):
        video_dir = tmp_path / "my_video"
        video_dir.mkdir()
        transcript = video_dir / "transcript.json"
        transcript.write_text(json.dumps({
            "text": "Hello world",
            "segments": [{"text": "Hello", "start": 0, "end": 1}],
            "language": "en",
        }))

        result = load_preexisting_transcript("my_video", str(tmp_path))
        assert result is not None
        assert result["text"] == "Hello world"
        assert len(result["segments"]) == 1

    def test_strip_720p_suffix(self, tmp_path):
        video_dir = tmp_path / "my_video"
        video_dir.mkdir()
        transcript = video_dir / "transcript.json"
        transcript.write_text(json.dumps({
            "text": "Text",
            "segments": [],
            "language": "en",
        }))

        result = load_preexisting_transcript("my_video_720p", str(tmp_path))
        assert result is not None
        assert result["text"] == "Text"

    def test_strip_dedup_suffix(self, tmp_path):
        video_dir = tmp_path / "my_video"
        video_dir.mkdir()
        transcript = video_dir / "transcript.json"
        transcript.write_text(json.dumps({
            "text": "Text",
            "segments": [],
            "language": "en",
        }))

        result = load_preexisting_transcript("my_video_dedup", str(tmp_path))
        assert result is not None

    def test_strip_dedup_720p_suffix_priority(self, tmp_path):
        # Both _dedup_720p and _720p and _dedup strip to same base
        video_dir = tmp_path / "my_video"
        video_dir.mkdir()
        transcript = video_dir / "transcript.json"
        transcript.write_text(json.dumps({
            "text": "Text",
            "segments": [],
            "language": "en",
        }))

        result = load_preexisting_transcript("my_video_dedup_720p", str(tmp_path))
        assert result is not None
        assert result["text"] == "Text"

    def test_not_found_returns_none(self, tmp_path):
        # No matching directory exists
        result = load_preexisting_transcript("nonexistent", str(tmp_path))
        assert result is None

    def test_invalid_json_returns_none(self, tmp_path):
        video_dir = tmp_path / "my_video"
        video_dir.mkdir()
        transcript = video_dir / "transcript.json"
        transcript.write_text("{invalid json")

        result = load_preexisting_transcript("my_video", str(tmp_path))
        assert result is None

    def test_invalid_json_fallback_to_base(self, tmp_path):
        # _720p dir has bad JSON, base dir has good JSON
        video_dir_suff = tmp_path / "my_video_720p"
        video_dir_suff.mkdir()
        bad_transcript = video_dir_suff / "transcript.json"
        bad_transcript.write_text("not json!")

        video_dir_base = tmp_path / "my_video"
        video_dir_base.mkdir()
        good_transcript = video_dir_base / "transcript.json"
        good_transcript.write_text(json.dumps({
            "text": "Recovered",
            "segments": [],
            "language": "en",
        }))

        result = load_preexisting_transcript("my_video_720p", str(tmp_path))
        assert result is not None
        assert result["text"] == "Recovered"

    def test_not_a_dict_skips(self, tmp_path):
        video_dir = tmp_path / "my_video"
        video_dir.mkdir()
        transcript = video_dir / "transcript.json"
        transcript.write_text(json.dumps(["list", "not", "dict"]))

        result = load_preexisting_transcript("my_video", str(tmp_path))
        assert result is None

    def test_missing_text_key_populated(self, tmp_path):
        video_dir = tmp_path / "my_video"
        video_dir.mkdir()
        transcript = video_dir / "transcript.json"
        transcript.write_text(json.dumps({
            "segments": [{"text": "A", "start": 0, "end": 1}],
            "language": "en",
        }))

        result = load_preexisting_transcript("my_video", str(tmp_path))
        assert result is not None
        assert result["text"] == ""
        assert len(result["segments"]) == 1

    def test_missing_segments_key_populated(self, tmp_path):
        video_dir = tmp_path / "my_video"
        video_dir.mkdir()
        transcript = video_dir / "transcript.json"
        transcript.write_text(json.dumps({
            "text": "Just text",
            "language": "en",
        }))

        result = load_preexisting_transcript("my_video", str(tmp_path))
        assert result is not None
        assert result["text"] == "Just text"
        assert result["segments"] == []
