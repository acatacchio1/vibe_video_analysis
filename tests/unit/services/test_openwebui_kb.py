"""
Unit tests for OpenWebUI Knowledge Base client
"""
import sys
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest
import requests

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.services.openwebui_kb import OpenWebUIClient, format_results_as_markdown


@pytest.mark.unit
class TestOpenWebUIClient:
    """Tests for OpenWebUIClient class"""

    def test_init(self):
        """Test client initialization"""
        client = OpenWebUIClient("http://localhost:3000", "test-api-key")
        assert client.base_url == "http://localhost:3000"
        assert client.api_key == "test-api-key"
        assert "Authorization" in client._session.headers
        assert client._session.headers["Authorization"] == "Bearer test-api-key"

    @patch("src.services.openwebui_kb.requests.Session")
    def test_test_connection_success(self, mock_session_class):
        """Test test_connection with successful 200 response"""
        # Setup mock
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"total": 5}
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        # Create client and test
        client = OpenWebUIClient("http://localhost:3000", "test-key")
        client._session = mock_session  # Replace the actual session
        result = client.test_connection()

        # Verify
        assert result["ok"] is True
        assert result["knowledge_bases"] == 5
        mock_session.get.assert_called_once_with(
            "http://localhost:3000/api/v1/knowledge/", timeout=10
        )

    @patch("src.services.openwebui_kb.requests.Session")
    def test_test_connection_401(self, mock_session_class):
        """Test test_connection with 401 unauthorized response"""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = OpenWebUIClient("http://localhost:3000", "test-key")
        client._session = mock_session
        result = client.test_connection()

        assert result["ok"] is False
        assert "Authentication failed" in result["error"]

    @patch("src.services.openwebui_kb.requests.Session")
    def test_test_connection_connection_error(self, mock_session_class):
        """Test test_connection with ConnectionError"""
        mock_session = Mock()
        mock_session.get.side_effect = requests.ConnectionError("Cannot connect")
        mock_session_class.return_value = mock_session

        client = OpenWebUIClient("http://localhost:3000", "test-key")
        client._session = mock_session
        result = client.test_connection()

        assert result["ok"] is False
        assert "Cannot connect" in result["error"]

    @patch("src.services.openwebui_kb.requests.Session")
    def test_test_connection_timeout(self, mock_session_class):
        """Test test_connection with Timeout"""
        mock_session = Mock()
        mock_session.get.side_effect = requests.Timeout("Timed out")
        mock_session_class.return_value = mock_session

        client = OpenWebUIClient("http://localhost:3000", "test-key")
        client._session = mock_session
        result = client.test_connection()

        assert result["ok"] is False
        assert "Connection timed out" in result["error"]

    @patch("src.services.openwebui_kb.requests.Session")
    def test_list_knowledge_bases(self, mock_session_class):
        """Test list_knowledge_bases returns items"""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {"id": "kb1", "name": "Test KB 1"},
                {"id": "kb2", "name": "Test KB 2"},
            ],
            "total": 2,
        }
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = OpenWebUIClient("http://localhost:3000", "test-key")
        client._session = mock_session
        result = client.list_knowledge_bases()

        assert len(result) == 2
        assert result[0]["id"] == "kb1"
        assert result[1]["name"] == "Test KB 2"
        mock_session.get.assert_called_once_with(
            "http://localhost:3000/api/v1/knowledge/", timeout=10
        )

    @patch("src.services.openwebui_kb.OpenWebUIClient.list_knowledge_bases")
    def test_find_knowledge_base_found(self, mock_list_kbs):
        """Test find_knowledge_base with case-insensitive match"""
        mock_list_kbs.return_value = [
            {"id": "kb1", "name": "Video Analysis"},
            {"id": "kb2", "name": "Other KB"},
        ]

        client = OpenWebUIClient("http://localhost:3000", "test-key")
        result = client.find_knowledge_base("video analysis")

        assert result is not None
        assert result["id"] == "kb1"
        assert result["name"] == "Video Analysis"

    @patch("src.services.openwebui_kb.OpenWebUIClient.list_knowledge_bases")
    def test_find_knowledge_base_not_found(self, mock_list_kbs):
        """Test find_knowledge_base returns None when not found"""
        mock_list_kbs.return_value = [
            {"id": "kb1", "name": "Video Analysis"},
            {"id": "kb2", "name": "Other KB"},
        ]

        client = OpenWebUIClient("http://localhost:3000", "test-key")
        result = client.find_knowledge_base("Non-existent KB")

        assert result is None

    @patch("src.services.openwebui_kb.requests.Session")
    def test_create_knowledge_base_success(self, mock_session_class):
        """Test create_knowledge_base with successful creation"""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "new-kb", "name": "New KB"}
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = OpenWebUIClient("http://localhost:3000", "test-key")
        client._session = mock_session
        result = client.create_knowledge_base("New KB", "Test description")

        assert result is not None
        assert result["id"] == "new-kb"
        mock_session.post.assert_called_once_with(
            "http://localhost:3000/api/v1/knowledge/create",
            json={"name": "New KB", "description": "Test description"},
            timeout=30,
        )

    @patch("src.services.openwebui_kb.requests.Session")
    def test_create_knowledge_base_failure(self, mock_session_class):
        """Test create_knowledge_base returns None on failure"""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = OpenWebUIClient("http://localhost:3000", "test-key")
        client._session = mock_session
        result = client.create_knowledge_base("New KB")

        assert result is None

    @patch("src.services.openwebui_kb.OpenWebUIClient.find_knowledge_base")
    def test_ensure_knowledge_base_existing(self, mock_find_kb):
        """Test ensure_knowledge_base returns existing KB ID"""
        mock_find_kb.return_value = {"id": "existing-kb", "name": "Video Analysis"}

        client = OpenWebUIClient("http://localhost:3000", "test-key")
        result = client.ensure_knowledge_base("Video Analysis")

        assert result == "existing-kb"
        mock_find_kb.assert_called_once_with("Video Analysis")

    @patch("src.services.openwebui_kb.OpenWebUIClient.find_knowledge_base")
    @patch("src.services.openwebui_kb.OpenWebUIClient.create_knowledge_base")
    def test_ensure_knowledge_base_create(self, mock_create_kb, mock_find_kb):
        """Test ensure_knowledge_base creates new KB when not found"""
        mock_find_kb.return_value = None
        mock_create_kb.return_value = {"id": "new-kb", "name": "Video Analysis"}

        client = OpenWebUIClient("http://localhost:3000", "test-key")
        result = client.ensure_knowledge_base("Video Analysis")

        assert result == "new-kb"
        mock_find_kb.assert_called_once_with("Video Analysis")
        mock_create_kb.assert_called_once_with(
            name="Video Analysis",
            description="Video Analyzer results - auto-generated from video analysis jobs",
        )

    @patch("src.services.openwebui_kb.requests.post")
    def test_upload_text_file_success(self, mock_requests_post):
        """Test upload_text_file with successful upload"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "file-123"}
        mock_requests_post.return_value = mock_response

        client = OpenWebUIClient("http://localhost:3000", "test-key")
        result = client.upload_text_file("Test content", "testfile")

        assert result == "file-123"
        mock_requests_post.assert_called_once()
        call_args = mock_requests_post.call_args
        assert call_args[0][0] == "http://localhost:3000/api/v1/files/"
        assert "files" in call_args[1]
        assert "data" in call_args[1]

    @patch("src.services.openwebui_kb.requests.post")
    def test_upload_text_file_failure(self, mock_requests_post):
        """Test upload_text_file returns None on failure"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_requests_post.return_value = mock_response

        client = OpenWebUIClient("http://localhost:3000", "test-key")
        result = client.upload_text_file("Test content", "testfile")

        assert result is None

    @patch("src.services.openwebui_kb.requests.Session")
    def test_add_file_to_knowledge_success(self, mock_session_class):
        """Test add_file_to_knowledge returns True on success"""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = OpenWebUIClient("http://localhost:3000", "test-key")
        client._session = mock_session
        result = client.add_file_to_knowledge("kb-123", "file-456")

        assert result is True
        mock_session.post.assert_called_once_with(
            "http://localhost:3000/api/v1/knowledge/kb-123/file/add",
            json={"file_id": "file-456"},
            timeout=30,
        )

    @patch("src.services.openwebui_kb.requests.Session")
    def test_add_file_to_knowledge_failure(self, mock_session_class):
        """Test add_file_to_knowledge returns False on failure"""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Error message"  # Must be a string for slicing
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = OpenWebUIClient("http://localhost:3000", "test-key")
        client._session = mock_session
        result = client.add_file_to_knowledge("kb-123", "file-456")

        assert result is False

    @patch("src.services.openwebui_kb.OpenWebUIClient.ensure_knowledge_base")
    @patch("src.services.openwebui_kb.OpenWebUIClient.upload_text_file")
    @patch("src.services.openwebui_kb.OpenWebUIClient.add_file_to_knowledge")
    def test_upload_result_to_kb_full_flow(
        self, mock_add_file, mock_upload_file, mock_ensure_kb
    ):
        """Test complete upload_result_to_kb flow"""
        mock_ensure_kb.return_value = "kb-123"
        mock_upload_file.return_value = "file-456"
        mock_add_file.return_value = True

        client = OpenWebUIClient("http://localhost:3000", "test-key")
        results = {
            "metadata": {"date": "2024-01-01", "model": "test-model"},
            "video_description": "Test description",
        }
        result = client.upload_result_to_kb(
            results, "test_video.mp4", "Video Analysis", "job-123"
        )

        assert result["success"] is True
        assert result["kb_id"] == "kb-123"
        assert result["file_id"] == "file-456"
        mock_ensure_kb.assert_called_once_with("Video Analysis")
        mock_upload_file.assert_called_once()
        mock_add_file.assert_called_once_with("kb-123", "file-456")

    @patch("src.services.openwebui_kb.OpenWebUIClient.ensure_knowledge_base")
    def test_upload_result_to_kb_no_kb(self, mock_ensure_kb):
        """Test upload_result_to_kb when KB cannot be created"""
        mock_ensure_kb.return_value = None

        client = OpenWebUIClient("http://localhost:3000", "test-key")
        results = {"metadata": {}}
        result = client.upload_result_to_kb(
            results, "test_video.mp4", "Video Analysis", "job-123"
        )

        assert result["success"] is False
        assert result["kb_id"] is None
        assert result["file_id"] is None
        assert "error" in result
        assert "Could not find or create knowledge base" in result["error"]


