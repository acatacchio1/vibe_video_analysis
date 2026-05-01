import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

from src.schemas import JobConfig
from src.worker.pipelines import create_pipeline, get_available_pipelines
from src.worker.pipelines.native_video import (
    NativeVideoPipeline,
    NATIVE_VIDEO_MAX_DURATION,
)


@pytest.mark.unit
class TestPipelineCreation:
    def test_create_pipeline_typed_config(self, native_video_job_dir, native_video_config):
        p = create_pipeline("native_video", native_video_job_dir, native_video_config)
        assert isinstance(p, NativeVideoPipeline)
        assert p.typed_config is not None
        assert p.typed_config.job_id == "nv_test_job"

    def test_create_pipeline_raw_dict(self, native_video_job_dir, native_video_config):
        p = create_pipeline(
            "native_video", native_video_job_dir, native_video_config,
            use_typed_config=False,
        )
        assert isinstance(p, NativeVideoPipeline)
        assert p.typed_config is None
        assert p.config == native_video_config


@pytest.mark.unit
class TestGetVideoPath:
    def test_typed_config_path(self, native_video_pipeline):
        video_path = native_video_pipeline._get_video_path()
        assert isinstance(video_path, Path)
        assert "test_video.mp4" in str(video_path)

    def test_raw_dict_fallback(self, native_video_job_dir, native_video_config):
        p = NativeVideoPipeline(native_video_job_dir, native_video_config)
        assert p.typed_config is None
        video_path = p._get_video_path()
        assert isinstance(video_path, Path)
        assert "test_video.mp4" in str(video_path)


@pytest.mark.unit
class TestGetJobId:
    def test_typed_config(self, native_video_pipeline):
        job_id = native_video_pipeline._get_job_id()
        assert job_id == "nv_test_job"

    def test_raw_dict_fallback(self, native_video_job_dir, native_video_config):
        p = NativeVideoPipeline(native_video_job_dir, native_video_config)
        job_id = p._get_job_id()
        assert job_id == "nv_test_job"

    def test_raw_dict_missing_key(self, native_video_job_dir):
        config = {"video_path": "/tmp/vid.mp4", "provider_type": "litellm", "model": "x"}
        p = NativeVideoPipeline(native_video_job_dir, config)
        job_id = p._get_job_id()
        assert job_id == ""


@pytest.mark.unit
class TestGetAudioConfig:
    def test_typed_config(self, native_video_pipeline):
        cfg = native_video_pipeline._get_audio_config()
        assert cfg["whisper_model"] == "large"
        assert cfg["language"] == "en"
        assert cfg["device"] == "gpu"

    def test_raw_dict(self, native_video_job_dir, native_video_config):
        p = NativeVideoPipeline(native_video_job_dir, native_video_config)
        cfg = p._get_audio_config()
        assert cfg["whisper_model"] == "large"
        assert cfg["language"] == "en"
        assert cfg["device"] == "gpu"

    def test_raw_dict_no_audio_key(self, native_video_job_dir):
        config = {
            "job_id": "test",
            "video_path": "/tmp/v.mp4",
            "provider_type": "litellm",
            "model": "qwen3-27b-q8",
            "params": {"temperature": 0.0},
        }
        p = NativeVideoPipeline(native_video_job_dir, config)
        cfg = p._get_audio_config()
        assert cfg["whisper_model"] == "large"
        assert cfg["language"] == "en"
        assert cfg["device"] == "gpu"


@pytest.mark.unit
class TestGetPhase2Config:
    def test_typed_config_enabled(self, native_video_pipeline):
        enabled, ptype, model, temp, pconfig = native_video_pipeline._get_phase2_config()
        assert enabled is True
        assert ptype == "litellm"
        assert model == "qwen3-27b-q8"
        assert temp == 0.0

    def test_typed_config_disabled(self, native_video_job_dir, native_video_config):
        native_video_config["params"]["phase2"]["enabled"] = False
        typed = JobConfig(**native_video_config)
        p = NativeVideoPipeline(native_video_job_dir, typed)
        enabled, _, _, _, _ = p._get_phase2_config()
        assert enabled is False

    def test_litellm_url_auto_default(self, native_video_job_dir, native_video_config):
        native_video_config["params"]["phase2"]["provider_config"] = {}
        typed = JobConfig(**native_video_config)
        p = NativeVideoPipeline(native_video_job_dir, typed)
        _, ptype, _, _, pconfig = p._get_phase2_config()
        assert ptype == "litellm"
        assert "url" in pconfig

    def test_openrouter_provider(self, native_video_job_dir, native_video_config):
        native_video_config["params"]["phase2"]["provider_type"] = "openrouter"
        native_video_config["params"]["phase2"]["provider_config"] = {"api_key": "sk-or-123"}
        typed = JobConfig(**native_video_config)
        p = NativeVideoPipeline(native_video_job_dir, typed)
        _, ptype, _, _, pconfig = p._get_phase2_config()
        assert ptype == "openrouter"
        assert pconfig.get("api_key") == "sk-or-123"


