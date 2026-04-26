import pytest
from pathlib import Path


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Root directory of the video-analyzer-web project."""
    return Path(__file__).parent.parent.parent


@pytest.fixture(scope="session")
def small_video_path(project_root: Path) -> Path:
    """Small test video (~8MB, short duration, ~100 frames)."""
    video_path = project_root / "test_videos" / "small" / "source" / \
        "YTDown.com_YouTube_Squirrel-dropkicks-groundhog_Media_B7zDTlQP1-o_002_720p.mp4"
    assert video_path.exists(), f"Small test video not found at {video_path}"
    return video_path


@pytest.fixture(scope="session")
def medium_video_path(project_root: Path) -> Path:
    """Medium test video (~14MB, longer duration)."""
    video_path = project_root / "test_videos" / "medium" / "source" / \
        "YTDown.com_YouTube_Robots-vs-humans-Beijing-half-marathon-d_Media_1vUnusbzNMQ_002_720p.mp4"
    assert video_path.exists(), f"Medium test video not found at {video_path}"
    return video_path
