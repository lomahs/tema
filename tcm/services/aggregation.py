"""Turning loaded test cases into the four aggregate views.

These are plain functions over `TestCase` lists with no Flask involvement, so
the API layer and the SharePoint report publisher compute the same numbers from
the same code. Every count is bucketed through `STATUS`, which means the result
taxonomy stays the single place where the vocabulary is defined.
"""
from collections import Counter, defaultdict

from tcm.domain.device import DEVICES
from tcm.domain.scope import SCOPES
from tcm.domain.status import STATUS


def _group_counts(cases, key_fn):
    """Bucket cases by `key_fn` and count each bucket by status key.

    Yields (key, group, counts) with every status key present in `counts`, so no
    row is ever missing a column. Cases are classified with `classify_case`, not
    `classify`, because some statuses are only recognisable from the whole row.
    """
    buckets = defaultdict(list)
    for c in cases:
        key = key_fn(c)
        if key is None:
            continue
        buckets[key].append(c)

    for key, group in sorted(buckets.items()):
        counts = STATUS.zero_counts()
        counts.update(Counter(STATUS.classify_case(c) for c in group))
        yield key, group, counts


def in_plan(cases):
    """The cases whose scope group counts toward the total.

    A scope group marked `"excluded": true` names work that is reported but not
    committed to, so it must not move any figure read as progress. Summary is
    the one screen that still shows it — it draws a table per group, and a group
    with no table would simply vanish — so `summary_rows` does not filter and
    the report publisher passes its cases through here instead. Everything that
    adds groups together calls this, which is why the definition lives in one
    place rather than being repeated at each of them.
    """
    return [c for c in cases if SCOPES.is_counted(c.scope)]


def _counted_total(counts):
    """A group's total: the statuses in the plan, and only those.

    Not `len(group)`. Statuses the taxonomy marks `excluded` still get a column
    so their count is visible, but a case outside the plan must not inflate the
    denominator progress is read against. So the invariant is not "total equals
    the sum of every status column" but the narrower "total equals the sum of
    the *counted* ones" — which is also why the report, whose columns are the
    counted statuses, still adds up exactly.
    """
    return sum(counts[key] for key in STATUS.counted)


def summary_rows(cases, by_scope=False):
    """Per file and device: the status breakdown, plus the cases owing a reason.

    Args:
        cases: The loaded `TestCase` list.
        by_scope: Split each (file, device) further by scope group, adding a
            `scope` key to every row. The Summary view reports FPT and JP work
            as separate tables and asks for this; the report publisher does not,
            and its sheet keeps the coarser one row per (file, device). Both come
            from this one function so the two can only ever differ in
            granularity — the scope rows of a file still add up to its
            unscoped row.

    Returns:
        A `(groups, missing_reason)` tuple. `missing_reason` lists cases whose
        status is in `STATUS.needs_reason` but that carry neither a ticket id
        nor a note.
    """
    groups = []
    missing_reason = []
    needs_reason = set(STATUS.needs_reason)

    def key_fn(c):
        if by_scope:
            return (SCOPES.classify(c.scope), c.file_name, c.device)
        return (c.file_name, c.device)

    for key, group, counts in _group_counts(cases, key_fn):
        scope, file_name, device = key if by_scope else (None, *key)
        # `device_family` rides along beside `device` rather than being worked
        # out in the browser: Summary's "By device type" rows and the published
        # report then read one classification, so neither can disagree with the
        # other about which handset a block belongs to.
        row = {"file": file_name, "device": device,
               "device_family": DEVICES.classify(device),
               "total": _counted_total(counts), **counts}
        if by_scope:
            # Ahead of the counts, so a row reads scope -> file -> device -> the
            # band, the same left-to-right order the tables are drawn in.
            row = {"scope": scope, **row}
        groups.append(row)

        for c in group:
            status = STATUS.classify_case(c)
            if status not in needs_reason:
                continue
            if c.ticket_id or c.note:
                continue
            # `status` rides along so the UI can colour the row from the
            # taxonomy instead of re-classifying the raw result itself.
            missing_reason.append({
                "file": c.file_name,
                "sheet": c.sheet,
                "device": c.device,
                # The raw Scope, as `issue_rows` carries it: the caller decides
                # whether a group outside the plan owes anybody an explanation,
                # and cannot do so from a row that does not say where it came
                # from.
                "scope": c.scope,
                "row": c.row_num,
                "case_no": c.case_no,
                "result": c.result,
                "status": status,
            })

    return groups, missing_reason



