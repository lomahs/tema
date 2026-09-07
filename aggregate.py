"""Turning loaded test cases into the four aggregate views.

These are plain functions over `TestCase` lists with no Flask involvement, so
the API layer and the SharePoint report publisher compute the same numbers from
the same code. Every count is bucketed through `STATUS`, which means the result
taxonomy stays the single place where the vocabulary is defined.
"""
from collections import Counter, defaultdict

from parser.status import STATUS


def _group_counts(cases, key_fn):
    """Bucket cases by `key_fn` and count each bucket by status key.

    Yields (key, group, counts) with every status key present in `counts`, so a
    group's `total` always equals the sum of its status columns.
    """
    buckets = defaultdict(list)
    for c in cases:
        key = key_fn(c)
        if key is None:
            continue
        buckets[key].append(c)

    for key, group in sorted(buckets.items()):
        counts = STATUS.zero_counts()
        counts.update(Counter(STATUS.classify(c.result) for c in group))
        yield key, group, counts


def summary_rows(cases):
    """Per file and device: the status breakdown, plus the cases owing a reason.

    Returns:
        A `(groups, missing_reason)` tuple. `missing_reason` lists cases whose
        status is in `STATUS.needs_reason` but that carry neither a ticket id
        nor a note.
    """
    groups = []
    missing_reason = []
    needs_reason = set(STATUS.needs_reason)

    for (file_name, device), group, counts in _group_counts(
        cases, lambda c: (c.file_name, c.device)
    ):
        groups.append({"file": file_name, "device": device, "total": len(group), **counts})

        for c in group:
            status = STATUS.classify(c.result)
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
                "row": c.row_num,
                "case_no": c.case_no,
                "result": c.result,
                "status": status,
            })

    return groups, missing_reason


def daily_rows(cases):
    """Stats grouped by file, device, PIC, and test_date.

    Cases with no date belong to no day and are left out entirely.
    """
    def key_fn(c):
        if not c.test_date:
            return None
        return (c.file_name, c.device, c.pic or "N/A", c.test_date)

    return [
        {"file": file_name, "device": device, "pic": pic, "date": date,
         "total": len(group), **counts}
        for (file_name, device, pic, date), group, counts in _group_counts(cases, key_fn)
    ]


def productivity_rows(cases):
    """Cases executed per working day, per PIC.

    "Executed" is whatever the taxonomy flags as such (`STATUS.executed`), so
    the measure follows `parser/result_status.json` rather than a hard-coded
    OK/NG list. A day only counts as worked when it carries at least one
    executed case: a day spent on cases that ended Pending would otherwise
    dilute the rate. Undated cases belong to no day, so they are left out
    entirely — the same rule `daily_rows` follows.
    """
    executed_keys = STATUS.executed
    buckets = defaultdict(list)
    for c in cases:
        if not c.test_date:
            continue
        buckets[c.pic or "N/A"].append(c)

    rows = []
    for pic, group in sorted(buckets.items()):
        counts = {key: 0 for key in executed_keys}
        days = set()
        for c in group:
            key = STATUS.classify(c.result)
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
    here — flagging a new status in `parser/result_status.json` is all it takes
    for it to start appearing in the report.

    Source order is kept deliberately: the rows then read in the same sequence
    as the workbooks they came from, so a tester can walk the sheet alongside.
    """
    wanted = set(STATUS.issue)
    rows = []
    for c in cases:
        status = STATUS.classify(c.result)
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
