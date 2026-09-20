"""Running the two preparation operations over a set of workbooks.

`tool_data` and `clearing` each know how to handle one workbook. This is the layer
above: it walks a list of them, isolates the failures, and returns plain dicts.

It exists for the same reason `tcm/services/aggregation.py` does: the
endpoints are `jsonify` wrappers around these functions, which keeps the
per-file walking and the error isolation out of the routes. Nothing here
imports Flask or touches the request; the routes own the HTTP.

**Errors are per-file, not fatal**, exactly as in `load_files`: one workbook
whose TOOL_DATA is unreadable must not sink a batch of forty.
"""

import logging
import os

from tcm.infrastructure.excel.reader import exclude_lock_files, find_workbooks, parse_tool_data
from tcm.infrastructure.excel.clearing import apply_plan, plan_file
from tcm.infrastructure.excel.tool_data import detect_file, diff_configs, write_tool_data_sheet
from tcm.infrastructure.excel.workbook import has_tool_data


log = logging.getLogger(__name__)


def source_workbooks(source: dict | None) -> list[str]:
    """Every workbook a loaded source names.

    `source` is the `{"type", "value"}` dict `/api/load` remembers. A folder is
    re-globbed rather than remembered, so a workbook added since the last load
    still appears — which is the reason to open the panel at all.
    """
    if not source:
        return []
    if source["type"] == "folder":
        return find_workbooks(source["value"])
    return exclude_lock_files(source["value"])


def describe(paths: list[str]) -> list[dict]:
    """Report what state each workbook is in.

    `has_tool_data` is what decides whether a file is offered "Create" or
    "Check"; `blocks` is how many device blocks its sheet already describes, or
    `None` when there is no readable sheet to count.
    """
    files = []
    for path in paths:
        entry = {"file": os.path.basename(path), "path": path,
                 "has_tool_data": False, "blocks": None}
        try:
            entry["has_tool_data"] = has_tool_data(path)
            if entry["has_tool_data"]:
                entry["blocks"] = len(parse_tool_data(path))
        except Exception as e:
            # A workbook that cannot even be opened still belongs on the list —
            # seeing it there with its error is how you find out why.
            log.warning("[%s] Could not inspect: %s", entry["file"], e)
            entry["error"] = str(e)
        files.append(entry)
    return files


def detect(paths: list[str], apply: bool = False) -> list[dict]:
    """Detect each workbook's layout, and write it in when `apply`.

    A workbook that already has a TOOL_DATA sheet is diffed rather than assumed
    stale — it may have been corrected by hand — so the caller can show what
    would change before allowing the overwrite.
    """
    results = []
    for path in paths:
        entry = {"file": os.path.basename(path), "path": path,
                 "detected": [], "unresolved": [], "diff": None, "written": False}
        try:
            configs, unresolved = detect_file(path)
            entry["detected"] = [c.to_dict() for c in configs]
            entry["unresolved"] = [
                {"sheet": u.sheet, "row": u.row, "reason": u.reason} for u in unresolved
            ]

            if has_tool_data(path):
                try:
                    entry["diff"] = diff_configs(parse_tool_data(path), configs).to_dict()
                except ValueError as e:
                    # An unreadable sheet is exactly what needs replacing, so
                    # this is reported rather than treated as a failure.
                    entry["diff_error"] = str(e)

            if apply:
                if configs:
                    write_tool_data_sheet(path, configs)
                    entry["written"] = True
                else:
                    # Writing an empty sheet would delete a working one.
                    entry["error"] = "Nothing detected; left as it was"
        except Exception as e:
            log.warning("[%s] TOOL_DATA detection failed: %s", entry["file"], e)
            entry["error"] = str(e)
        results.append(entry)
    return results


def clear(paths: list[str], keep: set[str], apply: bool = False) -> list[dict]:
    """Plan each workbook's results wipe, and carry it out when `apply`.

    `keep` is taken as already validated against the taxonomy: a typo that
    silently cleared the rows it was meant to protect is not recoverable from
    the file, so that check belongs at the edge, before any file is opened.
    """
    results = []
    for path in paths:
        entry = {"file": os.path.basename(path), "path": path,
                 "plan": None, "applied": False}
        try:
            plan = plan_file(path, keep)
            entry["plan"] = plan.to_dict()
            if apply and plan.items:
                apply_plan(path, plan)
                entry["applied"] = True
        except Exception as e:
            log.warning("[%s] Clearing failed: %s", entry["file"], e)
            entry["error"] = str(e)
        results.append(entry)
    return results
