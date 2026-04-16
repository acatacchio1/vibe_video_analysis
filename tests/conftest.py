# Re-export all shared fixtures so they are discoverable by all test subdirectories.
from tests.fixtures.conftest import (
    temp_upload_dir,
    temp_jobs_dir,
    mock_gpu_data,
    sample_job_config,
    sample_frame_analysis,
    sample_results_file,
    mock_nvmlopen,
    mock_chat_job_response,
    mock_ollama_client,
    mock_video_file,
    mock_ffprobe_output,
    setup_vram_manager,
)
