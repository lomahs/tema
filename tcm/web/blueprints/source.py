from flask import Blueprint, jsonify, request

from tcm.infrastructure.dialog import DialogError, pick_files, pick_folder
from tcm.services import preparation as runner
from tcm.web.blueprints import workspace

bp = Blueprint("source", __name__)


@bp.route("/api/load", methods=["POST"])
def load_data():
    """POST /api/load — read test cases from a folder or an explicit file list.

    Body: `{"folder": "..."}` or `{"files": ["...", ...]}`.
    """
    body = request.get_json(silent=True) or {}
    if "folder" in body:
        result, status = workspace().load_folder(body["folder"])
    elif "files" in body and isinstance(body["files"], list):
        result, status = workspace().load_files(body["files"])
    else:
        return jsonify({"error": "Provide 'folder' or 'files' in request body"}), 400
    return jsonify(result), status


@bp.route("/api/reload", methods=["POST"])
def reload_data():
    """POST /api/reload — re-read whatever source `/api/load` last accepted.

    Errors with 400 if nothing has been loaded yet.
    """
    result, status = workspace().reload()
    return jsonify(result), status


@bp.route("/api/browse", methods=["POST"])
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


@bp.route("/api/prepare/files")
def prepare_files():
    """GET /api/prepare/files - the loaded source's workbooks and their state."""
    if not workspace().source:
        return jsonify({"error": "No data loaded yet. Use /api/load first."}), 400

    return jsonify({"files": runner.describe(workspace().source_workbooks())})
