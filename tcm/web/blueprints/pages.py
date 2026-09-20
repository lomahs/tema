"""The one HTML page.

Everything past this is a single-page app: `index.html` loads the ES modules
under `static/js/`, and every other blueprint in this package answers JSON to
them. This route's only job is to serve the shell they run inside.
"""
from flask import Blueprint, render_template

bp = Blueprint("pages", __name__)


@bp.route("/")
def index():
    return render_template("index.html")
