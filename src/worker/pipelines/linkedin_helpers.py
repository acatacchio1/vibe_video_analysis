"""
Helper functions for LinkedIn pipeline.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


def load_linkedin_prompt(prompt_name: str) -> str:
    """Load LinkedIn prompt by name."""
    # Try multiple possible locations
    base_paths = [
        Path(__file__).parent.parent.parent,  # video-analyzer-web/
        Path(__file__).parent.parent.parent.parent,  # parent of video-analyzer-web/
    ]
    
    for base_path in base_paths:
        prompt_path = base_path / "prompts" / "linkedin" / f"{prompt_name}.txt"
        if prompt_path.exists():
            return prompt_path.read_text()
    
    # Fallback: try relative to current directory
    prompt_path = Path("prompts") / "linkedin" / f"{prompt_name}.txt"
    if prompt_path.exists():
        return prompt_path.read_text()
    
    logger.error(f"LinkedIn prompt not found: {prompt_name}")
    raise FileNotFoundError(f"LinkedIn prompt not found: {prompt_name}")


def parse_json_response(response_text: str) -> Dict[str, Any]:
    """Parse JSON response from LLM, handling common issues."""
    try:
        # Try to extract JSON if there's extra text
        response_text = response_text.strip()
        
        # Find first { and last }
        start = response_text.find('{')
        end = response_text.rfind('}')
        
        if start != -1 and end != -1 and end > start:
            json_str = response_text[start:end+1]
            return json.loads(json_str)
        else:
            # Try parsing the whole thing
            return json.loads(response_text)
            
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        logger.error(f"Response text: {response_text[:500]}...")
        # Return a basic structure
        return {
            "error": f"JSON parse error: {str(e)}",
            "raw_response": response_text[:200]
        }


def safe_get_transcript_text(transcript) -> Optional[str]:
    """Safely extract text from transcript which could be dict, object, or None."""
    if transcript is None:
        return None
    # Try dictionary access first
    if hasattr(transcript, 'get'):
        try:
            return transcript.get('text')
        except (AttributeError, KeyError):
            pass
    # Try attribute access
    if hasattr(transcript, 'text'):
        try:
            return transcript.text
        except AttributeError:
            pass
    # Try item access (for dict-like objects without .get)
    try:
        return transcript['text']
    except (KeyError, TypeError):
        pass
    return None


def safe_get_transcript_segments(transcript) -> Optional[List[Dict[str, Any]]]:
    """Safely extract segments from transcript which could be dict, object, or None."""
    if transcript is None:
        return None
    # Try dictionary access first
    if hasattr(transcript, 'get'):
        try:
            return transcript.get('segments')
        except (AttributeError, KeyError):
            pass
    # Try attribute access
    if hasattr(transcript, 'segments'):
        try:
            return transcript.segments
        except AttributeError:
            pass
    # Try item access (for dict-like objects without .get)
    try:
        return transcript['segments']
    except (KeyError, TypeError):
        pass
    return None


def get_transcript_context(transcript_segments: List[Dict[str, Any]], 
                          timestamp: float, 
                          window_seconds: float = 30.0) -> Tuple[str, str]:
    """
    Get transcript context for a given timestamp.
    Returns (recent_context, prior_context)
    """
    if not transcript_segments:
        return "", ""
    
    recent_segments = []
    prior_segments = []
    
    for segment in transcript_segments:
        seg_start = segment.get("start", 0)
        seg_end = segment.get("end", seg_start + 5)  # Default 5 seconds if no end
        
        # Check if segment overlaps with or is near the timestamp
        if seg_start <= timestamp <= seg_end:
            # Segment contains the timestamp
            recent_segments.append(segment)
        elif seg_end < timestamp and (timestamp - seg_end) <= window_seconds:
            # Segment ended recently
            recent_segments.append(segment)
        elif seg_start > timestamp and (seg_start - timestamp) <= window_seconds:
            # Segment starts soon
            recent_segments.append(segment)
        elif seg_end < timestamp and (timestamp - seg_end) <= window_seconds * 2:
            # Segment ended somewhat recently (for prior context)
            prior_segments.append(segment)
    
    # Get text from segments
    recent_text = " ".join([s.get("text", "") for s in recent_segments[-3:]])  # Last 3 segments
    prior_text = " ".join([s.get("text", "") for s in prior_segments[-6:-3]])  # Segments before recent
    
    return recent_text.strip(), prior_text.strip()


def format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"