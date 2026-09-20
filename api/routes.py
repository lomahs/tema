import logging
import os
import threading

from flask import Blueprint, jsonify, request

import aggregate
import tcm.settings as config
import config_store
from api.filedialog import DialogError, pick_files, pick_folder
from parser.excel_reader import load_from_folder, load_from_files
from tcm.domain.device import DEVICES
from tcm.domain.scope import SCOPES
from tcm.domain.status import STATUS
from prepare import runner
from prepare.clear import DEFAULT_KEEP
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


# --- the editable configs --------------------------------------------------
#
# `jsonify` wrappers around `config_store`, the same arrangement as the
# aggregate and prepare endpoints. The rules — what validates, what is written,
# what takes effect — are the store's; what stays here is the request.


@api.route("/api/config")
def get_config():
    """GET /api/config - every editable config file, and the vocabularies.

    The vocabularies (tones, derive conditions, the sheet-label field names)
    come down with the data so the editor never writes its own copy of a list
    the validator would then refuse.
    """
    return jsonify(config_store.read_all())


@api.route("/api/config/<name>", methods=["PUT"])
def put_config(name):
    """PUT /api/config/<name> - validate `{"data": {...}}`, save it, apply it.

    A refused edit changes nothing: the store validates before it writes, so a
    400 here means the file on disk and the running app are both as they were.
    The message is the config class's own, because it names the invariant that
    was broken rather than saying the edit was bad.
    """
    if name not in config_store.CONFIGS:
        return jsonify({
            "error": f"Unknown config '{name}'; "
                     f"expected one of {', '.join(sorted(config_store.CONFIGS))}"
        }), 404

    body = request.get_json(silent=True) or {}
    data = body.get("data")
    if not isinstance(data, dict):
        return jsonify({"error": "Provide 'data' as the config object to save"}), 400

    try:
        saved = config_store.save(name, data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except OSError as e:
        return jsonify({"error": f"Could not write the config file: {e}"}), 500

    return jsonify(saved), 200


@api.route("/api/cases")
def get_cases():
    """GET /api/cases?status=<key> — the loaded cases classified as one status.

    The slice behind a status figure: click the 3 in NG's column and this is
    what Detail fetches. One status per request, cached in the browser, so the
    cost of opening a case list is the status you asked for rather than every
    case of every workbook — which is what the endpoint this replaced charged on
    every load, before anyone had looked at anything.

    `status` is derived here rather than stored on the case, so editing the
    result taxonomy takes effect without re-reading the workbooks.

    Its coverage is Summary's, not Review's: a scope group marked `excluded` is
    reported but not committed to, and Detail draws a card for it that the
    reader may deliberately press, so its cases arrive with the group named on
    them and the view decides — see `aggregate.status_cases`. Everything that
    adds groups together still filters through `in_plan`.

    The parameter is required, and one the taxonomy does not name is a 400
    rather than an empty list: a browser asking for a status a config save has
    since removed is out of date, and "no cases" would read as "none today".
    """
    key = request.args.get("status", "").strip()
    if not key:
        return jsonify({
            "error": "Provide 'status' as the status key to fetch cases for; "
                     f"expected one of {', '.join(STATUS.keys)}"
        }), 400
    if key not in STATUS.keys:
        return jsonify({
            "error": f"Unknown status key '{key}'; "
                     f"expected one of {', '.join(STATUS.keys)}"
        }), 400

    return jsonify(aggregate.status_cases(_data["cases"], key))


@api.route("/api/summary")
def get_summary():
    groups, missing_reason = aggregate.summary_rows(_data["cases"], by_scope=True)
    # The rows stay whole — Summary draws a table per group, including one that
    # is out of the plan — but the "Missing reason" figure is a link into
    # Review, and Review holds only cases in the plan. A count of rows the
    # destination cannot show would send the reader to an empty table.
    missing_reason = [r for r in missing_reason if SCOPES.is_counted(r["scope"])]
    # The group definitions ride along so the view can title its tables and order
    # them, including the ones that happen to be empty for this dataset.
    # The device families ride along for the same reason: the "By device type"
    # rows are labelled from them, so the view names no device of its own.
    return jsonify({"groups": groups, "missing_reason": missing_reason,
                    "scopes": SCOPES.to_dict()["groups"],
                    "device_families": DEVICES.to_dict()["families"]})


@api.route("/api/file")
def get_file():
    """GET /api/file?name=<basename> — one workbook, sheet by sheet.

    The drill-in behind a file name, and the one read endpoint that is *not*
    about everything loaded. It reports every scope group, including one the
    plan excludes, because the page draws a Scope column and a Scope filter —
    see `aggregate.file_rows`. That makes its coverage Summary's rather than
    Review's, so the figures here can legitimately exceed Review's.

    The name is a query parameter rather than a path segment because workbook
    names carry spaces and Japanese, and `?name=` keeps the escaping the
    browser's business rather than the router's.

    A name nothing loaded answers to is a 404: the reader followed a link to a
    file this source does not have, and an empty table would read as a workbook
    with no cases in it.
    """
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"error": "No file name given."}), 400

    data = aggregate.file_rows(_data["cases"], name)
    if not data["cases"]:
        return jsonify({"error": f"No loaded file is called {name}."}), 404
    return jsonify(data)


