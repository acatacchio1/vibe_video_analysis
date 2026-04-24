"""
LinkedIn pipeline configuration with default weights and targets.
"""

from typing import Dict, Any


DEFAULT_SCORING_WEIGHTS = {
    "hook_strength": 25,           # 0-25 points
    "self_contained_value": 20,    # 0-20 points  
    "clarity_and_focus": 15,       # 0-15 points
    "speaker_energy": 15,          # 0-15 points
    "visual_quality": 10,          # 0-10 points
    "cta_potential": 10,           # 0-10 points
    "duration_fit": 5,             # 0-5 points
}

DEFAULT_TARGETS = {
    "ideal_duration_min": 30,      # seconds
    "ideal_duration_max": 60,      # seconds
    "max_duration": 90,            # seconds (hard limit)
    "min_duration": 15,            # seconds (hard limit)
    "hook_strength_threshold": 18, # minimum hook score for "strong"
    "total_score_threshold": 70,   # minimum total score for "PUBLISH"
}

DEFAULT_EDIT_PREFERENCES = {
    "prefer_vertical": True,       # Prefer 9:16 vertical format
    "allow_square": True,          # Allow 1:1 square format
    "auto_add_captions": True,     # Auto-suggest captions for silent viewing
    "detect_series": True,         # Detect related segments as series
    "series_min_clips": 3,         # Minimum clips for a series
    "series_max_gap": 60,          # Maximum gap between clips (seconds)
}


class LinkedInConfig:
    """LinkedIn pipeline configuration."""
    
    def __init__(self, user_config: Dict[str, Any] = None):
        self.scoring_weights = DEFAULT_SCORING_WEIGHTS.copy()
        self.targets = DEFAULT_TARGETS.copy()
        self.edit_preferences = DEFAULT_EDIT_PREFERENCES.copy()
        
        if user_config:
            self._apply_user_config(user_config)
    
    def _apply_user_config(self, user_config: Dict[str, Any]):
        """Apply user configuration overrides."""
        # Scoring weights
        if "scoring_weights" in user_config:
            for key, value in user_config["scoring_weights"].items():
                if key in self.scoring_weights:
                    self.scoring_weights[key] = value
        
        # Targets
        if "targets" in user_config:
            for key, value in user_config["targets"].items():
                if key in self.targets:
                    self.targets[key] = value
        
        # Edit preferences
        if "edit_preferences" in user_config:
            for key, value in user_config["edit_preferences"].items():
                if key in self.edit_preferences:
                    self.edit_preferences[key] = value
    
    def get_scoring_prompt_context(self) -> str:
        """Get scoring context for LLM prompts."""
        return f"""
SCORING WEIGHTS (total: {sum(self.scoring_weights.values())} points):
- Hook Strength: {self.scoring_weights['hook_strength']} points
- Self-Contained Value: {self.scoring_weights['self_contained_value']} points
- Clarity & Focus: {self.scoring_weights['clarity_and_focus']} points
- Speaker Energy: {self.scoring_weights['speaker_energy']} points
- Visual Quality: {self.scoring_weights['visual_quality']} points
- CTA Potential: {self.scoring_weights['cta_potential']} points
- Duration Fit: {self.scoring_weights['duration_fit']} points

IDEAL DURATION: {self.targets['ideal_duration_min']}-{self.targets['ideal_duration_max']} seconds
MAX DURATION: {self.targets['max_duration']} seconds (penalize longer)
MIN DURATION: {self.targets['min_duration']} seconds

PREFERRED FORMATS: {"Vertical (9:16)" if self.edit_preferences['prefer_vertical'] else ""} {"Square (1:1)" if self.edit_preferences['allow_square'] else ""}
"""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "scoring_weights": self.scoring_weights,
            "targets": self.targets,
            "edit_preferences": self.edit_preferences,
        }


def validate_duration(duration_seconds: float) -> Dict[str, Any]:
    """Validate segment duration against targets."""
    config = LinkedInConfig()
    
    if duration_seconds < config.targets["min_duration"]:
        return {
            "valid": False,
            "reason": f"Too short ({duration_seconds:.1f}s < {config.targets['min_duration']}s)",
            "score_penalty": 5,  # Max penalty for duration
        }
    elif duration_seconds > config.targets["max_duration"]:
        return {
            "valid": False,
            "reason": f"Too long ({duration_seconds:.1f}s > {config.targets['max_duration']}s)",
            "score_penalty": min(5, (duration_seconds - config.targets["max_duration"]) / 10),
        }
    elif (config.targets["ideal_duration_min"] <= duration_seconds <= config.targets["ideal_duration_max"]):
        return {
            "valid": True,
            "reason": f"Ideal duration ({duration_seconds:.1f}s)",
            "score_bonus": 2,
        }
    else:
        # Within min/max but not ideal range
        return {
            "valid": True,
            "reason": f"Acceptable duration ({duration_seconds:.1f}s)",
            "score_bonus": 0,
        }