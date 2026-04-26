import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

# Load real app module directly to avoid conftest mock replacing sys.modules["app"]
spec = importlib.util.spec_from_file_location("app_real", str(ROOT / "app.py"))
_real_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_real_app)

_extract_frames_direct = _real_app._extract_frames_direct
_run_dedup = _real_app._run_dedup
_run_dedup_sequential = _real_app._run_dedup_sequential
_renumber_frames = _real_app._renumber_frames

_mock_socketio = MagicMock()


def _run_extract(video_path):
    with patch.object(_real_app, "socketio", _mock_socketio):
        result = _extract_frames_direct(video_path)
        if result is None:
            return None
        result["video_dir"] = Path(result["video_dir"])
        result["frames_dir"] = Path(result["frames_dir"])
        return result


class TestFrameExtraction:
    def test_small_video_frame_extraction(self, small_video_path, tmp_path):
        dest = tmp_path / "uploads" / small_video_path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(small_video_path, dest)
        result = _run_extract(str(dest))
        assert result is not None
        assert result["frame_count"] > 0
        assert result["fps"] > 0
        assert result["duration"] > 0
        assert result["video_dir"].exists()
        assert result["frames_dir"].exists()

        frames = sorted(result["frames_dir"].glob("frame_*.jpg"))
        assert len(frames) == result["frame_count"]

        stem = small_video_path.stem.rsplit("_720p", 1)[0]
        thumb = result["video_dir"].parent / "thumbs" / f"{stem}.jpg"
        assert thumb.exists()

        meta = json.loads((result["video_dir"] / "frames_meta.json").read_text())
        assert meta["frame_count"] == result["frame_count"]
        assert abs(meta["fps"] - result["fps"]) < 0.1

        index = json.loads((result["video_dir"] / "frames_index.json").read_text())
        assert len(index) == result["frame_count"]
        assert "1" in index
        assert float(index["1"]) == 0.0

    def test_medium_video_frame_extraction(self, medium_video_path, tmp_path):
        dest = tmp_path / "uploads" / medium_video_path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(medium_video_path, dest)
        result = _run_extract(str(dest))
        assert result is not None
        assert result["frame_count"] > 10

        index = json.loads((result["video_dir"] / "frames_index.json").read_text())
        timestamps = [float(v) for v in index.values()]
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1]

    def test_probe_video_with_ffprobe(self, small_video_path):
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration", "-show_entries",
             "stream=r_frame_rate,codec_type",
             "-of", "json", str(small_video_path)],
            capture_output=True, text=True, timeout=15,
        )
        assert probe.returncode == 0
        info = json.loads(probe.stdout)
        assert "streams" in info
        assert "format" in info
        assert "duration" in info["format"]

    def test_extraction_creates_proper_naming(self, small_video_path, tmp_path):
        dest = tmp_path / "uploads" / small_video_path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(small_video_path, dest)
        result = _run_extract(str(dest))
        assert any("000001" in f.name for f in result["frames_dir"].glob("frame_*.jpg"))


class TestDedupWithRealFrames:
    def _setup_extracted(self, video_path, tmp_path):
        dest = tmp_path / "uploads" / video_path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(video_path, dest)
        result = _run_extract(str(dest))
        assert result is not None
        return result

    def test_dedup_reduces_frame_count(self, small_video_path, tmp_path):
        result = self._setup_extracted(small_video_path, tmp_path)
        dr = _run_dedup(result["frames_dir"], result["frames_dir"] / "thumbs", 10, 1.0)
        assert dr["original_count"] > 0
        assert dr["threshold"] == 10
        assert dr["deduped_count"] <= dr["original_count"]

    def test_dedup_mapping_consistency(self, small_video_path, tmp_path):
        result = self._setup_extracted(small_video_path, tmp_path)
        dr = _run_dedup(result["frames_dir"], result["frames_dir"] / "thumbs", 10, 1.0)
        for orig, dedup in dr["original_to_dedup_mapping"].items():
            assert str(dedup) in dr["dedup_to_original_mapping"]
            assert int(dr["dedup_to_original_mapping"][str(dedup)]) == int(orig)

    def test_dedup_zero_threshold_no_removal(self, small_video_path, tmp_path):
        result = self._setup_extracted(small_video_path, tmp_path)
        orig = len(list(result["frames_dir"].glob("frame_*.jpg")))
        dr = _run_dedup_sequential(result["frames_dir"], result["frames_dir"] / "thumbs", 0, 1.0)
        assert dr["deduped_count"] == orig
        assert len(list(result["frames_dir"].glob("frame_*.jpg"))) == orig

    def test_dedup_renumbering(self, small_video_path, tmp_path):
        result = self._setup_extracted(small_video_path, tmp_path)
        _run_dedup(result["frames_dir"], result["frames_dir"] / "thumbs", 10, 1.0)
        fi, cnt, afps = _renumber_frames(result["frames_dir"], result["frames_dir"] / "thumbs", 1.0)
        frames = sorted(result["frames_dir"].glob("frame_*.jpg"))
        nums = []
        for fn in frames:
            m = re.search(r"frame_(\d+)", fn.name)
            if m:
                nums.append(int(m.group(1)))
        assert nums == sorted(nums)
        assert len(set(nums)) == len(nums)