@pytest.mark.unit
class TestGetProviderConfig:
    def test_typed_config(self, native_video_pipeline):
        ptype, model, pconfig = native_video_pipeline._get_provider_config()
        assert ptype == "litellm"
        assert model == "vision-best"

    def test_raw_dict(self, native_video_job_dir, native_video_config):
        p = NativeVideoPipeline(native_video_job_dir, native_video_config)
        ptype, model, pconfig = p._get_provider_config()
        assert ptype == "litellm"
        assert model == "vision-best"

    def test_raw_dict_defaults(self, native_video_job_dir):
        config = {"video_path": "/tmp/v.mp4", "provider_type": "openrouter", "model": "vicuna"}
        p = NativeVideoPipeline(native_video_job_dir, config)
        ptype, model, pconfig = p._get_provider_config()
        assert ptype == "openrouter"
        assert model == "vicuna"
        assert pconfig == {}


@pytest.mark.unit
class TestCheckVideoDuration:
    @patch("src.utils.video.get_video_duration")
    def test_short_video(self, mock_dur, native_video_pipeline):
        mock_dur.return_value = 200.0
        within, duration = native_video_pipeline._check_video_duration("/tmp/vid.mp4")
        assert within is True
        assert duration == 200.0

    @patch("src.utils.video.get_video_duration")
    def test_long_video(self, mock_dur, native_video_pipeline):
        mock_dur.return_value = 600.0
        within, duration = native_video_pipeline._check_video_duration("/tmp/vid.mp4")
        assert within is False
        assert duration == 600.0

    @patch("src.utils.video.get_video_duration")
    def test_boundary(self, mock_dur, native_video_pipeline):
        mock_dur.return_value = 420.0
        within, duration = native_video_pipeline._check_video_duration("/tmp/vid.mp4")
        assert within is True
        assert duration == 420.0

    @patch("src.utils.video.get_video_duration")
    def test_just_over_boundary(self, mock_dur, native_video_pipeline):
        mock_dur.return_value = 420.1
        within, duration = native_video_pipeline._check_video_duration("/tmp/vid.mp4")
        assert within is False
        assert duration == 420.1


@pytest.mark.unit
class TestGetTranscriptSegmentsWithEndTimes:
    def test_normal_segments(self, native_video_pipeline, sample_transcript):
        segments = native_video_pipeline._get_transcript_segments_with_end_times(sample_transcript)
        assert len(segments) == 3
        assert segments[0]["text"] == "Hello world"
        assert segments[0]["start"] == 0.0
        assert segments[0]["end"] == 3.0

    def test_missing_end_times(self, native_video_pipeline):
        transcript = {
            "text": "Hello",
            "segments": [
                {"text": "Hello", "start": 0.0},
                {"text": "world", "start": 5.0, "end": 10.0},
            ],
        }
        segments = native_video_pipeline._get_transcript_segments_with_end_times(transcript)
        assert len(segments) == 2
        assert segments[0]["end"] == 5.0
        assert segments[0]["text"] == "Hello"

    def test_empty_segments(self, native_video_pipeline):
        transcript = {"text": "Hello", "segments": []}
        segments = native_video_pipeline._get_transcript_segments_with_end_times(transcript)
        assert segments == []

    def test_none_transcript(self, native_video_pipeline):
        segments = native_video_pipeline._get_transcript_segments_with_end_times(None)
        assert segments == []


