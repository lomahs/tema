"""The Flask application factory."""
import logging
import os

from flask import Flask

from tcm import settings
from tcm.infrastructure.excel.loader import ExcelCaseLoader
from tcm.infrastructure.graph.auth import GraphAuth
from tcm.infrastructure.plan.json_store import JsonPlanRepository
from tcm.infrastructure.config_repo import JsonFileConfigRepository
from tcm.infrastructure.store.memory import InMemoryCaseStore
from tcm.services.identity import IdentityService
from tcm.services.planning import PlanningService
from tcm.services.workspace import Workspace
from tcm.web.blueprints import analytics, pages, plan, prepare, sharepoint, source
from tcm.web.blueprints import settings as settings_bp

#: templates/ and static/ stayed at the repository root: they are the app's
#: front end, not the package's data, and the run command documented in
#: README.md is still `.venv/bin/python app.py` from there.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_app(workspace=None, identity=None, planning=None):
    """Build the app.

    Args:
        workspace: A `Workspace`, or None to build the shipped one over the
            Excel reader and an in-memory store.
        identity: An `IdentityService`, or None to build one over Graph.
        planning: A `PlanningService`, or None to build one over the plan file
            named by `settings.PLAN_FILE`.

    All three are arguments so a test can build an app over fakes without
    patching a module; nothing in the app changes them after construction.
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

    # The plan file is not read here: unlike the vocabularies, a plan is
    # operational data, and an empty or absent one is the normal state rather
    # than something worth refusing to start over.
    app.extensions["planning"] = planning or PlanningService(
        JsonPlanRepository(JsonFileConfigRepository(), settings.PLAN_FILE))

    for module in (source, analytics, plan, prepare, settings_bp, sharepoint, pages):
        app.register_blueprint(module.bp)

    return app


def configure_logging():
    logging.basicConfig(
        level=logging.DEBUG if settings.DEBUG else logging.INFO,
        format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
