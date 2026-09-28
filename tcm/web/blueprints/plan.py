"""The test plan: what is meant to happen, and how it compared.

`jsonify` wrappers around `tcm.services.planning`, the same arrangement as the
analytics and prepare blueprints. The reasoning — the baseline rule, the join
against actuals, the phase and board figures — is the service's; what stays
here is the request: which date, which window, and turning the domain's
`ValueError` into the 400 that carries its message.

The named routes (`daily`, `phase`, `settings`, `board/<date>`) are registered before
`/api/plan/<date>` on purpose: registered after it, "phase" would be read as a
date and refused.

Every read takes the loaded cases from the workspace rather than being given
them, because "what actually happened" is only ever about the load in hand. With
nothing loaded the plan still reads and writes, and every actual is simply zero.
"""
from flask import Blueprint, jsonify, request

from tcm.web.blueprints import planning, workspace

bp = Blueprint("planning", __name__)


def _cases():
    return workspace().cases


@bp.route("/api/plan")
def get_calendar():
    """GET /api/plan?from=&to= — one line per day, planned against done.

    Days worked but never planned are included: the screen reports what
    happened, so a Thursday somebody tested without a plan must not be blank.
    """
    try:
        return jsonify(planning().calendar_view(
            request.args.get("from"), request.args.get("to"), _cases()))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/plan/daily")
def get_daily_plan():
    """GET /api/plan/daily?file=&device=&pic=&from=&to= — Daily's plan and attain.

    Filtered on both sides by exactly the values Daily's filters hold, so a
    narrowed Daily is measured against the plan for that same narrowing.
    """
    args = request.args
    try:
        return jsonify(planning().daily_plan(
            _cases(),
            file=args.get("file") or None, device=args.get("device") or None,
            pic=args.get("pic") or None, start=args.get("from"), end=args.get("to")))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/plan/phase")
def get_phase():
    """GET /api/plan/phase?window=3|5|10|all — KPIs, burndown and the phase grid.

    `window` is how many past phase days the forecast pace is read over.
    """
    try:
        return jsonify(planning().phase_view(_cases(), request.args.get("window", "5")))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/plan/settings")
def get_settings():
    """GET /api/plan/settings — the phase and daily target, defaults filled in."""
    return jsonify(planning().get_settings(_cases()))


@bp.route("/api/plan/settings", methods=["PUT"])
def put_settings():
    """PUT /api/plan/settings — `{phase_start, phase_end, daily_target}`.

    A refusal stores nothing, and the message is the domain's own.
    """
    body = request.get_json(silent=True) or {}
    try:
        planning().save_settings(body)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(planning().get_settings(_cases()))


@bp.route("/api/plan/board/<date>")
def get_board(date):
    """GET /api/plan/board/<date> — one day as slots x members, planned against worked."""
    try:
        return jsonify(planning().board_view(_cases(), date))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/plan/<date>")
def get_day(date):
    """GET /api/plan/<date> — one day's rows, each joined to what was run."""
    try:
        return jsonify(planning().day_view(date, _cases()))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/plan/<date>", methods=["PUT"])
def put_day(date):
    """PUT /api/plan/<date> — replace that day's rows with `{"entries": [...]}`.

    A refused edit changes nothing: the service validates the whole day before
    it writes, so a 400 here means the stored plan is as it was. The message is
    the domain's own, because it names the rule that was broken.
    """
    body = request.get_json(silent=True) or {}
    try:
        planning().save_day(date, body.get("entries") or [])
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(planning().day_view(date, _cases()))
