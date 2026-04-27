import json
import click
from src.cli.api_client import APIClient
from src.cli.socketio_client import SocketIOAnalyzer
from src.cli.output import Formatter
from src.cli.config import resolve_url, resolve_openrouter_key


@click.group(name="jobs")
@click.option("--url", default=None, help="Server URL")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def jobs(ctx, url, as_json):
    ctx.ensure_object(dict)
    actual_url = url or ctx.obj.get("url")
    ctx.obj["client"] = APIClient(resolve_url(actual_url))
    ctx.obj["fmt"] = Formatter()
    ctx.obj["as_json"] = as_json


@jobs.command(name="list")
@click.pass_context
def list_jobs(ctx):
    try:
        result = ctx.obj["client"].list_jobs()
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    if not result:
        ctx.obj["fmt"].info("No jobs found")
        return
    headers = ["Job ID", "Status", "Stage", "Model", "Provider", "Priority"]
    rows = [[
        j.get("job_id", ""),
        j.get("status", ""),
        j.get("stage", ""),
        j.get("model_id", "")[:40],
        j.get("provider_name", ""),
        j.get("priority", 0),
    ] for j in result]
    ctx.obj["fmt"].print_table(headers, rows, title="Jobs")


@jobs.command()
@click.argument("id")
@click.pass_context
def status(ctx, id):
    try:
        result = ctx.obj["client"].get_job(id)
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    ctx.obj["fmt"].print_key_value([
        ("Job ID", result.get("job_id", "?")),
        ("Status", result.get("status", "?")),
        ("Stage", result.get("stage", "?")),
        ("Progress", f"{result.get('progress', 0)}%"),
        ("Frames", f"{result.get('current_frame', '?')}/{result.get('total_frames', '?')}"),
        ("Model", result.get("model_id", "?")[:60]),
        ("Provider", result.get("provider_name", "?")),
        ("Priority", result.get("priority", 0)),
        ("GPU", result.get("gpu", "?")),
    ], title=f"Job {id}")


@jobs.command()
@click.argument("id")
@click.pass_context
def cancel(ctx, id):
    try:
        result = ctx.obj["client"].cancel_job(id)
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    if result.get("success"):
        ctx.obj["fmt"].success(f"Job {id} cancellation initiated")
    else:
        ctx.obj["fmt"].error(result.get("error", "Cannot cancel job"))


@jobs.command()
@click.argument("id")
@click.argument("priority", type=int)
@click.pass_context
def priority(ctx, id, priority):
    ctx.obj["fmt"].info(f"Setting priority of job {id} to {priority}...")
    try:
        result = ctx.obj["client"].update_job_priority(id, priority)
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    if result.get("success"):
        ctx.obj["fmt"].success(f"Priority updated to {priority}")
    else:
        ctx.obj["fmt"].error("Failed to update priority")


@jobs.command()
@click.argument("id")
@click.pass_context
def results(ctx, id):
    try:
        result = ctx.obj["client"].get_results(id)
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    desc = result.get("video_description", {})
    if isinstance(desc, dict):
        desc_text = desc.get("response", desc.get("text", ""))
    elif isinstance(desc, str):
        desc_text = desc
    else:
        desc_text = str(desc)
    ctx.obj["fmt"].print_key_value([
        ("Frames analyzed", len(result.get("frame_analyses", []))),
        ("Has transcript", bool(result.get("transcript"))),
        ("Model", result.get("metadata", {}).get("model", "?")),
    ], title=f"Results: Job {id}")
    if desc_text:
        ctx.obj["fmt"].print({"transcript": ""})
        ctx.obj["fmt"].print_description({"description": desc_text[:500]})


@jobs.command()
@click.argument("id")
@click.option("--limit", type=int, default=50, help="Max frames to show")
@click.option("--offset", type=int, default=0, help="Offset")
@click.pass_context
def frames(ctx, id, limit, offset):
    try:
        result = ctx.obj["client"].get_job_frames(id, limit, offset)
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    ctx.obj["fmt"].print_frames(result)


