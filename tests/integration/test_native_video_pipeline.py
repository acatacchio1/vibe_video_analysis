"""Integration tests for the native_video pipeline full run() flow."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.schemas import JobConfig
from src.worker.pipelines.native_video import NativeVideoPipeline


def _make_resp(content, usage=None):
    resp = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": content}}], "usage": usage or {}}
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.integration
class TestFullPipelineExecution:

    def test_full_run_litellm(self, pipeline, sample_transcript):
        video_resp = json.dumps([
            {"timestamp": "00:05.00", "duration": 10.0, "description": "Opening scene"},
            {"timestamp": "00:15.00", "duration": 10.0, "description": "Cat walks"},
            {"timestamp": "00:25.00", "duration": 5.0, "description": "Closing logo"},
        ])

        with patch("src.utils.video.get_video_duration", return_value=40.0), \
             patch("src.worker.pipelines.native_video.extract_audio", return_value=str(pipeline.job_dir / "audio.wav")), \
             patch("src.worker.pipelines.native_video.transcribe_audio", return_value=sample_transcript), \
             patch("requests.post") as mock_post:
            mock_post.side_effect = [
                _make_resp("```json\n" + video_resp + "\n```"),
                _make_resp("Enhanced: Opening scene"),
                _make_resp("Enhanced: Cat walks"),
                _make_resp("Enhanced: Closing logo"),
                _make_resp("Video about a cat walking through a city."),
            ]
            result = pipeline.run()

        assert result["pipeline_type"] == "native_video"
        assert len(result["events"]) == 3
        assert result["transcript"]["text"]
        assert mock_post.call_count == 5
        assert (pipeline.output_dir / "results.json").exists()

    def test_full_run_no_audio(self, pipeline):
        video_resp = json.dumps([
            {"timestamp": "00:08.00", "duration": 15.0, "description": "Opening segment"},
            {"timestamp": "00:23.00", "duration": 10.0, "description": "Main content"},
        ])

        with patch("src.utils.video.get_video_duration", return_value=60.0), \
             patch("src.worker.pipelines.native_video.extract_audio", return_value=""), \
             patch("requests.post") as mock_post:
            mock_post.side_effect = [
                _make_resp("```json\n" + video_resp + "\n```"),
                _make_resp("Enhanced segment"),
                _make_resp("Enhanced content"),
                _make_resp("Video showing city scenes."),
            ]
            result = pipeline.run()

        assert result["pipeline_type"] == "native_video"
        assert len(result["events"]) == 2
        assert result["transcript"]["text"] == ""
        assert result["transcript"]["segments"] == []
        assert mock_post.call_count == 4

    def test_phase2_disabled_vision_only(self, job_dir, config_dict, sample_transcript):
        config_dict["params"]["phase2"]["enabled"] = False
        typed = JobConfig(**config_dict)
        pipe = NativeVideoPipeline(job_dir, typed)

        video_resp = json.dumps([
            {"timestamp": "00:02.00", "duration": 8.0, "description": "Person typing"},
            {"timestamp": "00:10.00", "duration": 5.0, "description": "Screen demo"},
        ])

        with patch("src.utils.video.get_video_duration", return_value=15.0), \
             patch("src.worker.pipelines.native_video.extract_audio", return_value=str(job_dir / "audio.wav")), \
             patch("src.worker.pipelines.native_video.transcribe_audio", return_value=sample_transcript), \
             patch("requests.post") as mock_post:
            mock_post.side_effect = [
                _make_resp("```json\n" + video_resp + "\n```"),
                _make_resp("A tutorial video showing keyboard typing."),
            ]
            result = pipe.run()

        assert result["pipeline_type"] == "native_video"
        assert len(result["events"]) == 2
        assert mock_post.call_count == 2

    def test_preexisting_transcript_fallback(self, pipeline):
        preexisting = {
            "text": "Pre-existing transcript text.",
            "segments": [{"text": "Pre-existing", "start": 0.0, "end": 4.0}],
            "language": "en",
            "whisper_model": "base",
        }
        video_resp = json.dumps([
            {"timestamp": "00:04.00", "duration": 8.0, "description": "Brief scene"},
        ])

        with patch("src.utils.video.get_video_duration", return_value=8.0), \
              patch("src.worker.pipelines.native_video.extract_audio", return_value=""), \
              patch("src.worker.pipelines.native_video.load_preexisting_transcript", return_value=preexisting), \
             patch("requests.post") as mock_post:
            mock_post.side_effect = [
                _make_resp("```json\n" + video_resp + "\n```"),
                _make_resp("Enhanced: Brief scene with narration"),
                _make_resp("Previously analyzed video."),
            ]
            result = pipeline.run()

        assert result["transcript"]["text"] == "Pre-existing transcript text."
        assert len(result["transcript"]["segments"]) == 1
        assert mock_post.call_count == 3

    def test_long_video_fallback(self, job_dir, config_dict):
        typed = JobConfig(**config_dict)
        pipe = NativeVideoPipeline(job_dir, typed)

        with patch("src.utils.video.get_video_duration", return_value=600.0), \
             patch("src.worker.pipelines.standard_two_step.StandardTwoStepPipeline") as mock_s2:
            mock_s2.return_value.run.return_value = 0
            result = pipe.run()

        assert result == 0
        mock_s2.assert_called_once()
