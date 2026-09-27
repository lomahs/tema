"""Snapshots: keeping a load, opening it again, and comparing two.

`jsonify` wrappers around `Workspace`. `/api/workspace` lives here because it
exists for the snapshot a restart restores: the page asks it what is already
loaded before deciding whether to open on Tools.
"""
from flask import Blueprint, jsonify, request

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
