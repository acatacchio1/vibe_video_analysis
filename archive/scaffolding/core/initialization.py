"""
Application initialization for Video Analyzer Web
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def initialize_app(app, socketio):
    """Initialize providers, monitors, and callbacks"""
    from providers.ollama import OllamaProvider
    from discovery import discovery
    from vram_manager import vram_manager
    from monitor import monitor

    # Initialize providers
    ollama_local = OllamaProvider("Ollama-Local", "http://host.docker.internal:11434")
    from app import providers
    providers["Ollama-Local"] = ollama_local

    # Load existing instances without scanning
    config_path = Path(__file__).parent.parent.parent / "config" / "default_config.json"
    known_instances = []
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
            known_instances = config.get("ollama_instances", [])
        except Exception as e:
            logger.warning(f"Could not load config: {e}")

    for url in known_instances:
        if "localhost" not in url and "127.0.0.1" not in url:
            name = f"Ollama-{url.split('//')[1].split(':')[0]}"
            providers[name] = OllamaProvider(name, url)
            discovery.add_host(url)

    # Wire up ollama ps check for VRAM manager
    def get_loaded_ollama_models():
        loaded = set()
        for p in providers.values():
            if hasattr(p, "get_running_models"):
                try:
                    for m in p.get_running_models():
                        loaded.add(m.get("name", ""))
                except Exception:
                    pass
        return loaded

    vram_manager.set_ollama_running_models_provider(get_loaded_ollama_models)

    # Set up Ollama URL provider for monitor
    monitor.set_ollama_url_provider(
        lambda: next((p.base_url for p in providers.values() if hasattr(p, "base_url")), None)
    )

    # Start system monitor
    monitor.start()

    # Register VRAM manager callback
    def on_vram_event(event, job):
        if event == "started":
            job_dir = Path("jobs") / job.job_id
            from app import spawn_worker
            spawn_worker(job.job_id, job_dir, job.gpu_assigned)
        socketio.emit("vram_event", {"event": event, "job": job.to_dict()})

    vram_manager.register_callback(on_vram_event)

    # Register monitor callback
    def on_monitor_update(data):
        socketio.emit("system_status", data)

    monitor.register_callback(on_monitor_update)
