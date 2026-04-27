import click
from src.cli.api_client import APIClient
from src.cli.output import Formatter
from src.cli.config import resolve_url, resolve_openwebui_url, resolve_openwebui_key


@click.group(name="knowledge")
@click.option("--url", default=None, help="Server URL")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def knowledge(ctx, url, as_json):
    ctx.ensure_object(dict)
    actual_url = url or ctx.obj.get("url")
    ctx.obj["client"] = APIClient(resolve_url(actual_url))
    ctx.obj["fmt"] = Formatter()
    ctx.obj["as_json"] = as_json


@knowledge.command()
@click.pass_context
def status(ctx):
    try:
        result = ctx.obj["client"].get_kb_status()
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    ctx.obj["fmt"].print_key_value([
        ("Enabled", result.get("enabled", False)),
        ("URL", result.get("url", "<not set>")),
        ("API Key", "***" if result.get("has_api_key") else "<not set>"),
        ("Knowledge Base", result.get("knowledge_base_name", "?")),
        ("Auto Sync", result.get("auto_sync", True)),
    ], title="OpenWebUI KB Status")
    conn = result.get("connection", {})
    if conn:
        ctx.obj["fmt"].print_key_value([
            ("Connection", "OK" if conn.get("ok") else conn.get("error", "Unknown")),
        ])


@knowledge.command()
@click.option("--enable", is_flag=True, help="Enable KB sync")
@click.option("--disable", is_flag=True, help="Disable KB sync")
@click.option("--url", default=None, help="OpenWebUI URL")
@click.option("--api-key", default=None, help="OpenWebUI API key")
@click.option("--kb-name", default=None, help="Knowledge base name")
@click.option("--auto-sync/--no-auto-sync", default=None, help="Auto-sync on completion")
@click.pass_context
def config(ctx, enable, disable, url, api_key, kb_name, auto_sync):
    client = ctx.obj["client"]
    fmt = ctx.obj["fmt"]
    body = {}
    if enable or disable:
        body["enabled"] = enable or (not disable)
    if url:
        body["url"] = url
    if api_key:
        body["api_key"] = api_key
    if kb_name:
        body["knowledge_base_name"] = kb_name
    if auto_sync is not None:
        body["auto_sync"] = auto_sync
    if not body:
        fmt.info("No changes specified")
        return
    try:
        result = client.save_kb_config(**body)
    except Exception as e:
        fmt.error(str(e))
        return
    if result.get("success"):
        fmt.success("OpenWebUI config saved")
    else:
        fmt.error(result.get("error", "Failed to save config"))


@knowledge.command()
@click.option("--url", default=None, help="OpenWebUI URL")
@click.option("--api-key", default=None, help="OpenWebUI API key")
@click.pass_context
def test(ctx, url, api_key):
    client = ctx.obj["client"]
    fmt = ctx.obj["fmt"]
    if not url and not api_key:
        url = resolve_openwebui_url()
        api_key = resolve_openwebui_key()
    if not url or not api_key:
        fmt.error("Provide --url and --api-key (or configure with 'va knowledge config')")
        return
    fmt.info("Testing connection...")
    try:
        result = client.test_kb_connection(url, api_key)
    except Exception as e:
        fmt.error(str(e))
        return
    if result.get("ok"):
        fmt.success("Connection OK")
    else:
        fmt.error(result.get("error", "Connection failed"))


@knowledge.command()
@click.argument("id")
@click.pass_context
def sync(ctx, id):
    ctx.obj["fmt"].info(f"Syncing job {id} to KB...")
    try:
        result = ctx.obj["client"].sync_job_to_kb(id)
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    if result.get("success"):
        ctx.obj["fmt"].success(f"Job {id} synced to KB")
    else:
        ctx.obj["fmt"].error(result.get("error", "Sync failed"))


@knowledge.command(name="sync-all")
@click.pass_context
def sync_all(ctx):
    ctx.obj["fmt"].info("Syncing all jobs to KB...")
    try:
        result = ctx.obj["client"].sync_all_to_kb()
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    ctx.obj["fmt"].print_key_value([
        ("Total", result.get("total", 0)),
        ("Synced", result.get("synced", 0)),
        ("Failed", result.get("failed", 0)),
        ("Skipped", result.get("skipped", 0)),
    ], title="KB Sync Results")


@knowledge.command()
@click.pass_context
def bases(ctx):
    try:
        result = ctx.obj["client"].list_knowledge_bases()
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    bs = result.get("bases", [])
    if not bs:
        ctx.obj["fmt"].info("No knowledge bases found")
        return
    ctx.obj["fmt"].print_key_value([("Count", len(bs))])
    for b in bs:
        name = b.get("name", b.get("id", "?"))
        bid = b.get("id", "?")
        print(f"  [{bid}] {name}")
    print()


@knowledge.command()
@click.argument("id")
@click.option("--kb-id", default=None, help="KB ID")
@click.option("--kb-name", default=None, help="KB name")
@click.pass_context
def send(ctx, id, kb_id, kb_name):
    if not kb_id and not kb_name:
        ctx.obj["fmt"].error("Specify --kb-id or --kb-name")
        return
    ctx.obj["fmt"].info(f"Sending job {id} to KB...")
    try:
        result = ctx.obj["client"].send_to_kb(id, kb_id or "", kb_name or "")
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    if result.get("success"):
        fmt = ctx.obj["fmt"]
        fmt.success(f"Job {id} sent to KB '{result.get('kb_name', '?')}'")
    else:
        ctx.obj["fmt"].error(result.get("error", "Send failed"))