@pytest.mark.unit
class TestGetTranscriptContextForTimestamp:
    def test_inside_segment(self, native_video_pipeline, sample_transcript):
        segments = native_video_pipeline._get_transcript_segments_with_end_times(sample_transcript)
        ctx = native_video_pipeline._get_transcript_context_for_timestamp(1.5, segments)
        assert "Hello world" in ctx

    def test_with_prior(self, native_video_pipeline, sample_transcript):
        segments = native_video_pipeline._get_transcript_segments_with_end_times(sample_transcript)
        ctx = native_video_pipeline._get_transcript_context_for_timestamp(6.0, segments)
        assert "This is a test" in ctx
        assert "PRIOR:" in ctx
        assert "Hello world" in ctx

    def test_before_transcript_starts(self, native_video_pipeline, sample_transcript):
        segments = native_video_pipeline._get_transcript_segments_with_end_times(sample_transcript)
        ctx = native_video_pipeline._get_transcript_context_for_timestamp(-20.0, segments)
        assert "Transcript begins" in ctx

    def test_after_transcript_short_gap(self, native_video_pipeline, sample_transcript):
        segments = native_video_pipeline._get_transcript_segments_with_end_times(sample_transcript)
        ctx = native_video_pipeline._get_transcript_context_for_timestamp(15.0, segments)
        assert "Transcript ended" in ctx
        assert "video" in ctx

    def test_after_transcript_long_gap(self, native_video_pipeline, sample_transcript):
        segments = native_video_pipeline._get_transcript_segments_with_end_times(sample_transcript)
        ctx = native_video_pipeline._get_transcript_context_for_timestamp(50.0, segments)
        assert "Transcript ended" in ctx
        assert "may not be relevant" in ctx

    def test_empty_segments(self, native_video_pipeline):
        ctx = native_video_pipeline._get_transcript_context_for_timestamp(5.0, [])
        assert ctx == ""


