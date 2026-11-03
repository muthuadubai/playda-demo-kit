import logging
import sys

from flask import Flask
from flask_cors import CORS

from app.routes import demo_bp


def create_app():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    from demo_kit import config

    app = Flask(__name__)
    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": config.ALLOWED_ORIGINS,
                "allow_headers": ["Authorization", "Content-Type", "X-Job-Token"],
            }
        },
    )
    app.register_blueprint(demo_bp)

    @app.route("/health")
    def health():
        return {"ok": True}

    return app
