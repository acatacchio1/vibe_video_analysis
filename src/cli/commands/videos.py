from pathlib import Path
import click
from src.cli.api_client import APIClient
from src.cli.output import Formatter
from src.cli.config import resolve_url


@click.group(name="videos")
@click.option("--url", default=None, help="Server URL")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def videos(ctx, url, as_json):
    ctx.ensure_object(dict)
    actual_url = url or ctx.obj.get("url")
    ctx.obj["client"] = APIClient(resolve_url(actual_url))
    ctx.obj["fmt"] = Formatter()
    ctx.obj["as_json"] = as_json


@videos.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--whisper-model", default="base", help="Whisper model to use")
@click.option("--language", default="en", help="Language code")
@click.pass_context
def upload(ctx, file, whisper_model, language):
    path = Path(file)
    try:
        result = ctx.obj["client"].upload_video(path, whisper_model, language)
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    if result.get("success"):
        ctx.obj["fmt"].success(f"Uploaded {result.get('filename', path.name)}")
    else:
        ctx.obj["fmt"].error(result.get("error", "Upload failed"))


@videos.command()
@click.argument("name")
@click.pass_context
def delete(ctx, name):
    try:
        result = ctx.obj["client"].delete_video(name)
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    if result.get("success"):
        ctx.obj["fmt"].success(f"Deleted {name}")
    else:
        ctx.obj["fmt"].error(result.get("error", "Delete failed"))


@videos.command(name="list")
@click.pass_context
def list_videos(ctx):
    try:
        result = ctx.obj["client"].list_videos()
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    for cat, label in [("source_videos", "Source"), ("processed_videos", "Processed")]:
        items = result.get(cat, [])
        if not items:
            continue
        ctx.obj["fmt"].print_key_value([("Category", f"{label} videos ({len(items)})")])
        headers = ["Name", "Size", "Duration", "Frames", "Has Analysis"]
        rows = [[
            v.get("name", ""),
            v.get("size_human", ""),
            v.get("duration_formatted", ""),
            v.get("frame_count", 0),
            "✓" if v.get("has_analysis") else "",
        ] for v in items]
        ctx.obj["fmt"].print_table(headers, rows)


@videos.command()
@click.argument("name")
@click.pass_context
def info(ctx, name):
    try:
        result = ctx.obj["client"].get_frame_meta(name)
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    ctx.obj["fmt"].print_key_value([
        ("Frames", result.get("frame_count", "?")),
        ("FPS", result.get("fps", "?")),
        ("Duration", result.get("duration", "?")),
    ], title=name)


@videos.command()
@click.argument("name")
@click.pass_context
def transcript(ctx, name):
    try:
        result = ctx.obj["client"].get_transcript(name)
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    ctx.obj["fmt"].print_key_value([
        ("Language", result.get("language", "?")),
        ("Whisper model", result.get("whisper_model", "?")),
    ])
    txt = result.get("text", "")
    if txt:
        ctx.obj["fmt"].print_transcript({"transcript": txt})


@videos.command(name="frames-index")
@click.argument("name")
@click.pass_context
def frames_index(ctx, name):
    try:
        result = ctx.obj["client"].get_frames_index(name)
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    if not result:
        ctx.obj["fmt"].info("No frames index found")
        return
    headers = ["Frame #", "Timestamp"]
    rows = [[k, f"{v}s"] for k, v in result.items()]
    ctx.obj["fmt"].print_table(headers, rows[:100], title=f"{name} (showing first 100)")


@videos.command()
@click.argument("name")
@click.option("--threshold", type=int, default=10, help="Phash similarity threshold")
@click.pass_context
def dedup(ctx, name, threshold):
    ctx.obj["fmt"].info(f"Running dedup on {name} with threshold {threshold}...")
    try:
        result = ctx.obj["client"].run_dedup(name, threshold)
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    ctx.obj["fmt"].print_key_value([
        ("Original", result.get("original_count", "?")),
        ("Deduped", result.get("deduped_count", "?")),
        ("Dropped", result.get("dropped", "?")),
        ("Dropped %", f"{result.get('dropped_pct', '?')}%"),
    ], title="Dedup Results")