def file_rows(cases, file_name):
    """One workbook, read sheet by sheet: the drill-in behind a file name.

    Summary answers "how do the files compare"; this answers "what is in this
    one". So it is `summary_rows(by_scope=True)` cut once more, by the sheet each
    case was read from — a file's sheet rows add up to its Summary rows, which
    `tests/services/test_aggregate.py` asserts directly, the same property that
    stops the scope rows and the unscoped ones drifting.

    Two things differ from every other aggregate here, and both follow from the
    page being *about one file* rather than about progress:

    - **Every scope group is kept, including one the plan excludes.** `daily_rows`,
      `productivity_rows` and `issue_rows` all run through `in_plan` because a
      figure read as progress must not count work nobody committed to. This page
      draws a Scope column and a Scope filter, and a filter whose only option is
      FPT is not one. Summary keeps excluded groups for the same reason.
    - **Sheets stay in the order the workbook names them**, not alphabetically,
      so the table reads alongside the file's own tabs — the reasoning behind
      `issue_rows` keeping source order. Within a sheet, rows follow the scope
      group order the config file sets (the fallback last, as always) and then
      the device name. The view's sortable headers reorder from there.

    `total` keeps the meaning it has everywhere else: the sum of `STATUS.counted`,
    so an excluded status such as Out Of Scope gets its column but cannot inflate
    the denominator.

    Args:
        cases: The loaded `TestCase` list — every file, as the store holds it.
        file_name: Basename of the workbook to report on. A basename, not a path,
            because that is what a `TestCase` carries and how Summary and Daily
            already key a file; two workbooks of the same name in different
            folders merge here exactly as they merge there.

    Returns:
        `{"file", "rows", "cases"}`. `cases` is that file's cases in source
        order, each a plain dict carrying the `status` it classified as and the
        `scope_group` it belongs to, so the view can list and filter them
        without a second round trip. An unknown file gives
        empty lists rather than an error: the aggregate reports what is loaded,
        and whether that is worth a 404 is the endpoint's business.
    """
    mine = [c for c in cases if c.file_name == file_name]

    sheet_order = {}
    for c in mine:
        sheet_order.setdefault(c.sheet, len(sheet_order))
    scope_order = {key: i for i, key in enumerate(SCOPES.keys)}

    def key_fn(c):
        return (c.sheet, SCOPES.classify(c.scope), c.device)

    rows = [
        {"sheet": sheet, "scope": scope, "device": device,
         "device_family": DEVICES.classify(device),
         "total": _counted_total(counts), **counts}
        for (sheet, scope, device), _group, counts in _group_counts(mine, key_fn)
    ]
    rows.sort(key=lambda r: (sheet_order[r["sheet"]], scope_order[r["scope"]], r["device"]))

    return {
        "file": file_name,
        "rows": rows,
        # `scope_group` rides along beside the raw Scope for the reason
        # `device_family` does: the rows above are keyed by group, so a page
        # filtering rows by group and cases by the string in the cell would be
        # filtering its two halves through two different vocabularies.
        "cases": [{**c.to_dict(), "status": STATUS.classify_case(c),
                   "scope_group": SCOPES.classify(c.scope)} for c in mine],
    }


