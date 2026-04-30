from typing import NotRequired, TypedDict


class Event(TypedDict):
    """TypedDict for a single video event in native video pipeline results.

    Keys:
        timestamp: Float (seconds, NOT "mm:ss" format — conversion happens at save time)
        duration: Float (seconds)
        description: Str (vision analysis text)
        combined_analysis: Str, optional (populated after Phase 2 synthesis)
        vision_only: Bool, defaults to True (changes to False when synthesis adds combined_analysis)
    """

    timestamp: float
    duration: float
    description: str
    combined_analysis: NotRequired[str]
    vision_only: NotRequired[bool]


class VideoResults(TypedDict):
    """TypedDict for the final results.json structure of the native video pipeline.

    Mirrors standard_two_step.py results structure but uses `events` array instead of `frames`.

    Keys:
        metadata: Dict with `pipeline_type: "native_video"` and other job metadata
        video_analysis: Str (full analysis text)
        events: List[Event] (video events with timestamps, descriptions, synthesis)
        transcript: Dict with `text` and `segments` keys
        video_description: Str (final synthesized video description)
        token_usage: Dict with `prompt_tokens`, `completion_tokens`, `total_tokens`
    """

    metadata: dict
    video_analysis: str
    events: list[Event]
    transcript: dict
    video_description: str
    token_usage: dict
