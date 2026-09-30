"""Snapshots: keeping a load, opening it again, and comparing two.

`jsonify` wrappers around `Workspace`. `/api/workspace` lives here because it
exists for the snapshot a restart restores: the page asks it what is already
loaded before deciding whether to open on Tools.
"""
from flask import Blueprint, jsonify, request

from tcm.domain.scope import SCOPES
from tcm.domain.status import STATUS
from tcm.web.blueprints import workspace

bp = Blueprint("snapshots", __name__)


@bp.route("/api/workspace")
def get_workspace():
    """GET /api/workspace — what is loaded now, and whether it came from a snapshot."""
    return jsonify(workspace().state())


@bp.route("/api/snapshots")
def list_snapshots():
    """GET /api/snapshots — every snapshot, newest first, and the one on screen."""
    return jsonify({"snapshots": workspace().snapshots(), "origin": workspace().origin})


@bp.route("/api/snapshots", methods=["POST"])
def save_snapshot():
    """POST /api/snapshots — `{"label": "..."}`; keep what is loaded now."""
    label = (request.get_json(silent=True) or {}).get("label", "")
    if not isinstance(label, str):
        return jsonify({"error": "'label' must be text"}), 400
    result, status = workspace().save_snapshot(label)
    return jsonify(result), status


@bp.route("/api/snapshots/compare")
def compare_snapshots():
    """GET /api/snapshots/compare?base=<id>&head=<id> — what changed from base to head."""
    base = request.args.get("base", type=int)
    head = request.args.get("head", type=int)
    if base is None or head is None:
        return jsonify({"error": "Provide 'base' and 'head' snapshot ids"}), 400
    result, status = workspace().compare(base, head)
    return jsonify(result), status


def _compare_side(prefix):
    """One side of a move from the query: `(scope group, status)`, None, or an error.

    A side is named by both halves or neither -- neither is how an added or a
    removed row is asked for. Keys are checked against the taxonomy and the
    scope groups as they stand, because a move named with a key that no longer
    exists would list nothing and read as "nothing moved".
    """
    scope = request.args.get(f"{prefix}_scope")
    status = request.args.get(f"{prefix}_status")
    if scope is None and status is None:
        return None, None
    if scope is None or status is None:
        return None, f"Give both '{prefix}_scope' and '{prefix}_status', or neither"
    if scope not in SCOPES.keys:
        return None, f"Unknown scope group {scope!r}; expected one of {', '.join(SCOPES.keys)}"
    if status not in STATUS.keys:
        return None, f"Unknown status {status!r}; expected one of {', '.join(STATUS.keys)}"
    return (scope, status), None


@bp.route("/api/snapshots/compare/cases")
def compare_snapshot_cases():
    """GET /api/snapshots/compare/cases?base&head&from_scope&from_status&to_scope&to_status

    The cases behind one move of `/api/snapshots/compare`. Leave out the `from_*`
    pair for rows added, the `to_*` pair for rows removed.
    """
    base = request.args.get("base", type=int)
    head = request.args.get("head", type=int)
    if base is None or head is None:
        return jsonify({"error": "Provide 'base' and 'head' snapshot ids"}), 400
    was, error = _compare_side("from")
    now, error = (None, error) if error else _compare_side("to")
    if error:
        return jsonify({"error": error}), 400
    if was is None and now is None:
        return jsonify({"error": "Name at least one side of the move"}), 400
    result, status = workspace().compared_cases(base, head, was, now)
    return jsonify(result), status


@bp.route("/api/snapshots/<int:snapshot_id>/open", methods=["POST"])
def open_snapshot(snapshot_id):
    """POST /api/snapshots/<id>/open — put a snapshot on screen, as a load would."""
    result, status = workspace().open_snapshot(snapshot_id)
    return jsonify(result), status


@bp.route("/api/snapshots/<int:snapshot_id>", methods=["DELETE"])
def delete_snapshot(snapshot_id):
    """DELETE /api/snapshots/<id>."""
    result, status = workspace().delete_snapshot(snapshot_id)
    return jsonify(result), status
