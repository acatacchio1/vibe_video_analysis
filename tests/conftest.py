# Re-export all shared fixtures so they are discoverable by all test subdirectories.
# The app and client fixtures are needed by API tests in tests/unit/api/

from tests.fixtures.conftest import (
    temp_upload_dir,
    temp_jobs_dir,
    mock_gpu_data,
    sample_job_config,
    sample_frame_analysis,
    sample_results_file,
    mock_nvmlopen,
    mock_chat_job_response,
    mock_video_file,
    mock_ffprobe_output,
    setup_vram_manager,
    # New fixtures for API/WebSocket testing
    mock_api_error,
    mock_vram_manager,
    mock_chat_queue_manager,
    mock_socketio,
    mock_monitor,
    mock_providers_dict,
    temp_video_with_frames,
    temp_job_with_results,
    mock_openwebui_responses,
    app,
    client,
)
