"""
Flask application factory for Video Analyzer Web
"""
import os
from pathlib import Path

from flask import Flask
from flask_socketio import SocketIO

socketio = SocketIO(
    cors_allowed_origins="*",
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=1024 * 1024 * 100,
)


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.urandom(24)

    socketio.init_app(app)

    from src.api.videos import videos_bp
    from src.api.providers import providers_bp
    from src.api.jobs import jobs_bp
    from src.api.llm import llm_bp
    from src.api.results import results_bp
    from src.api.system import system_bp
    from src.api.transcode import transcode_bp

    app.register_blueprint(videos_bp)
    app.register_blueprint(providers_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(llm_bp)
    app.register_blueprint(results_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(transcode_bp)

    from src.websocket.handlers import register_socket_handlers
    register_socket_handlers(socketio)

    from src.core.initialization import initialize_app
    initialize_app(app, socketio)

    return app
