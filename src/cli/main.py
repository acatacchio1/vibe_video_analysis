import json

import click
from src.cli import config
from src.cli.api_client import APIClient
from src.cli.output import Formatter
from src.cli.commands import videos, jobs, providers, results, system, knowledge, llm


@click.group()
@click.option("--url", default=None, help="Server URL (overrides config)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def cli(ctx, url, as_json):
    ctx.ensure_object(dict)
    ctx.obj["as_json"] = as_json
    if url:
        ctx.obj["url"] = url


cli.add_command(videos.videos, name="videos")
cli.add_command(jobs.jobs, name="jobs")
cli.add_command(providers.providers, name="providers")
cli.add_command(results.results, name="results")
cli.add_command(system.system, name="system")
cli.add_command(knowledge.knowledge, name="knowledge")
cli.add_command(llm.llm, name="llm")


@cli.group(name="config")
@click.pass_context
def config_group(ctx):
    ctx.ensure_object(dict)


@config_group.command(name="show")
@click.pass_context
def config_show(ctx):
    c = config.show_config()
    if ctx.obj.get("as_json"):
        print(json.dumps(c, indent=2))
        return
    for k, v in c.items():
        print(f"  {k}: {v}")


@config_group.command(name="set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def config_set(ctx, key, value):
    config.set_value(key, value)
    print(f"OK: Set {key} = {value}")


@config_group.command(name="unset")
@click.argument("key")
@click.pass_context
def config_unset(ctx, key):
    config.unset_value(key)
    print(f"Unset {key}")


@cli.group(name="models")
@click.option("--url", default=None, help="Server URL")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def models(ctx, url, as_json):
    ctx.ensure_object(dict)
    ctx.obj["client"] = APIClient(config.resolve_url(url))
    ctx.obj["fmt"] = Formatter()
    ctx.obj["as_json"] = as_json


@models.command(name="litellm")
@click.argument("url", required=False, default="http://172.16.17.3:4000/v1")
@click.pass_context
def models_litellm(ctx, url):
    client = ctx.obj["client"]
    fmt = ctx.obj["fmt"]
    try:
        result = client.get_litellm_status()
    except Exception as e:
        fmt.error(str(e))
        return
    if ctx.obj["as_json"]:
        fmt.print_json(result)
        return
    models_list = result.get("models", [])
    fmt.info(f"Models via LiteLLM: {len(models_list)}")
    for m in models_list:
        name = m.get("id", m.get("name", str(m))) if isinstance(m, dict) else str(m)
        print(f"  {name[:60]}")
    if len(models_list) > 50:
        fmt.info(f"  ... and {len(models_list) - 50} more")
    print()


@models.command(name="openrouter")
@click.pass_context
def models_openrouter(ctx):
    client = ctx.obj["client"]
    fmt = ctx.obj["fmt"]
    try:
        result = client.get_openrouter_models()
    except Exception as e:
        fmt.error(str(e))
        return
    if ctx.obj["as_json"]:
        fmt.print_json(result)
        return
    models_list = result.get("models", [])
    fmt.info(f"OpenRouter models: {len(models_list)}")
    for m in models_list[:50]:
        name = m.get("name", m.get("id", "?"))
        print(f"  {name[:60]}")
    if len(models_list) > 50:
        fmt.info(f"  ... and {len(models_list) - 50} more")
    print()


@cli.command()
@click.argument("model")
@click.argument("frames", type=int)
@click.option("--url", default=None, help="Server URL")
@click.pass_context
def cost(ctx, model, frames, url):
    actual_url = url or ctx.obj.get("url")
    client = APIClient(config.resolve_url(actual_url))
    fmt = Formatter()
    try:
        result = client.estimate_cost(model, frames)
    except Exception as e:
        fmt.error(str(e))
        return
    if ctx.obj.get("as_json"):
        fmt.print_json(result)
        return
    fmt.info(f"Estimated cost: ${result.get('estimated_cost', '?')}")
    if result.get("per_frame"):
        fmt.info(f"Per frame: ${result['per_frame']}")


@cli.command()
@click.option("--url", default=None, help="Server URL")
@click.pass_context
def balance(ctx, url):
    actual_url = url or ctx.obj.get("url")
    client = APIClient(config.resolve_url(actual_url))
    fmt = Formatter()
    try:
        result = client.get_balance()
    except Exception as e:
        fmt.error(str(e))
        return
    if ctx.obj.get("as_json"):
        fmt.print_json(result)
        return
    fmt.info(f"Balance: ${result.get('balance', '?')}")
    if result.get("usage"):
        fmt.info(f"Usage: ${result['usage']}")


if __name__ == "__main__":
    cli()
