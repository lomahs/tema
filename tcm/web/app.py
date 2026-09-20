"""The Flask application factory."""
import logging
import os

from flask import Flask

from tcm import settings
from tcm.infrastructure.excel.loader import ExcelCaseLoader
from tcm.infrastructure.graph.auth import GraphAuth
from tcm.infrastructure.store.memory import InMemoryCaseStore
from tcm.services.identity import IdentityService
from tcm.services.workspace import Workspace
from tcm.web.blueprints import analytics, pages, prepare, sharepoint, source
from tcm.web.blueprints import settings as settings_bp

#: templates/ and static/ stayed at the repository root: they are the app's
#: front end, not the package's data, and the run command documented in
#: README.md is still `.venv/bin/python app.py` from there.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_app(workspace=None, identity=None):
    """Build the app.

    Args:
        workspace: A `Workspace`, or None to build the shipped one over the
            Excel reader and an in-memory store.
        identity: An `IdentityService`, or None to build one over Graph.

    Both are arguments so a test can build an app over fakes without patching
    a module; nothing in the app changes them after construction.
    """
    app = Flask(
        __name__,
        template_folder=os.path.join(_ROOT, "templates"),
        static_folder=os.path.join(_ROOT, "static"),
    )

    app.extensions["workspace"] = workspace or Workspace(
        ExcelCaseLoader(), InMemoryCaseStore())
    app.extensions["identity"] = identity or IdentityService(GraphAuth(
        client_id=settings.GRAPH_CLIENT_ID,
        tenant_id=settings.GRAPH_TENANT_ID,
        scopes=settings.GRAPH_SCOPES,
        cache_path=settings.GRAPH_TOKEN_CACHE,
    ))

    for module in (source, analytics, prepare, settings_bp, sharepoint, pages):
        app.register_blueprint(module.bp)

    return app


def configure_logging():
    logging.basicConfig(
        level=logging.DEBUG if settings.DEBUG else logging.INFO,
        format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