class TestResultsAPI:
    def test_list_results_empty(self, client, app):
        resp = client.get("/api/results")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_results_format_with_production_data(self, project_root):
        rp = project_root / "jobs" / "e87c15ab" / "output" / "results.json"
        if not rp.exists():
            pytest.skip("Real completion data not available")
        rr = json.loads(rp.read_text())
        for key in {"metadata", "transcript", "frame_analyses", "video_description"}:
            assert key in rr
        assert rr["metadata"]["frames_processed"] > 0

    def test_transcript_structure_valid(self, project_root):
        rp = project_root / "jobs" / "e87c15ab" / "output" / "results.json"
        if not rp.exists():
            pytest.skip("Real completion data not available")
        transcript = json.loads(rp.read_text()).get("transcript", {})
        assert transcript.get("text", "")
        if "segments" in transcript and transcript["segments"]:
            seg = transcript["segments"][0]
            assert all(k in seg for k in ("start", "end", "text"))
            assert seg["end"] >= seg["start"]


class TestErrorHandling:
    def test_nonexistent_video_path(self, tmp_path):
        fake = tmp_path / "fake_video_input.mp4"
        fake.write_bytes(b"not a real video")
        assert _run_extract(str(fake)) is None

    def test_dedup_no_frames(self, tmp_path):
        ed = tmp_path / "ef"
        ed.mkdir()
        td = ed / "thumbs"
        td.mkdir()
        dr = _run_dedup_sequential(ed, td, 10, 1.0)
        assert dr["original_count"] == 0
        assert dr["deduped_count"] == 0

    def test_renumber_empty_dir(self, tmp_path):
        ed = tmp_path / "er"
        ed.mkdir()
        td = ed / "thumbs"
        td.mkdir()
        fi, cnt, fps = _renumber_frames(ed, td, 1.0)
        assert cnt == 0
        assert len(fi) == 0


class TestDataIntegrity:
    def _get_extracted(self, video_path, tmp_path):
        dest = tmp_path / "uploads" / video_path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(video_path, dest)
        result = _run_extract(str(dest))
        assert result is not None
        return result

    def test_meta_and_index_consistency(self, small_video_path, tmp_path):
        result = self._get_extracted(small_video_path, tmp_path)
        meta = json.loads((result["video_dir"] / "frames_meta.json").read_text())
        index = json.loads((result["video_dir"] / "frames_index.json").read_text())
        assert meta["frame_count"] == len(index)

    def test_frame_files_match_meta_count(self, small_video_path, tmp_path):
        result = self._get_extracted(small_video_path, tmp_path)
        meta = json.loads((result["video_dir"] / "frames_meta.json").read_text())
        assert len(list(result["frames_dir"].glob("frame_*.jpg"))) == meta["frame_count"]

    def test_timestamps_sequential_in_index(self, small_video_path, tmp_path):
        result = self._get_extracted(small_video_path, tmp_path)
        index = json.loads((result["video_dir"] / "frames_index.json").read_text())
        ts = [float(index[str(i)]) for i in range(1, len(index) + 1)]
        for i in range(1, len(ts)):
            assert ts[i] >= ts[i - 1]

    def test_dedup_preserves_integrity(self, small_video_path, tmp_path):
        from PIL import Image
        result = self._get_extracted(small_video_path, tmp_path)
        _run_dedup(result["frames_dir"], result["frames_dir"] / "thumbs", 10, 1.0)
        for ff in result["frames_dir"].glob("frame_*.jpg"):
            img = Image.open(ff)
            assert img.format == "JPEG"
            assert img.size[0] > 0 and img.size[1] > 0

    def test_frame_index_sequential_keys(self, small_video_path, tmp_path):
        result = self._get_extracted(small_video_path, tmp_path)
        index = json.loads((result["video_dir"] / "frames_index.json").read_text())
        keys = sorted(int(k) for k in index.keys())
        assert keys == list(range(1, len(keys) + 1))
