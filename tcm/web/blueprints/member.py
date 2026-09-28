"""The Member tab: each person's productivity, and each person against the plan.

`jsonify` wrappers around `tcm.services.members`. Four endpoints rather than one
because they are wanted at different times: productivity, the totals and the
week list once per load or plan change, and one week's cells every time the
reader pages. Every figure is the service's, and every response names the day
it counts through, so the four can be seen to agree.
"""
from flask import Blueprint, jsonify

from tcm.web.blueprints import member_report, workspace

bp = Blueprint("member", __name__)


@bp.route("/api/member/productivity")
def get_productivity():
    """Executed cases per working day per PIC, through yesterday, with the plan beside."""
    return jsonify(member_report().productivity(workspace().cases))


@bp.route("/api/member/totals")
def get_totals():
    """Plan, actual, delta and adherence per member and for the team, through yesterday."""
    return jsonify(member_report().totals(workspace().cases))


@bp.route("/api/member/weeks")
def get_weeks():
    """Every Monday-to-Friday week the matrix can page to, and which one holds today."""
    return jsonify(member_report().weeks(workspace().cases))


@bp.route("/api/member/week/<monday>")
def get_week(monday):
    """GET /api/member/week/<YYYY-MM-DD> — one week's cells; the date must be a Monday."""
    try:
        return jsonify(member_report().week(workspace().cases, monday))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
