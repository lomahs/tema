"""Phases and the member roster.

Every write answers with the whole overview, so the card that made it redraws
from one response. A broken rule is the domain's ValueError, a 400 carrying its
message; an id nothing answers to is a 404.
"""
from flask import Blueprint, jsonify, request

from tcm.web.blueprints import phase_service, workspace

bp = Blueprint("phases", __name__)


def _overview(status=200):
    return jsonify(phase_service().overview(workspace().cases)), status


def _run(action, status=200):
    try:
        action()
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return _overview(status)


def _body():
    return request.get_json(silent=True) or {}


@bp.route("/api/phases")
def list_phases():
    """GET /api/phases — `{phases, active_id, members, suggestions}`."""
    return _overview()


@bp.route("/api/phases", methods=["POST"])
def create_phase():
    """POST /api/phases — `{name, phase_start?, phase_end?, daily_target?, members?, activate?}`."""
    return _run(lambda: phase_service().create(_body()), 201)


@bp.route("/api/phases/<int:phase_id>", methods=["PUT"])
def update_phase(phase_id):
    """PUT /api/phases/<id> — replace name, dates, target and members."""
    return _run(lambda: phase_service().update(phase_id, _body()))


@bp.route("/api/phases/<int:phase_id>", methods=["DELETE"])
def delete_phase(phase_id):
    """DELETE /api/phases/<id> — its plans go with it; the last phase stays."""
    return _run(lambda: phase_service().delete(phase_id))


@bp.route("/api/phases/<int:phase_id>/activate", methods=["POST"])
def activate_phase(phase_id):
    """POST /api/phases/<id>/activate — every plan figure now reads this phase."""
    return _run(lambda: phase_service().activate(phase_id))


@bp.route("/api/members", methods=["POST"])
def add_member():
    """POST /api/members — `{name, phase_id?}`; `phase_id` also puts them on that phase."""
    body = _body()
    return _run(lambda: phase_service().add_member(body.get("name"), body.get("phase_id")), 201)


@bp.route("/api/members/<int:member_id>", methods=["DELETE"])
def delete_member(member_id):
    """DELETE /api/members/<id> — refused while a plan row names them."""
    return _run(lambda: phase_service().delete_member(member_id))
