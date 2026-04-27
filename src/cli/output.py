"""Terminal output formatting for CLI."""
import json
import sys
from typing import Any

try:
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.panel import Panel
    _HAVE_RICH = True
except ImportError:
    _HAVE_RICH = False


class Formatter:
    """Terminal output formatter with rich fallback to plain text."""

    def __init__(self):
        self.console = Console() if _HAVE_RICH else None

    def print_json(self, data: Any, indent: int = 2):
        print(json.dumps(data, indent=indent, default=str))

    def print_table(self, headers, rows, title=None):
        if self.console:
            table = Table(title=title if title else None,
                          header_style="bold green", border_style="dim")
            for h in headers:
                table.add_column(str(h))
            for row in rows:
                table.add_row(*[str(v) for v in row])
            self.console.print(table)
        else:
            if title:
                print(f"\n{title}")
                print("=" * len(title))
            widths = [len(str(h)) for h in headers]
            for i, row in enumerate(rows):
                for j, val in enumerate(row):
                    widths[j] = max(widths[j], len(str(val)))
            fmt = "  ".join(f"{{:<{w}}}" for w in widths)
            header_line = fmt.format(*headers)
            print(header_line)
            print("  ".join("-" * w for w in widths))
            for row in rows:
                print(fmt.format(*[str(v) for v in row]))
            print()

    def print_key_value(self, pairs, title=None):
        if title and self.console:
            self.console.print(Panel("\n".join(f"[bold]{k}[/bold]: {v}" for k, v in pairs),
                                    title=title))
        else:
            if title:
                print(f"\n{title}")
                print("=" * len(title))
            for k, v in pairs:
                print(f"  {k}: {v}")
            print()

    def success(self, msg):
        if self.console:
            self.console.print(f"[green]✓ {msg}[/green]")
        else:
            print(f"OK: {msg}")

    def error(self, msg):
        if self.console:
            self.console.print(f"[red]✗ {msg}[/red]")
        else:
            print(f"ERROR: {msg}", file=sys.stderr)

    def info(self, msg):
        if self.console:
            self.console.print(f"[dim]{msg}[/dim]")
        else:
            print(msg)

    def spinner_progress(self, description="Working"):
        if self.console:
            return Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=self.console,
            )
        return None

    def bar_progress(self, total=100):
        if self.console:
            prog = Progress(
                TextColumn("[bold blue]{task.description}"),
                BarColumn(bar_width=30),
                "{task.percentage:>3.1f}%",
                console=self.console,
            )
            task_id = prog.add_task(description, total=total)
            return prog, task_id
        return None, None

    def print_frames(self, frames):
        if not frames:
            self.info("No frame analyses available")
            return
        headers = ["Frame", "Timestamp", "Analysis"]
        rows = []
        for f in frames:
            num = f.get("frame_number", "?")
            ts = f"{f.get('timestamp', '?'):.1f}s" if "timestamp" in f else "?"
            analysis = (f.get("analysis", "") or "")[:80]
            if len(f.get("analysis", "")) > 80:
                analysis += "…"
            rows.append([num, ts, analysis])
        self.print_table(headers, rows, title="Frame Analyses")

    def print_job_status(self, data, end=""):
        status = data.get("status", "?")
        progress = data.get("progress", 0)
        stage = data.get("stage", "?")
        cur = data.get("current_frame", "?")
        tot = data.get("total_frames", "?")
        line = f"  [{status:>12s}] {stage:<20s} {progress:>3}%  frames {cur}/{tot}"
        if self.console:
            color = {"completed": "green", "failed": "red", "cancelled": "yellow"}.get(
                status, "white")
            self.console.print(f"[{color}]{line}[/{color}]", end=end)
        else:
            print(line, end=end, flush=True)

    def print_frame_update(self, data):
        num = data.get("frame_number", "?")
        analysis = data.get("analysis", "")[:100]
        ts = data.get("timestamp", "?")
        if self.console:
            self.console.print(f"\n  Frame {num} ({ts:.1f}s): [dim]{analysis}[/dim]")
        else:
            print(f"\n  Frame {num} ({ts:.1f}s): {analysis}")

    def print_synthesis_update(self, data):
        num = data.get("frame_number", "?")
        combined = data.get("combined_analysis", "")[:120]
        if self.console:
            self.console.print(f"\n  Synthesis {num}: [dim]{combined}[/dim]")
        else:
            print(f"\n  Synthesis {num}: {combined}")

    def print_job_complete(self, data, success):
        if success:
            self.success(f"Job {data.get('job_id', '?')} completed")
        else:
            self.error(f"Job {data.get('job_id', '?')} failed")

    def print_transcript(self, data, max_lines=30):
        text = data.get("transcript", "")
        lines = text.split("\n") if text else []
        prefix = "Transcript"
        if len(lines) > max_lines:
            lines = lines[:max_lines] + ["..."]
        if self.console:
            self.console.print(f"\n[dim]{prefix}:[/dim]\n[dim]{chr(10).join(lines)}[/dim]\n")
        else:
            print(f"\n{prefix}:")
            for line in lines:
                print(f"  {line}")
            print()

    def print_description(self, data):
        desc = data.get("description", "")
        prefix = "Video Description"
        if self.console:
            self.console.print(f"\n[dim]{prefix}:[/dim]\n{desc}\n")
        else:
            print(f"\n{prefix}:")
            print(f"  {desc}")
            print()

    def pretty_print(self, data, as_json=False):
        if as_json:
            self.print_json(data)
            return
        if isinstance(data, dict):
            self.print_key_value(data.items())
        elif isinstance(data, list):
            if not data:
                self.info("No results")
                return
            if isinstance(data[0], dict):
                headers = sorted({k for d in data for k in d.keys()})
                rows = [[d.get(h, "") for h in headers] for d in data]
                self.print_table(headers, rows)
            else:
                for item in data:
                    print(f"  {item}")
        else:
            print(data)
