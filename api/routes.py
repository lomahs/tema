import logging
import os
import threading

from flask import Blueprint, jsonify, request

import aggregate
import config
from api.filedialog import DialogError, pick_files, pick_folder
from parser.excel_reader import load_from_folder, load_from_files
from parser.status import STATUS
from report.publisher import SheetMissing, publish_to_url
from sharepoint.auth import GraphAuth, NotConfigured, NotSignedIn
from sharepoint.client import GraphClient, GraphError

log = logging.getLogger(__name__)

api = Blueprint("api", __name__)

#: The signed-in identity. Module-level for the same reason `_data` is: this is
#: a single-user local tool, and there is one person at the keyboard.
_auth = GraphAuth(
    client_id=config.GRAPH_CLIENT_ID,
    tenant_id=config.GRAPH_TENANT_ID,
    scopes=config.GRAPH_SCOPES,
    cache_path=config.GRAPH_TOKEN_CACHE,
)

#: A device login in progress. The user has been shown a code and is off typing
#: it into microsoft.com/devicelogin; a background thread waits for them.
_login = {}
_login_lock = threading.Lock()


def _reset_login():
    with _login_lock:
        _login.clear()
        _login.update({"state": "idle", "user_code": None,
                       "verification_uri": None, "error": None})


_reset_login()


def _spawn(fn, *args):
    """Run `fn` off the request thread. Replaced in tests to run inline."""
    threading.Thread(target=fn, args=args, daemon=True).start()

# In-memory store
_data = {
    "cases": [],
    "file_results": [],
    "source": None,  # {"type": "folder"|"files", "value": str|list}
}


def _load(source_type: str, value):
    """Load a folder or file list into the in-memory store.

    The store is only updated once the load succeeds, so a failed call leaves
    the previously loaded data — and the `source` that `/api/reload` reuses —
    untouched.

    Args:
        source_type: Either "folder" or "files".
        value: A folder path, or a list of file paths.

    Returns:
        A `(body, http_status)` tuple, ready to hand to `jsonify`.
    """
    if source_type == "folder":
        path = os.path.abspath(value)
        if not os.path.isdir(path):
            return {"error": f"Folder not found: {value}"}, 400
        cases, file_results = load_from_folder(path)
        source = {"type": "folder", "value": path}
    else:
        paths = [os.path.abspath(f) for f in value]
        missing = [f for f in paths if not os.path.isfile(f)]
        if missing:
            return {"error": f"Files not found: {missing}"}, 400
        cases, file_results = load_from_files(paths)
        source = {"type": "files", "value": paths}

    # Only remember the source once the load actually got that far.
    _data["source"] = source
    _data["cases"] = cases
    _data["file_results"] = file_results
    return {
        "loaded": len(cases),
        "file_count": len(file_results),
        "file_results": file_results,
    }, 200


@api.route("/api/load", methods=["POST"])
def load_data():
    """POST /api/load — read test cases from a folder or an explicit file list.

    Body: `{"folder": "..."}` or `{"files": ["...", ...]}`.
    """
    body = request.get_json(silent=True) or {}
    if "folder" in body:
        result, status = _load("folder", body["folder"])
    elif "files" in body and isinstance(body["files"], list):
        result, status = _load("files", body["files"])
    else:
        return jsonify({"error": "Provide 'folder' or 'files' in request body"}), 400
    return jsonify(result), status


@api.route("/api/reload", methods=["POST"])
def reload_data():
    """POST /api/reload — re-read whatever source `/api/load` last accepted.

    Errors with 400 if nothing has been loaded yet.
    """
    src = _data["source"]
    if not src:
        return jsonify({"error": "No data loaded yet. Use /api/load first."}), 400
    result, status = _load(src["type"], src["value"])
    return jsonify(result), status


@api.route("/api/browse", methods=["POST"])
def browse():
    """POST /api/browse — open a native folder / file dialog on the server.

    Body: `{"mode": "folder"|"files", "initial": "..."}`, where `initial` is the
    directory the dialog opens at. Answers `{"paths": [...]}`; cancelling is an
    empty list, not an error.

    This only fills the input in the UI — loading stays the user's next,
    explicit step, so the store and the `/api/reload` source are untouched.
    """
    body = request.get_json(silent=True) or {}
    mode = body.get("mode")
    if mode not in ("folder", "files"):
        return jsonify({"error": "Provide 'mode' as either 'folder' or 'files'"}), 400

    initial = body.get("initial") or None
    picker = pick_folder if mode == "folder" else pick_files
    try:
        return jsonify({"paths": picker(initial)}), 200
    except DialogError as e:
        return jsonify({"error": f"Could not open the file dialog: {e}"}), 500