@api.route("/api/daily")
def get_daily():
    """Stats grouped by file, device, PIC, and test_date."""
    return jsonify(aggregate.daily_rows(_data["cases"]))


@api.route("/api/productivity")
def get_productivity():
    """Cases executed per working day, per PIC."""
    return jsonify(aggregate.productivity_rows(_data["cases"]))


# --- Preparing the workbooks -----------------------------------------------
#
# Reading a workbook needs a TOOL_DATA sheet describing its layout, and a new
# test round needs last round's results out of the way. Both are things you do
# to the source files themselves, before or between loads - so unlike every
# other endpoint here, these two write to disk.
#
# The work itself lives in `prepare.runner`, which the CLIs call too; these are
# `jsonify` wrappers with the two guards that are genuinely about the request:
# which files may be touched, and whether `keep` names real statuses.


def _requested_files(body) -> tuple[list[str], dict | None]:
    """The `files` of a request, checked against what the loaded source names.

    Returns `(paths, error)`, where `error` is a `(body, status)` tuple ready to
    return. A path outside the source is refused outright rather than silently
    skipped: the user cannot have chosen it, and these operations overwrite
    files.
    """
    if not _data["source"]:
        return [], ({"error": "No data loaded yet. Use /api/load first."}, 400)

    raw = body.get("files")
    if not isinstance(raw, list) or not raw:
        return [], ({"error": "Provide 'files' as a non-empty list of paths"}, 400)

    allowed = {os.path.abspath(p) for p in runner.source_workbooks(_data["source"])}
    paths = [os.path.abspath(p) for p in raw]
    unknown = [p for p in paths if p not in allowed]
    if unknown:
        return [], ({"error": f"Not part of the loaded source: {unknown}"}, 400)

    return paths, None


@api.route("/api/prepare/files")
def prepare_files():
    """GET /api/prepare/files - the loaded source's workbooks and their state."""
    if not _data["source"]:
        return jsonify({"error": "No data loaded yet. Use /api/load first."}), 400

    return jsonify({"files": runner.describe(runner.source_workbooks(_data["source"]))})


@api.route("/api/prepare/tool-data", methods=["POST"])
def prepare_tool_data():
    """POST /api/prepare/tool-data - detect each workbook's layout.

    Body: `{"files": [...], "apply": false}`. Without `apply` this only reports
    what it found, including a diff against any TOOL_DATA sheet already there;
    with it, the detected rows are written in.
    """
    body = request.get_json(silent=True) or {}
    paths, error = _requested_files(body)
    if error:
        return jsonify(error[0]), error[1]

    return jsonify({"results": runner.detect(paths, apply=bool(body.get("apply")))})


@api.route("/api/prepare/clear", methods=["POST"])
def prepare_clear():
    """POST /api/prepare/clear - empty each workbook's result cells.

    Body: `{"files": [...], "keep": ["Cancel"], "apply": false}`. Without
    `apply` this answers the plan only; with it, the planned cells are blanked.

    `keep` is validated for the whole request before any file is opened: a typo
    that silently cleared the rows it was meant to protect is not recoverable.
    """
    body = request.get_json(silent=True) or {}
    paths, error = _requested_files(body)
    if error:
        return jsonify(error[0]), error[1]

    keep = body.get("keep")
    if keep is None:
        keep = list(DEFAULT_KEEP)
    if not isinstance(keep, list):
        return jsonify({"error": "Provide 'keep' as a list of status keys"}), 400

    unknown = [k for k in keep if k not in STATUS.keys]
    if unknown:
        return jsonify({
            "error": f"Unknown status key(s) {', '.join(unknown)}; "
                     f"expected one of {', '.join(STATUS.keys)}"
        }), 400

    return jsonify({"results": runner.clear(
        paths, set(keep), apply=bool(body.get("apply")))})


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
