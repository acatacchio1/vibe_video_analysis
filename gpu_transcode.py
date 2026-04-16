#!/usr/bin/env python3
"""
GPU transcoding utilities with fallback to CPU.
Detects available GPU encoders (NVENC, QSV, VAAPI) and provides appropriate FFmpeg commands.
"""

import subprocess
import logging
from typing import List, Dict, Optional, Tuple
import re

logger = logging.getLogger(__name__)


def detect_gpu_encoders() -> Dict[str, bool]:
    """
    Detect available GPU encoders by running ffmpeg -encoders.
    Returns dict with encoder availability.
    """
    encoders = {
        "nvenc": False,  # NVIDIA NVENC
        "qsv": False,  # Intel Quick Sync Video
        "vaapi": False,  # VAAPI (AMD/Intel)
        "cuda": False,  # CUDA acceleration
    }

    try:
        # Run ffmpeg to list encoders
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            output = result.stdout.lower()

            # Check for NVENC encoders
            if any(x in output for x in ["h264_nvenc", "hevc_nvenc", "av1_nvenc"]):
                encoders["nvenc"] = True
                logger.info("NVENC GPU encoder detected")

            # Check for QSV encoders
            if any(x in output for x in ["h264_qsv", "hevc_qsv", "av1_qsv"]):
                encoders["qsv"] = True
                logger.info("Intel QSV GPU encoder detected")

            # Check for VAAPI
            if "vaapi" in output:
                encoders["vaapi"] = True
                logger.info("VAAPI GPU encoder detected")

            # Check for CUDA
            if "cuda" in output:
                encoders["cuda"] = True
                logger.info("CUDA acceleration available")

    except Exception as e:
        logger.warning(f"Failed to detect GPU encoders: {e}")

    return encoders


def get_gpu_vram_available(gpu_index: int = 0) -> Optional[int]:
    """
    Get available VRAM on specified GPU in bytes.
    Returns None if NVML not available or GPU not found.
    """
    try:
        import pynvml

        pynvml.nvmlInit()
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_index)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            return mem_info.free
        finally:
            pynvml.nvmlShutdown()

    except ImportError:
        logger.debug("pynvml not available for VRAM check")
    except Exception as e:
        logger.warning(f"Failed to get GPU VRAM: {e}")

    return None


def check_gpu_vram_required(video_path: str, gpu_index: int = 0) -> bool:
    """
    Check if enough VRAM is available for GPU transcoding.
    Returns True if sufficient VRAM, False otherwise.
    """
    # Estimate VRAM requirement based on video resolution
    try:
        # Get video resolution
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=p=0",
                video_path,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )

        if probe.returncode == 0:
            dimensions = probe.stdout.strip().split(",")
            if len(dimensions) == 2:
                width = int(dimensions[0])
                height = int(dimensions[1])

                # Rough VRAM estimate: 1.5x frame buffer size * 3 buffers
                pixels = width * height
                bytes_per_pixel = 1.5  # YUV420
                buffers = 3  # Input, output, processing
                estimated_vram = int(pixels * bytes_per_pixel * buffers)

                # Add 10% safety margin
                estimated_vram = int(estimated_vram * 1.1)

                logger.debug(
                    f"Estimated VRAM needed for {width}x{height}: {estimated_vram / (1024**2):.1f}MB"
                )

                # Check available VRAM
                available_vram = get_gpu_vram_available(gpu_index)
                if available_vram is not None:
                    has_enough = available_vram >= estimated_vram
                    logger.info(
                        f"GPU {gpu_index} VRAM: {available_vram / (1024**3):.2f}GB available, {estimated_vram / (1024**3):.2f}GB needed - {'OK' if has_enough else 'INSUFFICIENT'}"
                    )
                    return has_enough

    except Exception as e:
        logger.warning(f"Failed to estimate VRAM requirement: {e}")

    # If we can't estimate, assume it's OK
    return True


def get_best_encoder(video_path: str, gpu_index: int = 0) -> Tuple[str, List[str]]:
    """
    Determine the best encoder to use for transcoding.
    Returns (encoder_type, ffmpeg_args) where encoder_type is one of:
    "nvenc", "qsv", "vaapi", "cpu"
    """
    encoders = detect_gpu_encoders()

    # Force CPU encoding for now to avoid NVENC driver issues
    # TODO: Restore GPU encoding when driver compatibility is fixed
    logger.info("Using CPU encoding (libx264) with thread optimization (GPU disabled)")
    cpu_count = get_cpu_thread_count()
    args = [
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-threads",
        str(cpu_count),
    ]
    return "cpu", args


def get_cpu_thread_count() -> int:
    """Get optimal CPU thread count for transcoding."""
    try:
        import multiprocessing

        cpu_count = multiprocessing.cpu_count()

        # Use 30 threads if available, otherwise use 75% of available cores
        if cpu_count >= 40:
            return 30
        else:
            return max(1, int(cpu_count * 0.75))

    except Exception:
        # Fallback to 4 threads if we can't detect
        return 4


def build_transcode_command(
    input_path: str,
    output_path: str,
    width: int = 1280,
    height: int = 720,
    fps: int = 1,
    gpu_index: int = 0,
) -> List[str]:
    """
    Build FFmpeg command for transcoding with appropriate encoder.
    """
    # Force CPU encoding for now
    logger.info("FORCING CPU ENCODING - bypassing GPU detection")
    cpu_count = get_cpu_thread_count()
    encoder_args = [
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-threads",
        str(cpu_count),
    ]
    encoder_type = "cpu"

    # Base command
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-vf",
        f"scale={width}:{height},fps={fps}",
    ]

    # Add encoder-specific arguments
    cmd.extend(encoder_args)

    # Audio settings (same for all)
    cmd.extend(
        [
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "44100",
            "-progress",
            "pipe:1",
            "-nostats",
            output_path,
        ]
    )

    # Add GPU-specific initialization if needed
    if encoder_type == "nvenc":
        # NVENC works with CUDA context
        cmd.insert(1, "-hwaccel")
        cmd.insert(2, "cuda")
        cmd.insert(3, "-hwaccel_output_format")
        cmd.insert(4, "cuda")

    elif encoder_type == "qsv":
        # QSV requires MFX initialization
        cmd.insert(1, "-hwaccel")
        cmd.insert(2, "qsv")
        cmd.insert(3, "-hwaccel_output_format")
        cmd.insert(4, "qsv")

    return cmd


def get_transcode_progress_parser(encoder_type: str):
    """
    Get progress parser function for the encoder type.
    Different encoders may output progress differently.
    """

    def parse_nvenc_progress(
        line: str, current_time_s: float, duration_s: float
    ) -> Optional[float]:
        """Parse NVENC progress output."""
        if line.startswith("out_time_ms="):
            try:
                current_time_s = int(line.split("=")[1]) / 1_000_000
                if duration_s > 0:
                    return min(current_time_s / duration_s * 100, 99)
            except ValueError:
                pass
        return None

    def parse_standard_progress(
        line: str, current_time_s: float, duration_s: float
    ) -> Optional[float]:
        """Parse standard FFmpeg progress output."""
        if line.startswith("out_time_ms="):
            try:
                current_time_s = int(line.split("=")[1]) / 1_000_000
                if duration_s > 0:
                    return min(current_time_s / duration_s * 100, 99)
            except ValueError:
                pass
        return None

    # Currently all encoders use standard progress output
    return parse_standard_progress