@api.route("/api/statuses")
def get_statuses():
    """The result taxonomy, so the UI renders the same buckets as the API."""
    return jsonify(STATUS.to_dict())


@api.route("/api/data")
def get_data():
    """GET /api/data — every loaded case, each with its classified `status` key.

    `status` is derived here rather than stored on the case, so editing the
    result taxonomy takes effect without re-reading the workbooks.
    """
    cases = []
    for c in _data["cases"]:
        row = c.to_dict()
        row["status"] = STATUS.classify(c.result)
        cases.append(row)
    return jsonify(cases)


@api.route("/api/summary")
def get_summary():
    groups, missing_reason = aggregate.summary_rows(_data["cases"])
    return jsonify({"groups": groups, "missing_reason": missing_reason})


@api.route("/api/daily")
def get_daily():
    """Stats grouped by file, device, PIC, and test_date."""
    return jsonify(aggregate.daily_rows(_data["cases"]))


@api.route("/api/productivity")
def get_productivity():
    """Cases executed per working day, per PIC."""
    return jsonify(aggregate.productivity_rows(_data["cases"]))


# --- SharePoint ------------------------------------------------------------

@api.route("/api/sharepoint/status")
def sharepoint_status():
    """GET /api/sharepoint/status — who is signed in, or how far a login has got.

    The UI polls this while the user is off typing their device code, so it
    folds the in-progress login into the answer rather than exposing a second
    endpoint for it.
    """
    status = _auth.status()
    with _login_lock:
        pending = _login["state"] == "pending"
        snapshot = dict(_login)

    if status["state"] == "signed_in":
        return jsonify(status)
    if pending:
        return jsonify({**status, "state": "pending",
                        "user_code": snapshot["user_code"],
                        "verification_uri": snapshot["verification_uri"]})
    if snapshot["error"]:
        return jsonify({**status, "error": snapshot["error"]})
    return jsonify(status)


@api.route("/api/sharepoint/login", methods=["POST"])
def sharepoint_login():
    """POST /api/sharepoint/login — start a device code sign-in.

    Answers as soon as Microsoft hands back a code, and waits for the user to
    type it on a background thread. Blocking the request for the minutes that
    can take would hold the single-threaded dev server hostage.
    """
    try:
        flow = _auth.begin_device_login()
    except NotConfigured as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        log.exception("Could not start the device login")
        return jsonify({"error": f"Could not start sign-in: {e}"}), 502

    with _login_lock:
        _login.update({"state": "pending", "error": None,
                       "user_code": flow.get("user_code"),
                       "verification_uri": flow.get("verification_uri")})

    _spawn(_await_login, flow)

    return jsonify({
        "user_code": flow.get("user_code"),
        "verification_uri": flow.get("verification_uri"),
        "expires_in": flow.get("expires_in"),
    })


def _await_login(flow):
    """Wait out the device flow, then leave the outcome where status can see it."""
    try:
        _auth.complete_device_login(flow)
    except Exception as e:
        log.warning("Device login did not complete: %s", e)
        with _login_lock:
            _login.update({"state": "failed", "error": str(e)})
        return
    _reset_login()


@api.route("/api/sharepoint/logout", methods=["POST"])
def sharepoint_logout():
    """POST /api/sharepoint/logout — forget the cached account."""
    _auth.sign_out()
    _reset_login()
    return jsonify(_auth.status())


@api.route("/api/report/publish", methods=["POST"])
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

    if not _data["cases"]:
        # Publishing nothing would clear the day's rows and write none back, so
        # a mis-click before loading must not reach the file.
        return jsonify({"error": "No test cases loaded. Load a source first."}), 400

    try:
        _auth.token()
    except NotConfigured as e:
        return jsonify({"error": str(e)}), 400
    except NotSignedIn as e:
        return jsonify({"error": str(e)}), 401

    graph = GraphClient(_auth.token)
    try:
        result = publish_to_url(_data["cases"], graph, url, run_date=body.get("run_date"))
    except (SheetMissing, ValueError) as e:
        return jsonify({"error": str(e)}), 400
    except GraphError as e:
        log.warning("Publishing to %s failed: %s", url, e)
        return jsonify({"error": str(e)}), 502

    return jsonify(result)
