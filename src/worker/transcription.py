"""
Shared transcription utilities extracted from worker pipelines.

Provides standalone functions for audio extraction, faster-whisper transcription,
and pre-existing transcript loading — usable across any pipeline implementation.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def extract_audio(video_path: str, job_dir: str) -> str:
    """
    Extract audio from a video file using ffmpeg.

    Produces a 16kHz mono WAV file (pcm_s16le) at ``{job_dir}/audio.wav``
    suitable for faster-whisper transcription.

    Args:
        video_path: Absolute path to the source video file.
        job_dir: Directory where ``audio.wav`` will be written.

    Returns:
        Absolute path to the extracted WAV file as a string, or an empty
        string if extraction failed or the video contains no audio stream.
    """
    audio_path = Path(job_dir) / "audio.wav"

    extract_cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(audio_path),
    ]
    logger.info(f"Running: {' '.join(extract_cmd)}")

    try:
        proc = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        logger.error("Audio extraction timed out after 120s")
        return str(audio_path) if audio_path.exists() and audio_path.stat().st_size > 0 else ""

    stderr = proc.stderr or ""
    if proc.returncode != 0:
        if "does not contain any stream" in stderr or "no audio" in stderr.lower():
            logger.info("No audio stream, skipping transcription")
        else:
            logger.warning(f"Audio extraction failed: {stderr[-300:]}")
        return ""

    if not audio_path.exists() or audio_path.stat().st_size == 0:
        logger.info("No audio extracted (empty output), skipping")
        return ""

    audio_size = audio_path.stat().st_size
    logger.info(f"Audio extracted: {audio_path} ({audio_size} bytes)")
    return str(audio_path)


def transcribe_audio(
    wav_path: str,
    whisper_model: str,
    language: Optional[str] = None,
    device: str = "cuda",
) -> Dict[str, Any]:
    """
    Transcribe a WAV audio file using faster-whisper.

    Loads the ``WhisperModel`` on *device* (``"cuda"`` or ``"cpu"``) with
    the appropriate compute type (``float16`` for CUDA, ``int8`` for CPU),
    runs transcription with VAD filtering, and returns structured results.

    Args:
        wav_path: Absolute path to a 16kHz mono WAV file.
        whisper_model: Model name or path (e.g. ``"large"``, ``"base"``, or a local path).
        language: ISO 639-1 language code (e.g. ``"en"``). Pass ``None`` for auto-detect.
        device: ``"cuda"`` for GPU or ``"cpu"`` for CPU inference.

    Returns:
        Dictionary with keys ``text`` (str), ``segments`` (list of dicts with
        ``text``, ``start``, ``end``), and ``language`` (str).

    Raises:
        RuntimeError: If the Whisper model fails to load or transcription errors out.
    """
    if device == "gpu":
        device = "cuda"
    compute_type = "float16" if device == "cuda" else "int8"

    logger.info(
        f"Loading Whisper model '{whisper_model}' on {device} (compute_type={compute_type})"
    )
    from faster_whisper import WhisperModel  # type: ignore[reportMissingImports]
    whisper = WhisperModel(
        model_size_or_path=whisper_model,
        device=device,
        compute_type=compute_type,
    )
    logger.info("Whisper model loaded successfully")

    accepted_languages = {
        "af","am","ar","as","az","ba","be","bg","bn","bo","br","bs","ca","cs",
        "cy","da","de","el","en","es","et","eu","fa","fi","fo","fr","gl","gu",
        "ha","haw","he","hi","hr","ht","hu","hy","id","is","it","ja","jw","ka",
        "kk","km","kn","ko","la","lb","ln","lo","lt","lv","mg","mi","mk","ml",
        "mn","mr","ms","mt","my","ne","nl","nn","no","oc","pa","pl","ps","pt",
        "ro","ru","sa","sd","si","sk","sl","sn","so","sq","sr","su","sv","sw",
        "ta","te","tg","th","tk","tl","tr","tt","uk","ur","uz","vi","yi","yo",
        "zh","yue",
    }
    lang_param = language if language in accepted_languages else None

    logger.info(f"Transcribing {wav_path} with language={lang_param}")

    try:
        segments_iter, info = whisper.transcribe(
            wav_path,
            beam_size=5,
            word_timestamps=False,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            language=lang_param,
        )
    except Exception as e:
        raise RuntimeError(f"Whisper transcription failed for {wav_path}: {e}") from e

    segment_list: List[Dict[str, Any]] = []
    full_text: List[str] = []
    for seg in segments_iter:
        segment_list.append({"text": seg.text, "start": seg.start, "end": seg.end})
        full_text.append(seg.text)

    detected_language = info.language if hasattr(info, "language") else language or ""
    logger.info(
        f"Transcription complete: {len(segment_list)} segments, "
        f"text length={len(full_text)}, lang={detected_language}"
    )

    return {
        "text": " ".join(full_text),
        "segments": segment_list,
        "language": detected_language,
        "whisper_model": whisper_model,
    }


def load_preexisting_transcript(
    video_stem: str,
    uploads_dir: str,
) -> Optional[Dict[str, Any]]:
    """
    Load a pre-existing ``transcript.json`` from the uploads directory.

    Resolves the correct directory name by stripping common suffixes
    (``_720p``, ``_dedup``) from *video_stem* and checking each candidate
    until ``transcript.json`` is found.

    Args:
        video_stem: The stem of the video filename (without extension).
            May include suffixes like ``_720p`` or ``_dedup``.
        uploads_dir: Path to the uploads root directory.

    Returns:
        Transcript dictionary (with ``text``, ``segments``, ``language`` keys)
        if found and valid, or ``None``.
    """
    uploads = Path(uploads_dir)

    # Build candidate directory names, stripping suffixes in priority order.
    candidates: List[str] = [video_stem]
    if video_stem.endswith("_dedup_720p"):
        candidates.append(video_stem.replace("_dedup_720p", ""))
    if "_720p" in video_stem:
        candidates.append(video_stem.replace("_720p", ""))
    if "_dedup" in video_stem:
        candidates.append(video_stem.replace("_dedup", ""))

    # Try each candidate directory for transcript.json.
    seen: set = set()
    for stem in candidates:
        if stem in seen:
            continue
        seen.add(stem)
        transcript_path = uploads / stem / "transcript.json"
        if transcript_path.exists():
            try:
                data = json.loads(transcript_path.read_text())
                if not isinstance(data, dict):
                    logger.warning(
                        f"Transcript {transcript_path} is not a dictionary, skipping"
                    )
                    continue
                if "text" not in data:
                    data["text"] = ""
                if "segments" not in data:
                    data["segments"] = []
                logger.info(
                    f"Loaded pre-existing transcript from {transcript_path}: "
                    f"{len(data.get('segments', []))} segments"
                )
                return data
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse {transcript_path}: {e}")
            except Exception as e:
                logger.error(f"Error reading {transcript_path}: {e}")

    logger.info(
        f"No pre-existing transcript found for video stem '{video_stem}' "
        f"in {uploads}"
    )
    return None
