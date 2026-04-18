"""
LLM Chat API routes
"""
from flask import Blueprint, request, jsonify
from chat_queue import chat_queue_manager

llm_bp = Blueprint("llm", __name__)


@llm_bp.route("/api/llm/chat", methods=["POST"])
def llm_chat():
    """Submit a chat request to the queue and return job_id"""
    data = request.json
    provider_type = data.get("provider_type")
    model_id = data.get("model")
    prompt = data.get("prompt", "")
    content = data.get("content", "")
    api_key = data.get("api_key", "")
    ollama_url = data.get("ollama_url", "http://localhost:11434")

    if not model_id:
        return jsonify({"error": "Model is required"}), 400
    if not prompt and not content:
        return jsonify({"error": "Prompt or content is required"}), 400

    try:
        job_id = chat_queue_manager.submit_job(
            provider_type=provider_type or "ollama",
            model_id=model_id,
            prompt=prompt,
            content=content,
            api_key=api_key,
            ollama_url=ollama_url,
        )
        return jsonify({"job_id": job_id, "message": "Chat job submitted to queue"})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Internal error: {str(e)}"}), 500


@llm_bp.route("/api/llm/chat/<job_id>", methods=["GET"])
def llm_chat_status(job_id: str):
    """Get status of a chat job"""
    status = chat_queue_manager.get_job_status(job_id)
    if not status:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(status)


@llm_bp.route("/api/llm/chat/<job_id>", methods=["DELETE"])
def cancel_llm_chat(job_id: str):
    """Cancel a chat job"""
    success = chat_queue_manager.cancel_job(job_id)
    if not success:
        return jsonify({"error": "Cannot cancel job"}), 400
    return jsonify({"success": True, "message": "Job cancelled"})


@llm_bp.route("/api/llm/queue/stats", methods=["GET"])
def llm_queue_stats():
    """Get chat queue statistics"""
    stats = chat_queue_manager.get_queue_stats()
    return jsonify(stats)
