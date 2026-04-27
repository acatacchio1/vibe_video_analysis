"""Config file handling for CLI."""
import json
import os
from pathlib import Path
from typing import Any, Optional


_CONFIG_VAR = "VIDEO_ANALYZER_CONFIG"
_DEFAULT_CONFIG_PATH = Path.home() / ".video-analyzer-cli.json"

REQUIRED_KEYS = ["url", "openrouter_api_key", "openwebui_url", "openwebui_api_key"]


def get_config_path() -> Path:
    return Path(os.environ.get(_CONFIG_VAR, _DEFAULT_CONFIG_PATH))


def load_config() -> dict:
    path = get_config_path()
    config = {}
    if path.exists():
        try:
            config = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    env_url = os.environ.get("VIDEO_ANALYZER_URL")
    if env_url:
        config["url"] = env_url
    env_ork = os.environ.get("OPENROUTER_API_KEY")
    if env_ork:
        config["openrouter_api_key"] = env_ork
    env_owurl = os.environ.get("OPENWEBUI_URL")
    if env_owurl:
        config["openwebui_url"] = env_owurl
    env_owkey = os.environ.get("OPENWEBUI_API_KEY")
    if env_owkey:
        config["openwebui_api_key"] = env_owkey
    return config


def save_config(config: dict):
    path = get_config_path()
    path.write_text(json.dumps(config, indent=2))


def get_value(key: str, fallback: Any = None) -> Any:
    config = load_config()
    return config.get(key, fallback)


def set_value(key: str, value: Any):
    config = load_config()
    config[key] = value
    save_config(config)


def unset_value(key: str):
    config = load_config()
    config.pop(key, None)
    save_config(config)


def resolve_url(cli_url: Optional[str] = None) -> str:
    if cli_url:
        return cli_url
    return get_value("url", "http://127.0.0.1:10000")


def resolve_openrouter_key() -> str:
    return get_value("openrouter_api_key", "")


def resolve_openwebui_url() -> str:
    return get_value("openwebui_url", "")


def resolve_openwebui_key() -> str:
    return get_value("openwebui_api_key", "")


def show_config() -> dict:
    config = load_config()
    display = {}
    for k in REQUIRED_KEYS:
        if k == "url":
            display[k] = config.get(k, "<not set>")
        elif "key" in k:
            display[k] = "***" if config.get(k) else "<not set>"
        else:
            display[k] = config.get(k, "<not set>")
    return display
