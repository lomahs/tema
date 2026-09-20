"""The Flask application factory."""
import logging
import os

from flask import Flask, render_template

from tcm.settings import DEBUG, PORT
from tcm.web.routes import api

#: templates/ and static/ stayed at the repository root: they are the app's
#: front end, not the package's data, and the run command documented in
#: README.md is still `.venv/bin/python app.py` from there.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(_ROOT, "templates"),
        static_folder=os.path.join(_ROOT, "static"),
    )
    app.register_blueprint(api)

    @app.route("/")
    def index():
        return render_template("index.html")

    return app


def configure_logging():
    logging.basicConfig(
        level=logging.DEBUG if DEBUG else logging.INFO,
        format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
