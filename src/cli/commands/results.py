import click
from src.cli.api_client import APIClient
from src.cli.output import Formatter
from src.cli.config import resolve_url


@click.group(name="results")
@click.option("--url", default=None, help="Server URL")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def results(ctx, url, as_json):
    ctx.ensure_object(dict)
    actual_url = url or ctx.obj.get("url")
    ctx.obj["client"] = APIClient(resolve_url(actual_url))
    ctx.obj["fmt"] = Formatter()
    ctx.obj["as_json"] = as_json


@results.command(name="list")
@click.pass_context
def list_results(ctx):
    try:
        result = ctx.obj["client"].list_results()
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    if not result:
        ctx.obj["fmt"].info("No stored results")
        return
    headers = ["Job ID", "Video", "Model", "Provider", "Frames", "Transcript", "Description"]
    rows = [[
        r.get("job_id", ""),
        r.get("video_path", "")[-40:],
        r.get("model", "")[:30],
        r.get("provider", ""),
        r.get("frame_count", 0),
        "✓" if r.get("has_transcript") else "",
        (r.get("desc_preview", "")[:30] + "…") if len(r.get("desc_preview", "")) > 30 else r.get("desc_preview", ""),
    ] for r in result]
    ctx.obj["fmt"].print_table(headers, rows, title="Stored Results")


@results.command(name="get")
@click.argument("id")
@click.pass_context
def get_result(ctx, id):
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
        ("Job ID", id),
        ("Frames", len(result.get("frame_analyses", []))),
        ("Has transcript", bool(result.get("transcript"))),
    ], title=f"Results: {id}")
    if desc_text:
        ctx.obj["fmt"].print_description({"description": desc_text[:1000]})
