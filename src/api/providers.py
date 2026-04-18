"""
Provider API routes
"""
import requests
from flask import Blueprint, request, jsonify
from providers.ollama import OllamaProvider
from providers.openrouter import OpenRouterProvider
from discovery import discovery

providers_bp = Blueprint("providers", __name__)


def get_providers():
    from app import providers
    return providers


@providers_bp.route("/api/providers")
def list_providers():
    """List configured providers"""
    result = [p.to_dict() for p in get_providers().values()]
    return jsonify(result)


@providers_bp.route("/api/providers/discover")
def discover_ollama():
    """Trigger Ollama discovery scan"""
    found = discovery.scan()
    for url in found:
        name = f"Ollama-{url.split('//')[1].replace(':', '-')}"
        if name not in get_providers():
            get_providers()[name] = OllamaProvider(name, url)
    return jsonify({"discovered": len(found), "urls": found})


@providers_bp.route("/api/providers/ollama/models")
def get_ollama_models():
    """Get models from Ollama server"""
    url = request.args.get("server")
    if not url:
        return jsonify({"error": "No server URL"}), 400
    provider = OllamaProvider("temp", url)
    models = provider.get_models()
    return jsonify({"server": url, "models": models, "status": provider.status})


@providers_bp.route("/api/providers/openrouter/models")
def get_openrouter_models():
    """Get models from OpenRouter"""
    api_key = request.args.get("api_key")
    if not api_key:
        return jsonify({"error": "No API key"}), 400
    provider = OpenRouterProvider("OpenRouter", api_key)
    get_providers()["OpenRouter"] = provider
    models = provider.get_models()
    return jsonify({"models": models, "status": provider.status})


@providers_bp.route("/api/providers/openrouter/cost")
def estimate_openrouter_cost():
    """Estimate cost for analysis"""
    api_key = request.args.get("api_key")
    model_id = request.args.get("model")
    frame_count = int(request.args.get("frames", 50))
    if not api_key or not model_id:
        return jsonify({"error": "Missing parameters"}), 400
    provider = get_providers().get("OpenRouter") or OpenRouterProvider("OpenRouter", api_key)
    cost = provider.estimate_cost(model_id, frame_count)
    return jsonify(cost)


@providers_bp.route("/api/providers/openrouter/balance")
def get_openrouter_balance():
    """Get OpenRouter API key balance"""
    api_key = request.args.get("api_key")
    if not api_key:
        return jsonify({"error": "No API key"}), 400
    try:
        response = requests.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            return jsonify({
                "balance": data.get("data", {}).get("balance", 0),
                "usage": data.get("data", {}).get("usage", 0),
                "limit": data.get("data", {}).get("limit", None),
            })
        elif response.status_code == 401:
            return jsonify({"error": "Invalid API key"}), 401
        else:
            return jsonify({"error": f"Failed to fetch balance: {response.status_code}"}), response.status_code
    except requests.RequestException as e:
        return jsonify({"error": f"Network error: {str(e)}"}), 503
    except Exception as e:
        return jsonify({"error": "Internal server error"}), 500
