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
    ctx.obj["fmt"].info("Scanning network for Ollama instances (this may take ~30s)...")
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


@providers.command(name="add-ollama")
@click.argument("url")
@click.pass_context
def add_ollama(ctx, url):
    client = ctx.obj["client"]
    fmt = ctx.obj["fmt"]
    try:
        current = client.get_ollama_instances().get("instances", [])
    except Exception:
        current = []
    if url not in current:
        current.append(url)
    try:
        result = client.update_ollama_instances(current)
    except Exception as e:
        fmt.error(str(e))
        return
    if result.get("ok"):
        fmt.success(f"Added Ollama instance: {url}")
    else:
        fmt.error(result.get("error", "Failed to add instance"))


@providers.command(name="instances")
@click.pass_context
def instances(ctx):
    try:
        result = ctx.obj["client"].get_ollama_instances()
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    insts = result.get("instances", [])
    if not insts:
        ctx.obj["fmt"].info("No Ollama instances configured")
        return
    for u in insts:
        print(f"  {u}")
    print()