@jobs.command(name="start")
@click.argument("video-path")
@click.option("--model", required=True, help="Model to use")
@click.option("--provider-type", required=True, type=click.Choice(["ollama", "openrouter"]),
              help="Provider type")
@click.option("--provider-name", default=None, help="Provider name (for ollama)")
@click.option("--ollama-url", default="http://host.docker.internal:11434",
              help="Ollama server URL")
@click.option("--priority", type=int, default=0, help="Job priority")
@click.option("--whisper-model", default="large", help="Whisper transcription model")
@click.option("--language", default="en", help="Transcription language")
@click.option("--temperature", type=float, default=0.0, help="Temperature")
@click.option("--fps", type=int, default=1, help="Frames per second to extract")
@click.option("--frames-per-minute", type=int, default=60, help="Max frames per minute")
@click.option("--similarity-threshold", type=int, default=10, help="Dedup threshold")
@click.option("--pipeline-type", default="standard_two_step", help="Analysis pipeline type")
@click.option("--phase2-provider-type", default=None, help="Phase 2 provider")
@click.option("--phase2-model", default=None, help="Phase 2 model")
@click.pass_context
def start(ctx, video_path, model, provider_type, provider_name, ollama_url,
          priority, whisper_model, language, temperature, fps, frames_per_minute,
          similarity_threshold, pipeline_type, phase2_provider_type, phase2_model):
    client = ctx.obj["client"]
    fmt = ctx.obj["fmt"]

    if not client.check_connection():
        fmt.error(f"Cannot connect to server at {client.base_url}")
        return

    provider_config = {}
    if provider_type == "ollama":
        if not provider_name:
            providers = client.list_providers()
            ollama_provs = [p for p in providers if p.get("name", "").startswith("Ollama")]
            if ollama_provs:
                provider_name = ollama_provs[0]["name"]
            else:
                fmt.error("No Ollama providers configured. Use --provider-name or 'va providers discover'")
                return
        provider_config["ollama_url"] = ollama_url
    elif provider_type == "openrouter":
        provider_name = "OpenRouter"
        api_key = resolve_openrouter_key()
        if not api_key:
            fmt.error("OpenRouter API key not configured. Set OPENROUTER_API_KEY env var or 'va config set openrouter_api_key <key>'")
            return
        provider_config["api_key"] = api_key

    params = {
        "temperature": temperature,
        "whisper_model": whisper_model,
        "language": language,
        "fps": fps,
        "frames_per_minute": frames_per_minute,
        "similarity_threshold": similarity_threshold,
        "pipeline_type": pipeline_type,
    }
    if phase2_provider_type:
        params["phase2_provider_type"] = phase2_provider_type
    if phase2_model:
        params["phase2_model"] = phase2_model

    payload = {
        "video_path": video_path,
        "provider_type": provider_type,
        "provider_name": provider_name,
        "model": model,
        "priority": priority,
        "provider_config": provider_config,
        "params": params,
    }

    fmt.info(f"Starting analysis: {model} on {video_path}")
    fmt.info(f"Connecting to SocketIO at {client.base_url}/socket.io...")

    try:
        analyzer = SocketIOAnalyzer(client.base_url, fmt)
    except ImportError:
        fmt.error("python-socketio not installed. Install with: pip install python-socketio")
        return

    if not analyzer.connect():
        fmt.error("Failed to connect to SocketIO server")
        return

    got_job = analyzer.start_analysis(payload)
    if not got_job:
        fmt.error("Start analysis failed (no job_id received)")
        analyzer.disconnect()
        return

    fmt.success(f"Job created: {got_job}")

    # Stay connected and wait for job_complete
    fmt.info("Monitoring job progress (Ctrl+C to stop monitoring)")
    try:
        while True:
            if not analyzer.sio.connected:
                break
            analyzer.sio.wait(seconds=5)
    except KeyboardInterrupt:
        fmt.info("\nStopped monitoring. Job may still be running.")

    analyzer.disconnect()
