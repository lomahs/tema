"""Signing in to Microsoft, and publishing the loaded cases to a report workbook.

`/api/sharepoint/*` covers the device-code login this app can't do silently:
`IdentityService` owns the flow, this blueprint only starts it, reports how
far it has got, and lets the user forget the account. `/api/report/publish`
is the one write in the app that leaves the machine — it hands the loaded
cases and a SharePoint URL to `publish_to_url`, which runs the same
aggregation the read endpoints serve, so a published report cannot disagree
with the screen it was published from.
"""
import logging

from flask import Blueprint, jsonify, request

from tcm.infrastructure.graph.auth import NotConfigured, NotSignedIn
from tcm.infrastructure.graph.client import GraphClient, GraphError
from tcm.services.publishing import SheetMissing, publish_to_url
from tcm.web.blueprints import identity, workspace

log = logging.getLogger(__name__)

bp = Blueprint("sharepoint", __name__)


@bp.route("/api/sharepoint/status")
def sharepoint_status():
    """GET /api/sharepoint/status — who is signed in, or how far a login has got.

    The UI polls this while the user is off typing their device code, so it
    folds the in-progress login into the answer rather than exposing a second
    endpoint for it.
    """
    return jsonify(identity().status())


@bp.route("/api/sharepoint/login", methods=["POST"])
def sharepoint_login():
    """POST /api/sharepoint/login — start a device code sign-in.

    Answers as soon as Microsoft hands back a code, and waits for the user to
    type it on a background thread. Blocking the request for the minutes that
    can take would hold the single-threaded dev server hostage.
    """
    try:
        body, status = identity().begin_login()
    except NotConfigured as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        log.exception("Could not start the device login")
        return jsonify({"error": f"Could not start sign-in: {e}"}), 502

    return jsonify(body), status


@bp.route("/api/sharepoint/logout", methods=["POST"])
def sharepoint_logout():
    """POST /api/sharepoint/logout — forget the cached account."""
    return jsonify(identity().sign_out())


@bp.route("/api/report/publish", methods=["POST"])
def publish_report():
    """POST /api/report/publish — write the current aggregates to a report file.

    Body: `{"url": "<SharePoint link>", "run_date": "YYYY-MM-DD"}`, where
    `run_date` is optional and defaults to today. Rows already carrying that
    date are replaced, so publishing twice in a day is safe.
    """
    body = request.get_json(silent=True) or {}
    url = (body.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Provide the SharePoint 'url' of the report file"}), 400

    if not workspace().cases:
        # Publishing nothing would clear the day's rows and write none back, so
        # a mis-click before loading must not reach the file.
        return jsonify({"error": "No test cases loaded. Load a source first."}), 400

    try:
        identity().token()
    except NotConfigured as e:
        return jsonify({"error": str(e)}), 400
    except NotSignedIn as e:
        return jsonify({"error": str(e)}), 401

    graph = GraphClient(identity().token)
    try:
        result = publish_to_url(workspace().cases, graph, url, run_date=body.get("run_date"))
    except (SheetMissing, ValueError) as e:
        return jsonify({"error": str(e)}), 400
    except GraphError as e:
        log.warning("Publishing to %s failed: %s", url, e)
        return jsonify({"error": str(e)}), 502

    return jsonify(result)
