"""Read-only aggregates over the loaded cases.

Each route is a thin `jsonify` wrapper around a function in
`tcm.services.aggregation` — the same functions the SharePoint publisher calls,
so the numbers on screen and the numbers in a published report cannot drift.
`/api/cases` is the one exception worth flagging: it serves the cases behind a
single status per request rather than the whole loaded set, which is what
keeps opening Detail affordable.
"""
from flask import Blueprint, jsonify, request

from tcm.domain.device import DEVICES
from tcm.domain.scope import SCOPES
from tcm.domain.status import STATUS
from tcm.services import aggregation as aggregate
from tcm.web.blueprints import workspace

bp = Blueprint("analytics", __name__)


@bp.route("/api/statuses")
def get_statuses():
    """The result taxonomy, so the UI renders the same buckets as the API."""
    return jsonify(STATUS.to_dict())


@bp.route("/api/cases")
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

    return jsonify(aggregate.status_cases(workspace().cases, key))


@bp.route("/api/summary")
def get_summary():
    groups, missing_reason = aggregate.summary_rows(workspace().cases, by_scope=True)
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


@bp.route("/api/file")
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

    data = aggregate.file_rows(workspace().cases, name)
    if not data["cases"]:
        return jsonify({"error": f"No loaded file is called {name}."}), 404
    return jsonify(data)


@bp.route("/api/daily")
def get_daily():
    """Stats grouped by file, device, PIC, and test_date."""
    return jsonify(aggregate.daily_rows(workspace().cases))


@bp.route("/api/productivity")
def get_productivity():
    """Cases executed per working day, per PIC."""
    return jsonify(aggregate.productivity_rows(workspace().cases))
