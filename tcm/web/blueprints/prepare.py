import os

from flask import Blueprint, jsonify, request

from tcm.domain.status import STATUS
from tcm.infrastructure.excel.clearing import DEFAULT_KEEP
from tcm.services import preparation as runner
from tcm.web.blueprints import workspace

bp = Blueprint("prepare", __name__)

# --- Preparing the workbooks -----------------------------------------------
#
# Reading a workbook needs a TOOL_DATA sheet describing its layout, and a new
# test round needs last round's results out of the way. Both are things you do
# to the source files themselves, before or between loads - so unlike every
# other endpoint here, these two write to disk.
#
# The work itself lives in `tcm.services.preparation`; these endpoints are
# `jsonify` wrappers with the two guards that are genuinely about the request:
# which files may be touched, and whether `keep` names real statuses.


def _requested_files(body) -> tuple[list[str], dict | None]:
    """The `files` of a request, checked against what the loaded source names.

    Returns `(paths, error)`, where `error` is a `(body, status)` tuple ready to
    return. A path outside the source is refused outright rather than silently
    skipped: the user cannot have chosen it, and these operations overwrite
    files.
    """
    if not workspace().source:
        return [], ({"error": "No data loaded yet. Use /api/load first."}, 400)

    raw = body.get("files")
    if not isinstance(raw, list) or not raw:
        return [], ({"error": "Provide 'files' as a non-empty list of paths"}, 400)

    allowed = {os.path.abspath(p) for p in workspace().source_workbooks()}
    paths = [os.path.abspath(p) for p in raw]
    unknown = [p for p in paths if p not in allowed]
    if unknown:
        return [], ({"error": f"Not part of the loaded source: {unknown}"}, 400)

    return paths, None


@bp.route("/api/prepare/tool-data", methods=["POST"])
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


@bp.route("/api/prepare/clear", methods=["POST"])
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
