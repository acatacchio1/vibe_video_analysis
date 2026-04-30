import click
from src.cli.api_client import APIClient
from src.cli.output import Formatter
from src.cli.config import resolve_url


@click.group(name="providers")
@click.option("--url", default=None, help="Server URL")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def providers(ctx, url, as_json):
    ctx.ensure_object(dict)
    actual_url = url or ctx.obj.get("url")
    ctx.obj["client"] = APIClient(resolve_url(actual_url))
    ctx.obj["fmt"] = Formatter()
    ctx.obj["as_json"] = as_json


@providers.command(name="list")
@click.pass_context
def list_providers(ctx):
    try:
        result = ctx.obj["client"].list_providers()
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    if not result:
        ctx.obj["fmt"].info("No providers configured")
        return
    headers = ["Name", "Status", "Type"]
    rows = [[
        p.get("name", ""),
        p.get("status", ""),
        p.get("type", ""),
    ] for p in result]
    ctx.obj["fmt"].print_table(headers, rows, title="Providers")


@providers.command()
@click.pass_context
def discover(ctx):
    ctx.obj["fmt"].info("Scanning network for AI instances (this may take ~30s)...")
    try:
        result = ctx.obj["client"].discover_providers()
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    ctx.obj["fmt"].success(f"Discovered {result.get('discovered', 0)} instances")
    for url in result.get("urls", []):
        ctx.obj["fmt"].info(f"  - {url}")


@providers.command(name="status")
@click.pass_context
def litellm_status(ctx):
    """Check LiteLLM status and list available models."""
    try:
        result = ctx.obj["client"].get_litellm_status()
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    models = result.get("models", [])
    ctx.obj["fmt"].success(f"LiteLLM online - {len(models)} models available")
    for m in models[:20]:
        ctx.obj["fmt"].info(f"  - {m.get('id', m.get('name', str(m)))}")
    if len(models) > 20:
        ctx.obj["fmt"].info(f"  ... and {len(models) - 20} more")