@videos.command(name="dedup-multi")
@click.argument("name")
@click.option("--thresholds", default="5,10,15,20,30",
              help="Comma-separated thresholds")
@click.pass_context
def dedup_multi(ctx, name, thresholds):
    ts = [int(t.strip()) for t in thresholds.split(",")]
    ctx.obj["fmt"].info(f"Running multi-threshold dedup on {name}...")
    try:
        result = ctx.obj["client"].run_dedup_multi(name, ts)
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    headers = ["Threshold", "Kept", "Dropped", "Drop %", "Duration"]
    by_thresh = result.get("keep_indices_by_threshold", {})
    original = result.get("original_count", 0)
    rows = [[
        t,
        len(v),
        original - len(v),
        f"{round((original - len(v)) / original * 100, 1)}%" if original else "0%",
        result.get("duration", "?"),
    ] for t, v in sorted(by_thresh.items(), key=lambda x: int(x[0]))]
    ctx.obj["fmt"].print_table(headers, rows, title=f"Multi-dedup: {name}")
    ctx.obj["fmt"].info("Apply a threshold with: va videos dedup <name> --threshold <value>")


@videos.command()
@click.argument("name")
@click.option("--detector-type", default="content", help="Detector type")
@click.option("--threshold", type=float, default=30.0, help="Scene threshold")
@click.option("--min-scene-len", type=int, default=15, help="Min scene length in frames")
@click.pass_context
def scenes(ctx, name, detector_type, threshold, min_scene_len):
    ctx.obj["fmt"].info(f"Detecting scenes in {name}...")
    try:
        result = ctx.obj["client"].detect_scenes(name, detector_type, threshold, min_scene_len)
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    ctx.obj["fmt"].print_key_value([
        ("FPS", result.get("fps", "?")),
        ("Detector", result.get("detector_config", {}).get("detector_type", "?")),
    ], title=f"Scenes: {name}")
    scenes_list = result.get("scenes", [])
    stats = result.get("statistics", {})
    ctx.obj["fmt"].print_key_value([
        ("Total scenes", stats.get("total_scenes", len(scenes_list))),
        ("Avg frames/scene", stats.get("avg_frames_per_scene", "?")),
        ("Detection time", f"{result.get('detection_time', '?'):.2f}s"),
    ])
    headers = ["Scene #", "Start Frame", "End Frame", "Start Time", "End Time", "Duration"]
    rows = []
    for i, s in enumerate(scenes_list):
        d = s if isinstance(s, dict) else s.to_dict() if hasattr(s, "to_dict") else {}
        rows.append([
            i + 1,
            d.get("start_frame", "?"),
            d.get("end_frame", "?"),
            f"{d.get('start_time', '?'):.1f}s",
            f"{d.get('end_time', '?'):.1f}s",
            f"{d.get('duration', '?'):.1f}s",
        ])
    ctx.obj["fmt"].print_table(headers, rows, title="Detected Scenes")


@videos.command(name="scene-dedup")
@click.argument("name")
@click.option("--threshold", type=int, default=10, help="Dedup threshold")
@click.option("--scene-threshold", type=float, default=30.0, help="Scene detection threshold")
@click.option("--min-scene-len", type=int, default=15, help="Min scene length")
@click.pass_context
def scene_dedup(ctx, name, threshold, scene_threshold, min_scene_len):
    ctx.obj["fmt"].info(f"Running scene-aware dedup on {name}...")
    try:
        result = ctx.obj["client"].scene_aware_dedup(name, threshold, scene_threshold, min_scene_len)
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    perf = result.get("performance", {})
    ctx.obj["fmt"].print_key_value([
        ("Total time", f"{perf.get('total_time', '?'):.2f}s"),
        ("Scene detection", f"{perf.get('scene_detection_time', '?'):.2f}s"),
        ("Dedup time", f"{perf.get('dedup_time', '?'):.2f}s"),
    ], title="Scene-Aware Dedup")
    dedup = result.get("results", {})
    ctx.obj["fmt"].print_key_value([
        ("Original", dedup.get("original_count", "?")),
        ("Deduped", dedup.get("deduped_count", "?")),
        ("Dropped", dedup.get("dropped", "?")),
    ])