def status_cases(cases, status_key):
    """Every loaded case classified as one status, as plain dicts.

    The Detail view fetches one status at a time and keeps what it fetched, so
    this is the slice behind a status figure: click the 3 in NG's column and
    these are the three rows. Splitting the load this way is what stops the
    browser being handed every case of every workbook before anyone has looked
    at one, and it only works because the slices **partition** the load — a case
    classifies as exactly one status, so two pressed cards can be unioned
    without double-counting and no case is unreachable.
    `tests/services/test_aggregate.py` asserts that directly.

    Cases are classified with `classify_case` rather than `classify`, like every
    other aggregate here: `対象外` with a PIC is a Cancel someone decided on and
    without one is work that was never in the plan, and the Result cell alone
    cannot tell them apart.

    **Work the plan excludes is kept.** Detail draws a card per scope group and
    adding an excluded one is the reader's deliberate choice, so filtering here
    would leave a card that could never be filled — the same reasoning that
    keeps every group in `file_rows` and in `summary_rows`. Everything that
    *adds groups together* still runs through `in_plan`; this produces a list,
    not a figure.

    Source order is kept, for the reason `issue_rows` keeps it: the view sorts
    from there, and the unsorted order should read like the workbook.

    Args:
        cases: The loaded `TestCase` list — every file, as the store holds it.
        status_key: A key from the taxonomy. One the taxonomy does not name
            simply matches nothing; whether that deserves a 400 is the
            endpoint's business, not this function's.

    Returns:
        A list of plain dicts, each carrying the `status` it classified as, the
        `scope_group` it belongs to and the `device_family` it merges into.
        Both ride along for the reason `file_rows` carries `scope_group` and
        `summary_rows` carries `device_family`: the figures a reader clicks are
        keyed by group and by family, so a view classifying the cases itself
        would be filtering the two halves of its own screen through two
        different vocabularies.
    """
    return [{**c.to_dict(), "status": status_key,
             "scope_group": SCOPES.classify(c.scope),
             "device_family": DEVICES.classify(c.device)}
            for c in cases if STATUS.classify_case(c) == status_key]


def daily_rows(cases):
    """Stats grouped by file, device, PIC, and test_date.

    Cases with no date belong to no day and are left out entirely, and so are
    cases in a scope group outside the plan — see `in_plan`.
    """
    def key_fn(c):
        if not c.test_date:
            return None
        return (c.file_name, c.device, c.pic or "N/A", c.test_date)

    cases = in_plan(cases)
    return [
        {"file": file_name, "device": device, "pic": pic, "date": date,
         "total": _counted_total(counts), **counts}
        for (file_name, device, pic, date), group, counts in _group_counts(cases, key_fn)
    ]


def productivity_rows(cases):
    """Cases executed per working day, per PIC.

    "Executed" is whatever the taxonomy flags as such (`STATUS.executed`), so
    the measure follows `config/result_status.json` rather than a hard-coded
    OK/NG list. A day only counts as worked when it carries at least one
    executed case: a day spent on cases that ended Pending would otherwise
    dilute the rate. Undated cases belong to no day, so they are left out
    entirely — the same rule `daily_rows` follows, as are cases in a scope group
    outside the plan.
    """
    executed_keys = STATUS.executed
    buckets = defaultdict(list)
    for c in in_plan(cases):
        if not c.test_date:
            continue
        buckets[c.pic or "N/A"].append(c)

    rows = []
    for pic, group in sorted(buckets.items()):
        counts = {key: 0 for key in executed_keys}
        days = set()
        for c in group:
            key = STATUS.classify_case(c)
            if key in counts:
                counts[key] += 1
                days.add(c.test_date)
        executed = sum(counts.values())
        rows.append({
            "pic": pic,
            **counts,
            "executed": executed,
            "days": len(days),
            "productivity": round(executed / len(days), 2) if days else 0,
        })
    return rows


def issue_rows(cases):
    """Every case whose status the taxonomy flags as an issue, in source order.

    Which statuses those are is `STATUS.issue`, not a list of keys spelled out
    here — flagging a new status in `config/result_status.json` is all it takes
    for it to start appearing in the report.

    Source order is kept deliberately: the rows then read in the same sequence
    as the workbooks they came from, so a tester can walk the sheet alongside.

    Cases in a scope group outside the plan are left out — see `in_plan`.
    """
    wanted = set(STATUS.issue)
    rows = []
    for c in in_plan(cases):
        status = STATUS.classify_case(c)
        if status not in wanted:
            continue
        rows.append({
            "file": c.file_name,
            "sheet": c.sheet,
            "device": c.device,
            "row": c.row_num,
            "case_no": c.case_no,
            "scope": c.scope,
            "status": status,
            "result": c.result,
            "test_date": c.test_date,
            "pic": c.pic,
            "ticket_id": c.ticket_id,
            "note": c.note,
        })
    return rows
