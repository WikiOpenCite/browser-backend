from flask import Flask
from browser.db.pool import create_pool
from browser.db import build_from_config
from browser.config import manager as config_manager

from ._citations import citations  # type: ignore


def create_app() -> Flask:
    """Get the Flask app instance."""

    db = config_manager.config.database
    create_pool(build_from_config(config_manager.config.database))  # type: ignore

    app = Flask(__name__)
    app.register_blueprint(citations)

    return app
