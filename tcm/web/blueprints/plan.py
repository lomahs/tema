"""The test plan: what is meant to happen, and how it compared.

`jsonify` wrappers around `tcm.services.planning`, the same arrangement as the
analytics and prepare blueprints. The reasoning — the baseline rule, the join
against actuals, the subtraction behind a suggestion — is the service's; what
stays here is the request: which date, which person, and turning the domain's
`ValueError` into the 400 that carries its message.

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


@bp.route("/api/plan/suggest")
def get_suggestions():
    """GET /api/plan/suggest?date=&device_family= — where a freed-up tester could go.

    `date` is required rather than defaulted to today: the answer subtracts what
    that day's plan already handed out, so a missing date would quietly report
    the work as entirely free.
    """
    date = request.args.get("date")
    if not date:
        return jsonify({"error": "A 'date' is required: the free figure is what "
                                 "that day's plan has not already given out"}), 400
    try:
        rows = planning().suggest(_cases(), date,
                                  device_family=request.args.get("device_family"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"date": date, "rows": rows})


@bp.route("/api/plan/person/<pic>")
def get_person(pic):
    """GET /api/plan/person/<pic> — one person across every day they appear on."""
    return jsonify(planning().person_view(pic, _cases()))


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


@bp.route("/api/plan/<date>/baseline", methods=["POST"])
def post_baseline(date):
    """POST /api/plan/<date>/baseline — judge the day against the plan as it stands.

    The baseline is otherwise frozen on the first edit made on or after the day
    itself. This is the way back from a first edit that was a typo.
    """
    try:
        planning().rebaseline(date)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(planning().day_view(date, _cases()))