@pytest.mark.unit
class TestSynthesizeEvents:
    def test_disabled_vision_only_passthrough(self, native_video_pipeline):
        native_video_pipeline.typed_config.params.phase2.enabled = False
        events = [{"description": "A cat sitting", "timestamp": 2.5}]
        result = native_video_pipeline._synthesize_events(events, {"text": "", "segments": []})
        assert len(result) == 1
        assert result[0]["combined_analysis"] == "A cat sitting"
        assert result[0]["vision_only"] is True

    @patch("requests.post")
    def test_litellm_success(self, mock_post, native_video_pipeline, sample_transcript):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Enhanced: A beautiful cat"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        events = [{"description": "A cat sitting", "timestamp": 1.5}]
        result = native_video_pipeline._synthesize_events(events, sample_transcript)
        assert result[0]["combined_analysis"] == "Enhanced: A beautiful cat"
        assert result[0]["vision_only"] is False
        assert result[0]["vision_analysis"] == "A cat sitting"
        assert result[0]["tokens"]["prompt_tokens"] == 100

    @patch("requests.post")
    def test_openrouter_success(self, mock_post, native_video_job_dir, native_video_config):
        native_video_config["params"]["phase2"]["provider_type"] = "openrouter"
        native_video_config["params"]["phase2"]["provider_config"] = {"api_key": "sk-or-999"}
        typed = JobConfig(**native_video_config)
        p = NativeVideoPipeline(native_video_job_dir, typed)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "OR analysis"}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 10},
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        transcript = {"text": "Hello", "segments": [{"start": 0, "end": 5, "text": "Hello"}]}
        events = [{"description": "Dog running", "timestamp": 2.0}]
        result = p._synthesize_events(events, transcript)
        assert result[0]["combined_analysis"] == "OR analysis"
        assert result[0]["phase2_model"] == p.typed_config.params.phase2.model

    @patch("requests.post")
    def test_per_event_exception_handling(self, mock_post, native_video_pipeline, sample_transcript):
        mock_resp_ok = MagicMock()
        mock_resp_ok.json.return_value = {
            "choices": [{"message": {"content": "Enhanced event 1"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        mock_resp_ok.raise_for_status = MagicMock()

        mock_post.side_effect = [mock_resp_ok, Exception("API error")]

        events = [
            {"description": "First event", "timestamp": 1.0},
            {"description": "Second event", "timestamp": 6.0},
        ]
        result = native_video_pipeline._synthesize_events(events, sample_transcript)
        assert result[0]["combined_analysis"] == "Enhanced event 1"
        assert result[0]["vision_only"] is False
        assert result[1]["combined_analysis"] == "Second event"
        assert result[1]["vision_only"] is True


@pytest.mark.unit
class TestSaveResults:
    def test_normal_case(self, native_video_pipeline, sample_transcript):
        events = [{"description": "A cat", "combined_analysis": "Enhanced cat", "timestamp": 1.0}]
        result = native_video_pipeline._save_results(events, sample_transcript, "Great video")
        assert result["pipeline_type"] == "native_video"
        assert result["video_description"] == "Great video"
        assert result["events"] == events
        assert result["frames"] == events
        assert result["metadata"]["job_id"] == "nv_test_job"
        assert (native_video_pipeline.output_dir / "results.json").exists()

    def test_transcript_not_dict(self, native_video_pipeline):
        result = native_video_pipeline._save_results([], "not a dict", "desc")
        assert isinstance(result["transcript"], dict)
        assert result["transcript"]["text"] == ""
        assert result["transcript"]["segments"] == []

    def test_no_tokens_accumulated(self, native_video_pipeline):
        events = [{"description": "No tokens here"}]
        result = native_video_pipeline._save_results(events, {"text": "x", "segments": []}, "desc")
        assert result["token_usage"]["total_tokens"] == 0


@pytest.mark.unit
class TestAnalyzeVideo:
    @patch("requests.post")
    def test_json_with_timestamp_conversion(self, mock_post, native_video_pipeline):
        raw_response = '```json\n[{"timestamp": "01:30.25", "duration": 10.0, "description": "Scene change"}]\n```'
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": raw_response}}],
            "usage": {},
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        with patch.object(native_video_pipeline, "_get_video_path") as mock_vp, \
             patch.object(native_video_pipeline, "_get_job_id") as mock_jid:
            mock_vp.return_value = Path("/tmp/vid.mp4")
            mock_jid.return_value = "test_job"

            events = native_video_pipeline._analyze_video()
            assert len(events) == 1
            assert events[0]["timestamp"] == 90.25  # mm:ss.ff → seconds
            assert events[0]["duration"] == 10.0

    @patch("requests.post")
    @patch("src.utils.video.get_video_duration")
    def test_json_parse_failure_fallback(self, mock_dur, mock_post, native_video_pipeline):
        mock_dur.return_value = 60.0
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "not valid JSON at all"}}],
            "usage": {},
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        with patch.object(native_video_pipeline, "_get_video_path") as mock_vp, \
             patch.object(native_video_pipeline, "_get_job_id") as mock_jid:
            mock_vp.return_value = Path("/tmp/vid.mp4")
            mock_jid.return_value = "test_job"

            events = native_video_pipeline._analyze_video()
            assert len(events) == 1
            assert events[0]["timestamp"] == 0.0
            assert events[0]["duration"] == 60.0
            assert "not valid JSON at all" in events[0]["description"]

    @patch("requests.post")
    def test_single_object_wrapped(self, mock_post, native_video_pipeline):
        raw_response = '{"timestamp": "00:05.00", "description": "Single event"}'  # noqa: E501
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": raw_response}}],
            "usage": {},
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        with patch.object(native_video_pipeline, "_get_video_path") as mock_vp, \
             patch.object(native_video_pipeline, "_get_job_id") as mock_jid:
            mock_vp.return_value = Path("/tmp/vid.mp4")
            mock_jid.return_value = "test_job"

            events = native_video_pipeline._analyze_video()
            assert isinstance(events, list)
            assert len(events) == 1

    @patch("requests.post")
    def test_non_vision_model_default(self, mock_post, native_video_job_dir, native_video_config):
        native_video_config["model"] = "qwen3-27b-q8"
        typed = JobConfig(**native_video_config)
        p = NativeVideoPipeline(native_video_job_dir, typed)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "[]"}}],
            "usage": {},
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        with patch.object(p, "_get_video_path") as mock_vp, \
             patch.object(p, "_get_job_id") as mock_jid:
            mock_vp.return_value = Path("/tmp/vid.mp4")
            mock_jid.return_value = "test_job"

            p._analyze_video()
            call_json = mock_post.call_args[1]["json"]
            assert call_json["model"] == "qwen3-vl-2b-instruct"


@pytest.mark.unit
class TestFactoryRegistration:
    def test_native_video_in_available_pipelines(self):
        pipelines = get_available_pipelines()
        assert "native_video" in pipelines


@pytest.mark.unit
class TestReconstructVideo:
    @patch("requests.post")
    def test_success(self, mock_post, native_video_pipeline, sample_transcript):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "This is a description of a cat video."}}],
            "usage": {},
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        events = [{"timestamp": 1.0, "description": "A cat", "combined_analysis": "Enhanced cat"}]
        desc = native_video_pipeline._reconstruct_video(events, sample_transcript)
        assert desc == "This is a description of a cat video."
        assert mock_post.called
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["json"]["max_tokens"] == 2048
