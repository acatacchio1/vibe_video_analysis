import click
from src.cli.api_client import APIClient
from src.cli.output import Formatter
from src.cli.config import resolve_url, resolve_openrouter_key


@click.group(name="llm")
@click.option("--url", default=None, help="Server URL")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def llm(ctx, url, as_json):
    ctx.ensure_object(dict)
    actual_url = url or ctx.obj.get("url")
    ctx.obj["client"] = APIClient(resolve_url(actual_url))
    ctx.obj["fmt"] = Formatter()
    ctx.obj["as_json"] = as_json


@llm.command()
@click.argument("model")
@click.argument("prompt")
@click.option("--provider-type", default="ollama", type=click.Choice(["ollama", "openrouter"]),
              help="Provider type")
@click.option("--ollama-url", default="http://host.docker.internal:11434",
              help="Ollama server URL")
@click.option("--temperature", type=float, default=0.1, help="Temperature")
@click.option("--content", default="", help="Additional content/context")
@click.pass_context
def chat(ctx, model, prompt, provider_type, ollama_url, temperature, content):
    client = ctx.obj["client"]
    fmt = ctx.obj["fmt"]
    api_key = ""
    if provider_type == "openrouter":
        api_key = resolve_openrouter_key()
        if not api_key:
            fmt.error("OpenRouter API key not configured")
            return
    fmt.info(f"Submitting chat job to {provider_type}/{model}...")
    try:
        result = client.submit_chat(
            provider_type=provider_type,
            model=model,
            prompt=prompt,
            content=content,
            temperature=temperature,
            api_key=api_key,
            ollama_url=ollama_url,
        )
    except Exception as e:
        fmt.error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    job_id = result.get("job_id")
    if job_id:
        fmt.success(f"Chat submitted: job {job_id}")
        fmt.info("Polling for result...")
        import time
        terminal = {"completed", "failed", "cancelled", "error"}
        for _ in range(120):
            time.sleep(2)
            try:
                status = client.get_chat_status(job_id)
            except Exception:
                fmt.error("Lost connection to server")
                return
            st = status.get("status", "")
            if st in terminal:
                if st == "completed":
                    fmt.success("Chat completed")
                    resp_text = status.get("response", status.get("text", status.get("data", "")))
                    if isinstance(resp_text, dict):
                        resp_text = resp_text.get("content", resp_text.get("text", ""))
                    fmt.print_description({"description": str(resp_text)})
                else:
                    fmt.error(f"Chat job {st}")
                return
            print(f"\r  [{st}>8s] polling...", end="", flush=True)
        fmt.error("Timed out waiting for chat response")
    else:
        fmt.error(result.get("error", "Chat submission failed"))


@llm.command()
@click.argument("id")
@click.pass_context
def status(ctx, id):
    try:
        result = ctx.obj["client"].get_chat_status(id)
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    ctx.obj["fmt"].print_key_value([
        ("Job ID", result.get("job_id", id)),
        ("Status", result.get("status", "?")),
    ])


@llm.command()
@click.argument("id")
@click.pass_context
def cancel(ctx, id):
    try:
        result = ctx.obj["client"].cancel_chat(id)
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if result.get("success"):
        ctx.obj["fmt"].success(f"Chat job {id} cancelled")
    else:
        ctx.obj["fmt"].error(result.get("error", "Cannot cancel job"))


@llm.command(name="queue-stats")
@click.pass_context
def queue_stats(ctx):
    try:
        result = ctx.obj["client"].get_queue_stats()
    except Exception as e:
        ctx.obj["fmt"].error(str(e))
        return
    if ctx.obj["as_json"]:
        ctx.obj["fmt"].print_json(result)
        return
    ctx.obj["fmt"].print_key_value([
        ("Queued", result.get("queued", 0)),
        ("Running", result.get("running", 0)),
        ("Completed", result.get("completed", 0)),
        ("Failed", result.get("failed", 0)),
    ], title="Chat Queue")
