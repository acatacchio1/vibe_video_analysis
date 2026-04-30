"""
Provider API routes
"""
import requests
import os
from flask import Blueprint, request, jsonify
from providers.litellm import LiteLLMProvider
from providers.openrouter import OpenRouterProvider

providers_bp = Blueprint("providers", __name__)


def get_providers():
    from app import providers
    return providers


def get_openrouter_api_key():
    """Get OpenRouter API key from environment or initialized provider"""
    env_key = os.environ.get("OPENROUTER_API_KEY")
    if env_key:
        return env_key

    provider = get_providers().get("OpenRouter")
    if provider and hasattr(provider, "api_key"):
        return provider.api_key

    return None


@providers_bp.route("/api/providers")
def list_providers():
    """List configured providers"""
    result = [p.to_dict() for p in get_providers().values()]
    return jsonify(result)


@providers_bp.route("/api/providers/litellm/models")
def get_litellm_models():
    """Get models from LiteLLM server"""
    api_url = request.args.get("server", "http://172.16.17.3:4000/v1")
    provider = LiteLLMProvider("temp", api_url)
    models = provider.get_models()
    return jsonify({"server": api_url, "models": models, "status": provider.status})


@providers_bp.route("/api/providers/openrouter/models")
def get_openrouter_models():
    """Get models from OpenRouter"""
    import logging
    logger = logging.getLogger(__name__)
    
    api_key = get_openrouter_api_key()
    if not api_key:
        logger.error("OpenRouter API key not configured")
        return jsonify({"error": "OpenRouter API key not configured"}), 400

    provider = get_providers().get("OpenRouter")
    current_status = provider.status if provider else "none"
    logger.info(f"OpenRouter provider found: {provider is not None}, status: {current_status}")
    
    needs_recreate = (not provider) or (provider.status in ("offline", "error") and not provider.pricing_cache)
    if needs_recreate:
        logger.info(f"Recreating OpenRouter provider (previous status: {current_status})")
        try:
            provider = OpenRouterProvider("OpenRouter", api_key)
            get_providers()["OpenRouter"] = provider
            logger.info(f"New OpenRouter status: {provider.status}, models: {len(provider.pricing_cache)}")
        except Exception as e:
            logger.error(f"Failed to create OpenRouter provider: {e}")
            return jsonify({"error": f"Failed to initialize OpenRouter: {str(e)}"}), 500

    models = provider.get_models()
    return jsonify({"models": models, "status": provider.status})


@providers_bp.route("/api/providers/openrouter/cost")
def estimate_openrouter_cost():
    """Estimate cost for analysis"""
    model_id = request.args.get("model")
    frame_count = int(request.args.get("frames", 50))
    if not model_id:
        return jsonify({"error": "Missing model parameter"}), 400

    api_key = get_openrouter_api_key()
    if not api_key:
        return jsonify({"error": "OpenRouter API key not configured"}), 400

    provider = get_providers().get("OpenRouter")
    if not provider:
        provider = OpenRouterProvider("OpenRouter", api_key)
        get_providers()["OpenRouter"] = provider

    cost = provider.estimate_cost(model_id, frame_count)
    return jsonify(cost)


@providers_bp.route("/api/providers/openrouter/balance")
def get_openrouter_balance():
    """Get OpenRouter API key balance"""
    api_key = get_openrouter_api_key()
    if not api_key:
        return jsonify({"error": "OpenRouter API key not configured"}), 400

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
