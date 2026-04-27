import click
from src.cli.api_client import APIClient
from src.cli.output import Formatter
from src.cli.config import resolve_url


@click.group(name="system")
@click.option("--url", default=None, help="Server URL")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def system(ctx, url, as_json):
    ctx.ensure_object(dict)
    actual_url = url or ctx.obj.get("url")
    ctx.obj["client"] = APIClient(resolve_url(actual_url))
    ctx.obj["fmt"] = Formatter()
    ctx.obj["as_json"] = as_json


@system.command()
@click.pass_context
def vram(ctx):
    try:
        result = ctx.obj["client"].get_vram_status()
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    gpus = result.get("gpus", [])
    if not gpus:
        ctx.obj["fmt"].info("No GPUs detected")
        return
    headers = ["GPU", "Name", "Total", "Used", "Free", "Jobs"]
    rows = [[
        g.get("index", "?"),
        g.get("name", "?")[:30],
        f"{g.get('total', 0):.1f}GB",
        f"{g.get('used', 0):.1f}GB",
        f"{g.get('free', 0):.1f}GB",
        len(g.get("jobs", [])),
    ] for g in gpus]
    ctx.obj["fmt"].print_table(headers, rows, title="GPU VRAM")


@system.command()
@click.pass_context
def gpus(ctx):
    try:
        result = ctx.obj["client"].get_gpu_list()
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    if not result:
        ctx.obj["fmt"].info("No GPUs detected")
        return
    headers = ["Index", "Name", "Total", "Used", "Free"]
    rows = [[
        g.get("index", "?"),
        g.get("name", "?"),
        f"{g.get('total_gb', 0):.1f}GB",
        f"{g.get('used_gb', 0):.1f}GB",
        f"{g.get('free_gb', 0):.1f}GB",
    ] for g in result]
    ctx.obj["fmt"].print_table(headers, rows, title="GPUs")


@system.command()
@click.option("--enable", is_flag=True, help="Enable debug mode")
@click.option("--disable", is_flag=True, help="Disable debug mode")
@click.pass_context
def debug(ctx, enable, disable):
    client = ctx.obj["client"]
    fmt = ctx.obj["fmt"]
    if enable and disable:
        fmt.error("Use --enable or --disable, not both")
        return
    if enable or disable:
        new_val = enable or not disable
        try:
            result = client.toggle_debug(new_val)
        except Exception as e:
            fmt.error(str(e))
            return
        if result.get("debug") == new_val:
            state = "enabled" if new_val else "disabled"
            fmt.success(f"Debug mode {state}")
        else:
            fmt.error("Failed to toggle debug")
        return
    try:
        result = client.get_debug_status()
    except Exception as e:
        fmt.error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    state = "ON" if result.get("debug") else "OFF"
    fmt.info(f"Debug mode: {state}")
