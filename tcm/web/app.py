"""The Flask application factory."""
import logging
import os

from flask import Flask

from tcm import settings
from tcm.infrastructure.db.bootstrap import open_database
from tcm.infrastructure.db.phases import SqlPhaseRepository
from tcm.infrastructure.db.plans import SqlPlanRepository
from tcm.infrastructure.db.snapshots import SqlSnapshotRepository
from tcm.infrastructure.excel.loader import ExcelCaseLoader
from tcm.infrastructure.graph.auth import GraphAuth
from tcm.infrastructure.store.memory import InMemoryCaseStore
from tcm.services.identity import IdentityService
from tcm.services.members import MemberService
from tcm.services.phases import PhaseService
from tcm.services.planning import PlanningService
from tcm.services.workspace import Workspace
from tcm.web.blueprints import analytics, pages, plan, prepare, sharepoint, snapshots, source
from tcm.web.blueprints import member as member_bp
from tcm.web.blueprints import phases as phases_bp
from tcm.web.blueprints import settings as settings_bp

#: templates/ and static/ stayed at the repository root: they are the app's
#: front end, not the package's data, and the run command documented in
#: README.md is still `.venv/bin/python app.py` from there.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_app(workspace=None, identity=None, planning=None, phases=None, database=None):
    """Build the app.

    Args:
        workspace: A `Workspace`, or None to build the shipped one over the
            Excel reader, an in-memory store and the database's snapshots --
            and to start it on the newest snapshot.
        identity: An `IdentityService`, or None to build one over Graph.
        planning: A `PlanningService`, or None to build one over the database.
        phases: A `PhaseService`, or None to build one over the database.
        database: An open `Database`, or None to open `settings.DATABASE_FILE`
            when any of the three above needs it.

    All are arguments so a test can build an app over fakes without patching a
    module; nothing in the app changes them after construction.
    """
    app = Flask(
        __name__,
        template_folder=os.path.join(_ROOT, "templates"),
        static_folder=os.path.join(_ROOT, "static"),
    )

    if database is None and (workspace is None or planning is None or phases is None):
        # Opened here and nowhere else. A database that cannot be opened or
        # migrated stops the app, like a malformed shipped config: running on
        # without the plan would invite a save over it.
        database = open_database(settings.DATABASE_FILE)

    if workspace is None:
        workspace = Workspace(ExcelCaseLoader(), InMemoryCaseStore(),
                              SqlSnapshotRepository(database))
        workspace.restore_latest()
    app.extensions["workspace"] = workspace
    app.extensions["identity"] = identity or IdentityService(GraphAuth(
        client_id=settings.GRAPH_CLIENT_ID,
        tenant_id=settings.GRAPH_TENANT_ID,
        scopes=settings.GRAPH_SCOPES,
        cache_path=settings.GRAPH_TOKEN_CACHE,
    ))
    app.extensions["planning"] = planning or PlanningService(SqlPlanRepository(database))
    app.extensions["phases"] = phases or PhaseService(SqlPhaseRepository(database))
    # Built over the planning service rather than handed in: it adds no I/O of
    # its own, so a test that fakes the plan has already faked everything here.
    app.extensions["member"] = MemberService(app.extensions["planning"])

    for module in (source, snapshots, analytics, plan, member_bp, phases_bp, prepare,
                   settings_bp, sharepoint, pages):
        app.register_blueprint(module.bp)

    return app


def configure_logging():
    logging.basicConfig(
        level=logging.DEBUG if settings.DEBUG else logging.INFO,
        format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
