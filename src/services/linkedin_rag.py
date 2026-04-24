"""
LinkedIn RAG service for OpenWebUI knowledge base.
Handles LinkedIn-specific queries and ranking of video segments.
"""

import json
import logging
import time
from typing import Dict, Any, List, Optional
import requests

from .openwebui_kb import OpenWebUIClient

logger = logging.getLogger(__name__)


class LinkedInRAGService:
    """LinkedIn RAG service for ranking video segments."""
    
    def __init__(self, openwebui_client: OpenWebUIClient):
        self.client = openwebui_client
        self.kb_name = "video_analyzer_linkedin"
        self.kb_id = None
        
    def ensure_linkedin_knowledge_base(self) -> Optional[str]:
        """Ensure LinkedIn knowledge base exists."""
        if not self.kb_id:
            self.kb_id = self.client.ensure_knowledge_base(self.kb_name)
        return self.kb_id
    
    def upload_linkedin_segments(self, segments: List[Dict[str, Any]], 
                                video_name: str, job_id: str) -> Dict[str, Any]:
        """Upload LinkedIn segments to knowledge base."""
        result = {"success": False, "kb_id": None, "file_id": None}
        
        kb_id = self.ensure_linkedin_knowledge_base()
        if not kb_id:
            result["error"] = "Could not find or create LinkedIn knowledge base"
            return result
        
        result["kb_id"] = kb_id
        
        # Format segments as markdown
        content = self._format_segments_as_markdown(segments, video_name, job_id)
        
        # Upload to OpenWebUI
        safe_filename = f"linkedin_{Path(video_name).stem}_{job_id[:8]}".replace(" ", "_")[:80]
        file_id = self.client.upload_text_file(content, safe_filename)
        
        if not file_id:
            result["error"] = "Failed to upload segments to OpenWebUI"
            return result
        
        result["file_id"] = file_id
        
        # Add to knowledge base
        added = self.client.add_file_to_knowledge(kb_id, file_id)
        if added:
            result["success"] = True
            logger.info(f"Successfully uploaded {len(segments)} LinkedIn segments to KB")
        else:
            result["error"] = "Failed to add segments to knowledge base"
        
        return result
    
    def _format_segments_as_markdown(self, segments: List[Dict[str, Any]], 
                                   video_name: str, job_id: str) -> str:
        """Format LinkedIn segments as markdown for knowledge base."""
        lines = []
        
        lines.append(f"# LinkedIn Video Segments: {video_name}")
        lines.append("")
        lines.append(f"**Job ID:** {job_id}")
        lines.append(f"**Total Segments:** {len(segments)}")
        lines.append(f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("## Segment Analysis")
        lines.append("")
        
        for segment in segments:
            segment_id = segment.get("segment_id", "unknown")
            start_time = segment.get("start_time", "00:00:00")
            end_time = segment.get("end_time", "00:00:00")
            duration = segment.get("duration_seconds", 0)
            transcript = segment.get("transcript", "")[:200] + "..." if len(segment.get("transcript", "")) > 200 else segment.get("transcript", "")
            visual_summary = segment.get("visual_summary", "")
            key_topics = ", ".join(segment.get("key_topics", []))
            speaker_energy = segment.get("speaker_energy", "unknown")
            hook_strength = segment.get("hook_strength", "unknown")
            
            lines.append(f"### Segment {segment_id}")
            lines.append("")
            lines.append(f"**Timestamp:** {start_time} - {end_time} ({duration:.1f}s)")
            lines.append(f"**Hook Strength:** {hook_strength}")
            lines.append(f"**Speaker Energy:** {speaker_energy}")
            lines.append(f"**Key Topics:** {key_topics}")
            lines.append("")
            lines.append("**Transcript:**")
            lines.append(f"> {transcript}")
            lines.append("")
            lines.append("**Visual Summary:**")
            lines.append(f"> {visual_summary}")
            lines.append("")
            lines.append("---")
            lines.append("")
        
        return "\n".join(lines)
    
    def query_linkedin_segments(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Query LinkedIn knowledge base for segments."""
        kb_id = self.ensure_linkedin_knowledge_base()
        if not kb_id:
            logger.error("LinkedIn knowledge base not available")
            return []
        
        try:
            # Use OpenWebUI query API
            url = self.client._url(f"/knowledge/{kb_id}/query")
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {self.client.api_key}"},
                json={
                    "query": query,
                    "top_k": top_k,
                    "score_threshold": 0.5,
                },
                timeout=30,
            )
            
            if response.status_code == 200:
                results = response.json()
                # Parse results to extract segment information
                return self._parse_query_results(results)
            else:
                logger.error(f"Query failed: {response.status_code} {response.text[:200]}")
                return []
                
        except Exception as e:
            logger.error(f"Error querying LinkedIn knowledge base: {e}")
            return []
    
    def _parse_query_results(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse OpenWebUI query results to extract segment information."""
        parsed = []
        
        for result in results.get("results", []):
            content = result.get("content", "")
            score = result.get("score", 0)
            
            # Try to extract segment info from content
            segment_info = self._extract_segment_from_content(content)
            if segment_info:
                segment_info["rag_score"] = score
                parsed.append(segment_info)
        
        return parsed
    
    def _extract_segment_from_content(self, content: str) -> Optional[Dict[str, Any]]:
        """Extract segment information from markdown content."""
        try:
            # This is a simplified parser - in production, you'd want more robust parsing
            lines = content.split("\n")
            segment = {}
            
            for line in lines:
                if line.startswith("### Segment "):
                    segment["segment_id"] = line.replace("### Segment ", "").strip()
                elif line.startswith("**Timestamp:**"):
                    # Extract timestamp info
                    ts_text = line.replace("**Timestamp:**", "").strip()
                    # Parse timestamp format: "00:00:00 - 00:00:30 (30.0s)"
                    if " - " in ts_text and "(" in ts_text:
                        parts = ts_text.split(" - ")
                        segment["start_time"] = parts[0].strip()
                        end_part = parts[1].split("(")[0].strip()
                        segment["end_time"] = end_part
                elif line.startswith("**Hook Strength:**"):
                    segment["hook_strength"] = line.replace("**Hook Strength:**", "").strip()
                elif line.startswith("**Speaker Energy:**"):
                    segment["speaker_energy"] = line.replace("**Speaker Energy:**", "").strip()
                elif line.startswith("> "):
                    # This is either transcript or visual summary
                    text = line[2:].strip()
                    if "transcript" not in segment:
                        segment["transcerpt"] = text
                    elif "visual_summary" not in segment:
                        segment["visual_summary"] = text
            
            if "segment_id" in segment:
                return segment
                
        except Exception as e:
            logger.error(f"Error extracting segment from content: {e}")
        
        return None
    
    def rank_segments_by_linkedin_criteria(self, segments: List[Dict[str, Any]], 
                                          scoring_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Rank segments using LinkedIn-specific criteria with OpenWebUI RAG."""
        if not segments:
            return []
        
        # First, upload segments to knowledge base if not already there
        # (This would be done in a separate step, but we check here)
        
        # Query for LinkedIn-specific criteria
        linkedin_queries = [
            "Find segments with strong hook or attention-grabbing opening",
            "Find self-contained valuable insights that work as standalone content",
            "Find segments with high speaker energy and direct eye contact",
            "Find segments suitable for vertical or square video format",
            "Find segments with clear call to action or natural conclusion",
        ]
        
        all_ranked = []
        
        for query in linkedin_queries:
            results = self.query_linkedin_segments(query, top_k=5)
            for result in results:
                # Add to ranked list if not already there
                segment_id = result.get("segment_id")
                if not any(s.get("segment_id") == segment_id for s in all_ranked):
                    all_ranked.append(result)
        
        # If RAG didn't return results, fall back to local scoring
        if not all_ranked:
            logger.info("OpenWebUI RAG returned no results, using local scoring")
            return self._rank_segments_locally(segments, scoring_config)
        
        # Merge RAG results with original segment data
        merged = []
        for rag_result in all_ranked:
            segment_id = rag_result.get("segment_id")
            original_segment = next((s for s in segments if s.get("segment_id") == segment_id), None)
            
            if original_segment:
                merged_segment = {**original_segment, **rag_result}
                
                # Calculate LinkedIn score based on RAG results
                score = self._calculate_linkedin_score(merged_segment, scoring_config)
                merged_segment["total_score"] = score
                merged_segment["score_breakdown"] = score.get("breakdown", {}) if isinstance(score, dict) else {}
                
                merged.append(merged_segment)
        
        # Sort by total score
        merged.sort(key=lambda x: x.get("total_score", 0), reverse=True)
        
        return merged
    
    def _calculate_linkedin_score(self, segment: Dict[str, Any], 
                                 scoring_config: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate LinkedIn score based on segment data and RAG results."""
        scores = {
            "hook_strength": 0,
            "self_contained_value": 0,
            "clarity_and_focus": 0,
            "speaker_energy": 0,
            "visual_quality": 0,
            "cta_potential": 0,
            "duration_fit": 0,
        }
        
        # Hook strength scoring
        hook_text = segment.get("hook_strength", "").lower()
        if "strong" in hook_text:
            scores["hook_strength"] = min(25, scoring_config.get("hook_strength", 25))
        elif "moderate" in hook_text:
            scores["hook_strength"] = min(15, scoring_config.get("hook_strength", 25) // 2)
        
        # Speaker energy scoring
        energy_text = segment.get("speaker_energy", "").lower()
        if "high" in energy_text:
            scores["speaker_energy"] = min(15, scoring_config.get("speaker_energy", 15))
        elif "medium" in energy_text:
            scores["speaker_energy"] = min(10, scoring_config.get("speaker_energy", 15) // 1.5)
        
        # Duration scoring
        duration = segment.get("duration_seconds", 0)
        if 30 <= duration <= 60:
            scores["duration_fit"] = min(5, scoring_config.get("duration_fit", 5))
        elif 15 <= duration <= 90:
            scores["duration_fit"] = min(3, scoring_config.get("duration_fit", 5) // 2)
        
        # Estimate other scores based on RAG confidence
        rag_score = segment.get("rag_score", 0.5)
        
        scores["self_contained_value"] = int(rag_score * scoring_config.get("self_contained_value", 20))
        scores["clarity_and_focus"] = int(rag_score * scoring_config.get("clarity_and_focus", 15))
        scores["visual_quality"] = int(rag_score * scoring_config.get("visual_quality", 10))
        scores["cta_potential"] = int(rag_score * scoring_config.get("cta_potential", 10))
        
        total = sum(scores.values())
        
        return {
            "total": total,
            "breakdown": scores,
            "max_possible": sum(scoring_config.values()) if isinstance(scoring_config, dict) else 100
        }
    
    def _rank_segments_locally(self, segments: List[Dict[str, Any]], 
                              scoring_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback local ranking when OpenWebUI is not available."""
        ranked = []
        
        for segment in segments:
            score = self._calculate_linkedin_score(segment, scoring_config)
            
            ranked_segment = {
                **segment,
                "total_score": score.get("total", 0),
                "score_breakdown": score.get("breakdown", {}),
                "recommendation": "PUBLISH" if score.get("total", 0) > 70 else 
                                 "PUBLISH WITH EDITS" if score.get("total", 0) > 60 else "SKIP",
                "suggested_hook_reframe": "Consider starting with a more provocative question",
                "edit_notes": "Trim first 2 seconds, add caption for key point",
                "series_potential": "",
                "linkedin_caption_starter": "Here's an insight from our latest discussion...",
            }
            
            ranked.append(ranked_segment)
        
        ranked.sort(key=lambda x: x.get("total_score", 0), reverse=True)
        return ranked


# Import Path here to avoid circular imports
from pathlib import Path