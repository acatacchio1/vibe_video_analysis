import subprocess
import threading
import time
import logging
import requests
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


class SystemMonitor:
    """Monitors system status (nvidia-smi, ollama ps via API)"""

    def __init__(self):
        self.nvidia_smi_interval = 10  # seconds
        self.ollama_ps_interval = (
            15  # seconds - more frequent since it's just an API call
        )
        self.callbacks: List[Callable] = []
        self.running = False
        self.last_nvidia = ""
        self.last_ollama = ""
        self.last_gpus = []
        self._ollama_url_provider: Optional[Callable[[], Optional[str]]] = None

    def set_ollama_url_provider(self, provider: Callable[[], Optional[str]]):
        """Set a callable that returns the current Ollama URL (or None if unavailable)"""
        self._ollama_url_provider = provider

    def get_ollama_url(self) -> Optional[str]:
        """Get current Ollama URL from provider or None"""
        if self._ollama_url_provider:
            return self._ollama_url_provider()
        return None

    def register_callback(self, callback: Callable):
        """Register callback for status updates"""
        self.callbacks.append(callback)

    def _notify(self, data_type: str, data, error: str = None):
        """Notify all callbacks"""
        payload = {
            "type": data_type,
            "data": data,
            "error": error,
            "timestamp": time.time(),
        }
        for callback in self.callbacks:
            try:
                callback(payload)
            except Exception as e:
                logger.error(f"Monitor callback error: {e}")

    def _get_nvidia_stats(self):
        """
        Returns structured per-GPU stats:
        - utilization %
        - VRAM used / total
        - per-process VRAM usage
        """
        try:
            # Query per-GPU utilization and memory
            gpu_result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=index,name,utilization.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            # Query per-process memory usage
            proc_result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-compute-apps=gpu_uuid,pid,used_memory,process_name",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            # Also get GPU UUIDs so we can map uuid -> index
            uuid_result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=index,gpu_uuid",
                    "--format=csv,noheader",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if gpu_result.returncode != 0:
                return None, gpu_result.stderr

            # Parse UUID -> index mapping
            uuid_to_idx = {}
            for line in uuid_result.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) == 2:
                    uuid_to_idx[parts[1]] = int(parts[0])

            # Parse per-process info
            procs_by_gpu = {}  # gpu_index -> list of {pid, mem_mb, name}
            if proc_result.returncode == 0:
                for line in proc_result.stdout.strip().splitlines():
                    if not line.strip():
                        continue
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) == 4:
                        gpu_uuid, pid, mem_mb, proc_name = parts
                        gpu_idx = uuid_to_idx.get(gpu_uuid, -1)
                        if gpu_idx >= 0:
                            short_name = proc_name.split("/")[-1][:40]
                            procs_by_gpu.setdefault(gpu_idx, []).append(
                                {
                                    "pid": pid,
                                    "mem_mb": int(mem_mb) if mem_mb.isdigit() else 0,
                                    "name": short_name,
                                }
                            )

            # Parse GPU lines and build structured output
            gpus = []
            for line in gpu_result.stdout.strip().splitlines():
                if not line.strip():
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) == 5:
                    idx = int(parts[0])
                    name = parts[1]
                    util = parts[2]
                    mem_used = int(parts[3])
                    mem_total = int(parts[4])
                    gpus.append(
                        {
                            "index": idx,
                            "name": name,
                            "util_pct": int(util),
                            "mem_used_mb": mem_used,
                            "mem_total_mb": mem_total,
                            "processes": procs_by_gpu.get(idx, []),
                        }
                    )

            return gpus, None

        except Exception as e:
            return None, str(e)

    def _format_nvidia(self, gpus):
        """Format GPU stats as clean text for display"""
        lines = []
        for gpu in gpus:
            bar_filled = int(gpu["util_pct"] / 5)  # 20-char bar
            bar = "█" * bar_filled + "░" * (20 - bar_filled)
            lines.append(f"GPU {gpu['index']}: {gpu['name']}")
            lines.append(f"  Util: [{bar}] {gpu['util_pct']:3d}%")
            lines.append(
                f"  VRAM: {gpu['mem_used_mb']:5d} / {gpu['mem_total_mb']} MiB  "
                f"({gpu['mem_used_mb'] * 100 // gpu['mem_total_mb']:3d}%)"
            )
            procs = gpu.get("processes", [])
            if procs:
                lines.append("  Processes:")
                for p in procs:
                    lines.append(
                        f"    PID {p['pid']:>7}  {p['mem_mb']:5d} MiB  {p['name']}"
                    )
            else:
                lines.append("  Processes: (none)")
            lines.append("")
        return "\n".join(lines).rstrip()

    def _nvidia_smi_loop(self):
        """Run nvidia-smi every 10 seconds"""
        while self.running:
            gpus, error = self._get_nvidia_stats()
            if gpus is not None:
                formatted = self._format_nvidia(gpus)
                self.last_nvidia = formatted
                self.last_gpus = gpus
                self._notify("nvidia_smi", {"text": formatted, "gpus": gpus})
            else:
                self.last_gpus = []
                self._notify("nvidia_smi", {"text": "", "gpus": []}, error)

            time.sleep(self.nvidia_smi_interval)

    def _ollama_ps_loop(self):
        """Poll Ollama /api/ps endpoint every 15 seconds"""
        while self.running:
            ollama_url = self.get_ollama_url()
            if not ollama_url:
                # No Ollama provider available, skip this cycle
                time.sleep(self.ollama_ps_interval)
                continue

            try:
                resp = requests.get(f"{ollama_url}/api/ps", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("models", [])
                    if models:
                        lines = [
                            "NAME                          SIZE     VRAM      UNTIL"
                        ]
                        for m in models:
                            name = m.get("name", "?")[:30]
                            size = _fmt_bytes(m.get("size", 0))
                            vram = _fmt_bytes(m.get("size_vram", 0))
                            expires = m.get("expires_at", "")[:19].replace("T", " ")
                            lines.append(f"{name:<30}  {size:>7}  {vram:>7}  {expires}")
                        text = "\n".join(lines)
                    else:
                        text = "(no models loaded)"
                    self.last_ollama = text
                    self._notify("ollama_ps", {"text": text, "models": models})
                else:
                    self._notify("ollama_ps", {"text": ""}, f"HTTP {resp.status_code}")
            except requests.ConnectionError:
                self._notify("ollama_ps", {"text": ""}, "Cannot connect to Ollama")
            except Exception as e:
                self._notify("ollama_ps", {"text": ""}, str(e))

            time.sleep(self.ollama_ps_interval)

    def start(self):
        """Start monitoring threads"""
        if self.running:
            return

        self.running = True
        threading.Thread(target=self._nvidia_smi_loop, daemon=True).start()
        threading.Thread(target=self._ollama_ps_loop, daemon=True).start()
        logger.info("System monitor started")

    def stop(self):
        """Stop monitoring"""
        self.running = False

    def get_latest(self) -> dict:
        """Get latest monitoring data"""
        return {
            "nvidia_smi": self.last_nvidia,
            "nvidia_gpus": self.last_gpus,
            "ollama_ps": self.last_ollama,
            "timestamp": time.time(),
        }


def _fmt_bytes(n):
    """Format bytes to human-readable string"""
    if n == 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# Global instance
monitor = SystemMonitor()
