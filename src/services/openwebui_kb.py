"""
OpenWebUI Knowledge Base client
Handles creating KBs, uploading files, and adding them to knowledge bases.
"""
import json
import uuid
import logging
import requests
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class OpenWebUIClient:
    """Client for OpenWebUI Knowledge Base API"""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v1{path}"

    def test_connection(self) -> dict:
        """Test connectivity and auth to OpenWebUI"""
        try:
            resp = self._session.get(self._url("/knowledge/"), timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return {"ok": True, "knowledge_bases": data.get("total", 0)}
            elif resp.status_code == 401:
                return {"ok": False, "error": "Authentication failed (401). Check your API key."}
            else:
                return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        except requests.ConnectionError:
            return {"ok": False, "error": f"Cannot connect to {self.base_url}"}
        except requests.Timeout:
            return {"ok": False, "error": "Connection timed out"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list_knowledge_bases(self) -> list:
        """List all knowledge bases"""
        resp = self._session.get(self._url("/knowledge/"), timeout=10)
        resp.raise_for_status()
        return resp.json().get("items", [])

    def find_knowledge_base(self, name: str) -> Optional[dict]:
        """Find a knowledge base by name (case-insensitive)"""
        items = self.list_knowledge_bases()
        for kb in items:
            if kb.get("name", "").lower() == name.lower():
                return kb
        return None

    def create_knowledge_base(self, name: str, description: str = "") -> Optional[dict]:
        """Create a new knowledge base"""
        resp = self._session.post(
            self._url("/knowledge/create"),
            json={"name": name, "description": description},
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.error(f"Failed to create KB '{name}': {resp.status_code} {resp.text[:300]}")
        return None

    def ensure_knowledge_base(self, name: str) -> Optional[str]:
        """Ensure a KB with the given name exists, create if not. Returns KB ID or None."""
        existing = self.find_knowledge_base(name)
        if existing:
            logger.info(f"Found existing knowledge base '{name}' (id={existing['id']})")
            return existing["id"]
        logger.info(f"Creating new knowledge base '{name}'")
        kb = self.create_knowledge_base(
            name=name,
            description="Video Analyzer results - auto-generated from video analysis jobs"
        )
        if kb:
            return kb.get("id")
        return None

    def upload_text_file(self, content: str, filename: str) -> Optional[str]:
        """
        Upload a text file to OpenWebUI. Returns file_id or None.
        Uses multipart form upload like the OpenWebUI files API expects.
        """
        url = self._url("/files/")
        # Remove Content-Type header for multipart
        headers = {"Authorization": f"Bearer {self.api_key}"}

        files = {
            "file": (f"{filename}.txt", content.encode("utf-8"), "text/plain"),
        }
        data = {
            "process": "true",
            "process_in_background": "true",
        }

        try:
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)
            if resp.status_code in (200, 201):
                result = resp.json()
                file_id = result.get("id")
                logger.info(f"Uploaded file '{filename}' to OpenWebUI (id={file_id})")
                return file_id
            else:
                logger.error(f"Failed to upload file '{filename}': {resp.status_code} {resp.text[:300]}")
                return None
        except Exception as e:
            logger.error(f"Error uploading file '{filename}': {e}")
            return None

    def add_file_to_knowledge(self, kb_id: str, file_id: str) -> bool:
        """Add an uploaded file to a knowledge base"""
        url = self._url(f"/knowledge/{kb_id}/file/add")
        resp = self._session.post(
            url,
            json={"file_id": file_id},
            timeout=30,
        )
        if resp.status_code == 200:
            logger.info(f"Added file {file_id} to KB {kb_id}")
            return True
        logger.error(f"Failed to add file to KB: {resp.status_code} {resp.text[:300]}")
        return False

    def upload_result_to_kb(
        self,
        results: dict,
        video_name: str,
        kb_name: str,
        job_id: str,
    ) -> dict:
        """
        Main entry point: format results as markdown, upload to KB.
        Returns dict with success status and details.
        """
        result = {"success": False, "kb_id": None, "file_id": None}

        kb_id = self.ensure_knowledge_base(kb_name)
        if not kb_id:
            result["error"] = "Could not find or create knowledge base"
            return result
        result["kb_id"] = kb_id

        content = format_results_as_markdown(results, video_name, job_id)
        safe_filename = Path(video_name).stem.replace(" ", "_")[:80]
        file_id = self.upload_text_file(content, f"{safe_filename}_{job_id[:8]}")
        if not file_id:
            result["error"] = "Failed to upload file to OpenWebUI"
            return result
        result["file_id"] = file_id

        added = self.add_file_to_knowledge(kb_id, file_id)
        if added:
            result["success"] = True
            logger.info(f"Successfully synced job {job_id} to OpenWebUI KB '{kb_name}'")
        else:
            result["error"] = "Failed to add file to knowledge base"

        return result


def format_results_as_markdown(results: dict, video_name: str, job_id: str) -> str:
    """Convert results.json into a structured markdown document for the knowledge base"""
    lines = []

    lines.append(f"# Video Analysis: {video_name}")
    lines.append("")

    metadata = results.get("metadata", {})
    lines.append(f"**Date:** {metadata.get('date', 'N/A')}")
    lines.append(f"**Job ID:** {job_id}")
    lines.append(f"**Model:** {metadata.get('model', 'N/A')}")
    lines.append(f"**Provider:** {metadata.get('provider', 'N/A')}")
    lines.append(f"**Frames Processed:** {metadata.get('frames_processed', 'N/A')}")
    lines.append("")

    video_description = results.get("video_description")
    if video_description:
        if isinstance(video_description, dict):
            desc_text = video_description.get("response", "")
        else:
            desc_text = str(video_description)
        if desc_text:
            lines.append("## Video Description")
            lines.append("")
            lines.append(desc_text)
            lines.append("")

    transcript = results.get("transcript")
    # Safely access transcript data
    transcript_text = None
    transcript_language = "unknown"
    transcript_model = "unknown"
    segments = []
    
    if transcript:
        # Try to get text
        if hasattr(transcript, 'get'):
            transcript_text = transcript.get("text")
            transcript_language = transcript.get("language", "unknown")
            transcript_model = transcript.get("whisper_model", "unknown")
            segments = transcript.get("segments", [])
        elif hasattr(transcript, 'text'):
            transcript_text = transcript.text
            if hasattr(transcript, 'language'):
                transcript_language = transcript.language
            if hasattr(transcript, 'whisper_model'):
                transcript_model = transcript.whisper_model
            if hasattr(transcript, 'segments'):
                segments = transcript.segments
        elif isinstance(transcript, dict):
            transcript_text = transcript.get("text")
            transcript_language = transcript.get("language", "unknown")
            transcript_model = transcript.get("whisper_model", "unknown")
            segments = transcript.get("segments", [])
    
    if transcript_text:
        lines.append("## Transcript")
        lines.append("")
        lines.append(f"*Language: {transcript_language} (Whisper model: {transcript_model})*")
        lines.append("")
        lines.append(transcript_text)
        lines.append("")
        if segments:
            lines.append("### Transcript Segments (with timestamps)")
            lines.append("")
            for seg in segments:
                ts = seg.get("start", 0)
                mins = int(ts // 60)
                secs = int(ts % 60)
                lines.append(f"- [{mins:02d}:{secs:02d}] {seg['text']}")
            lines.append("")

    frame_analyses = results.get("frame_analyses", [])
    if frame_analyses:
        lines.append("## Frame Analyses")
        lines.append("")
        for i, frame in enumerate(frame_analyses):
            frame_num = frame.get("frame", frame.get("frame_number", i + 1))
            ts = frame.get("video_ts", frame.get("timestamp", 0))
            mins = int(ts // 60)
            secs = int(ts % 60)
            analysis = frame.get("response", frame.get("analysis", ""))
            if analysis:
                lines.append(f"### Frame {frame_num} ({mins:02d}:{secs:02d})")
                lines.append("")
                lines.append(analysis)
                lines.append("")

    token_usage = results.get("token_usage")
    if token_usage:
        lines.append("## Token Usage")
        lines.append("")
        lines.append(f"- Prompt tokens: {token_usage.get('prompt_tokens', 'N/A')}")
        lines.append(f"- Completion tokens: {token_usage.get('completion_tokens', 'N/A')}")
        lines.append(f"- Total tokens: {token_usage.get('total_tokens', 'N/A')}")
        lines.append("")

    user_prompt = metadata.get("user_prompt")
    if user_prompt:
        lines.append("## User Prompt")
        lines.append("")
        lines.append(user_prompt)
        lines.append("")

    return "\n".join(lines)