@pytest.mark.unit
class TestFormatResultsAsMarkdown:
    """Tests for format_results_as_markdown function"""

    def test_format_results_basic(self):
        """Test with minimal results dict"""
        results = {
            "metadata": {
                "date": "2024-01-01",
                "model": "llama3.2",
                "provider": "litellm",
                "frames_processed": 10,
            }
        }
        markdown = format_results_as_markdown(results, "test_video.mp4", "job-123")
        
        assert "# Video Analysis: test_video.mp4" in markdown
        assert "**Date:** 2024-01-01" in markdown
        assert "**Job ID:** job-123" in markdown
        assert "**Model:** llama3.2" in markdown
        assert "**Provider:** litellm" in markdown
        assert "**Frames Processed:** 10" in markdown

    def test_format_results_with_transcript(self):
        """Test with transcript data including segments"""
        results = {
            "metadata": {"date": "2024-01-01"},
            "transcript": {
                "text": "Hello world. This is a test.",
                "language": "en",
                "whisper_model": "large-v3",
                "segments": [
                    {"start": 0.0, "text": "Hello world."},
                    {"start": 1.5, "text": "This is a test."},
                ],
            },
        }
        markdown = format_results_as_markdown(results, "test_video.mp4", "job-123")
        
        assert "## Transcript" in markdown
        assert "*Language: en (Whisper model: large-v3)*" in markdown
        assert "Hello world. This is a test." in markdown
        assert "### Transcript Segments (with timestamps)" in markdown
        assert "- [00:00] Hello world." in markdown
        assert "- [00:01] This is a test." in markdown

    def test_format_results_with_frame_analyses(self):
        """Test with frame analyses"""
        results = {
            "metadata": {"date": "2024-01-01"},
            "frame_analyses": [
                {
                    "frame": 1,
                    "video_ts": 0.0,
                    "response": "A person is speaking.",
                },
                {
                    "frame_number": 2,
                    "timestamp": 1.5,
                    "analysis": "The person is gesturing.",
                },
            ],
        }
        markdown = format_results_as_markdown(results, "test_video.mp4", "job-123")
        
        assert "## Frame Analyses" in markdown
        assert "### Frame 1 (00:00)" in markdown
        assert "A person is speaking." in markdown
        assert "### Frame 2 (00:01)" in markdown
        assert "The person is gesturing." in markdown

    def test_format_results_with_token_usage(self):
        """Test with token usage data"""
        results = {
            "metadata": {"date": "2024-01-01"},
            "token_usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 500,
                "total_tokens": 1500,
            },
        }
        markdown = format_results_as_markdown(results, "test_video.mp4", "job-123")
        
        assert "## Token Usage" in markdown
        assert "- Prompt tokens: 1000" in markdown
        assert "- Completion tokens: 500" in markdown
        assert "- Total tokens: 1500" in markdown

    def test_format_results_transcript_as_object(self):
        """Test with transcript as object with attributes"""
        class TranscriptObject:
            text = "Hello from object"
            language = "fr"
            whisper_model = "base"
            segments = [{"start": 0.0, "text": "Bonjour"}]
        
        results = {
            "metadata": {"date": "2024-01-01"},
            "transcript": TranscriptObject(),
        }
        markdown = format_results_as_markdown(results, "test_video.mp4", "job-123")
        
        assert "## Transcript" in markdown
        assert "*Language: fr (Whisper model: base)*" in markdown
        assert "Hello from object" in markdown
        assert "- [00:00] Bonjour" in markdown

    def test_format_results_video_description_string(self):
        """Test with video_description as string (not dict)"""
        results = {
            "metadata": {"date": "2024-01-01"},
            "video_description": "This is a string description",
        }
        markdown = format_results_as_markdown(results, "test_video.mp4", "job-123")
        
        assert "## Video Description" in markdown
        assert "This is a string description" in markdown

    def test_format_results_video_description_dict(self):
        """Test with video_description as dict with response"""
        results = {
            "metadata": {"date": "2024-01-01"},
            "video_description": {"response": "This is a dict description"},
        }
        markdown = format_results_as_markdown(results, "test_video.mp4", "job-123")
        
        assert "## Video Description" in markdown
        assert "This is a dict description" in markdown

    def test_format_results_with_user_prompt(self):
        """Test with user_prompt in metadata"""
        results = {
            "metadata": {
                "date": "2024-01-01",
                "user_prompt": "Analyze this video for key moments",
            },
        }
        markdown = format_results_as_markdown(results, "test_video.mp4", "job-123")
        
        assert "## User Prompt" in markdown
        assert "Analyze this video for key moments" in markdown

    def test_format_results_empty_transcript(self):
        """Test with empty transcript"""
        results = {
            "metadata": {"date": "2024-01-01"},
            "transcript": {},
        }
        markdown = format_results_as_markdown(results, "test_video.mp4", "job-123")
        
        # Should not include transcript section if no text
        assert "## Transcript" not in markdown

    def test_format_results_transcript_dict_without_segments(self):
        """Test with transcript dict without segments"""
        results = {
            "metadata": {"date": "2024-01-01"},
            "transcript": {
                "text": "Simple text",
                "language": "en",
            },
        }
        markdown = format_results_as_markdown(results, "test_video.mp4", "job-123")
        
        assert "## Transcript" in markdown
        assert "Simple text" in markdown
        # Should not include segments section
        assert "### Transcript Segments" not in markdown