"""Publishing a report into a workbook, against a stand-in for the real one.

`FakeWorkbook` keeps a real grid of cells and implements exactly the interface
`sharepoint.workbook.Workbook` offers, so these tests exercise the arithmetic
that decides *where* rows land without going near Graph.
"""
from datetime import datetime

import pytest

from parser import models
from report.layout import ReportLayout
from report.publisher import SheetMissing, publish
from sharepoint.workbook import UsedRange


class FakeWorkbook:
    """A workbook as a dict of grids. Row 1 of a sheet is `grid[0]`."""

    def __init__(self, sheets, tables=None):
        self.grids = {name: [list(row) for row in rows] for name, rows in sheets.items()}
        #: sheet -> (table name, header row). A sheet absent from here has no table.
        self.tables = dict(tables or {})
        self._by_table = {name: (sheet, header)
                          for sheet, (name, header) in self.tables.items()}

    # --- reading ---

    def worksheet_names(self):
        return list(self.grids)

    def used_range(self, sheet):
        grid = self.grids[sheet]
        # Graph reports the occupied rectangle, so trailing blank rows are not in it.
        while grid and all(cell in (None, "") for cell in grid[-1]):
            grid = grid[:-1]
        width = max((len(row) for row in grid), default=0)
        return UsedRange(row_index=0, column_index=0, row_count=len(grid),
                         column_count=width,
                         values=[row + [""] * (width - len(row)) for row in grid])

    # --- writing ---

    def write_values(self, sheet, first_row, first_column, rows):
        grid = self.grids[sheet]
        for offset, values in enumerate(rows):
            row_index = first_row - 1 + offset
            while len(grid) <= row_index:
                grid.append([])
            row = grid[row_index]
            while len(row) < first_column - 1 + len(values):
                row.append("")
            for i, value in enumerate(values):
                row[first_column - 1 + i] = value

    def delete_rows(self, sheet, first_row, count, first_column, width):
        del self.grids[sheet][first_row - 1:first_row - 1 + count]

    # --- tables ---

    def table_at(self, sheet, header_row):
        name, table_header = self.tables.get(sheet, (None, None))
        return name if table_header == header_row else None

    def table_rows(self, table):
        sheet, header_row = self._by_table[table]
        body = self.grids[sheet][header_row:]
        return [(i, list(row)) for i, row in enumerate(body)]

    def table_add_rows(self, table, rows):
        sheet, header_row = self._by_table[table]
        self.write_values(sheet, len(self.grids[sheet]) + 1, 1, rows)

    def table_delete_row(self, table, index):
        sheet, header_row = self._by_table[table]
        del self.grids[sheet][header_row + index]


SUMMARY_ONLY = {"sheets": [{
    "dataset": "summary", "sheet": "Summary", "header_row": 1, "first_column": "A",
    "columns": [{"field": "run_date"}, {"field": "file"}, {"field": "device"},
                {"field": "total"}],
}]}

HEADER = ["Run date", "File", "Device", "Total"]


def layout(raw=None):
    return ReportLayout.from_dict(raw or SUMMARY_ONLY)


def case(**kwargs):
    return models.TestCase(**{"file_name": "TC.xlsx", "sheet": "Login",
                              "device": "iPhone", "row_num": 4, **kwargs})


def data_rows(workbook, sheet="Summary", header_row=1):
    return workbook.grids[sheet][header_row:]


# --- appending -------------------------------------------------------------

def test_rows_are_appended_below_whatever_the_sheet_already_holds():
    wb = FakeWorkbook({"Summary": [HEADER, ["2026-09-05", "old.xlsx", "iPad", 9]]})

    publish([case(result="OK")], wb, layout(), run_date="2026-09-06")

    assert data_rows(wb) == [
        ["2026-09-05", "old.xlsx", "iPad", 9],
        ["2026-09-06", "TC.xlsx", "iPhone", 1],
    ]


def test_the_first_publish_into_an_empty_sheet_lands_under_the_header():
    wb = FakeWorkbook({"Summary": [HEADER]})

    publish([case(result="OK")], wb, layout(), run_date="2026-09-06")

    assert data_rows(wb) == [["2026-09-06", "TC.xlsx", "iPhone", 1]]


def test_a_report_says_what_it_did_to_each_sheet():
    wb = FakeWorkbook({"Summary": [HEADER]})

    result = publish([case(result="OK")], wb, layout(), run_date="2026-09-06")

    assert result["run_date"] == "2026-09-06"
    assert result["sheets"] == [{"sheet": "Summary", "deleted": 0, "appended": 1}]


def test_a_header_further_down_the_sheet_is_respected():
    """Report sheets often carry a title and a blank row above the table."""
    raw = {"sheets": [{**SUMMARY_ONLY["sheets"][0], "header_row": 3}]}
    wb = FakeWorkbook({"Summary": [["Weekly report"], [], HEADER]})

    publish([case(result="OK")], wb, layout(raw), run_date="2026-09-06")

    assert data_rows(wb, header_row=3) == [["2026-09-06", "TC.xlsx", "iPhone", 1]]


def test_a_table_that_starts_left_of_column_a_is_written_in_place():
    raw = {"sheets": [{**SUMMARY_ONLY["sheets"][0], "first_column": "C"}]}
    wb = FakeWorkbook({"Summary": [["", "", *HEADER]]})

    publish([case(result="OK")], wb, layout(raw), run_date="2026-09-06")

    assert data_rows(wb) == [["", "", "2026-09-06", "TC.xlsx", "iPhone", 1]]


# --- replacing a day -------------------------------------------------------

def test_rows_from_the_same_day_are_replaced_rather_than_doubled():
    wb = FakeWorkbook({"Summary": [HEADER]})

    publish([case(result="OK")], wb, layout(), run_date="2026-09-06")
    publish([case(result="OK")], wb, layout(), run_date="2026-09-06")

    assert data_rows(wb) == [["2026-09-06", "TC.xlsx", "iPhone", 1]]


def test_publishing_twice_leaves_the_sheet_exactly_as_it_was():
    """The whole point of keying on run_date: a re-run is safe after a failure."""
    wb = FakeWorkbook({"Summary": [HEADER, ["2026-09-05", "old.xlsx", "iPad", 9]]})
    cases = [case(result="OK"), case(device="iPad", result="NG")]

    publish(cases, wb, layout(), run_date="2026-09-06")
    once = [list(row) for row in wb.grids["Summary"]]
    publish(cases, wb, layout(), run_date="2026-09-06")

    assert wb.grids["Summary"] == once


def test_earlier_days_are_left_alone():
    wb = FakeWorkbook({"Summary": [
        HEADER,
        ["2026-09-04", "a.xlsx", "iPad", 1],
        ["2026-09-06", "stale.xlsx", "iPad", 2],
        ["2026-09-05", "b.xlsx", "iPad", 3],
    ]})

    result = publish([case(result="OK")], wb, layout(), run_date="2026-09-06")

    assert result["sheets"][0]["deleted"] == 1
    assert data_rows(wb) == [
        ["2026-09-04", "a.xlsx", "iPad", 1],
        ["2026-09-05", "b.xlsx", "iPad", 3],
        ["2026-09-06", "TC.xlsx", "iPhone", 1],
    ]


def test_same_day_rows_scattered_through_the_sheet_are_all_removed():
    """Deleting shifts rows up, so the blocks must come out bottom first."""
    wb = FakeWorkbook({"Summary": [
        HEADER,
        ["2026-09-06", "x", "iPad", 1],
        ["2026-09-05", "keep-1", "iPad", 2],
        ["2026-09-06", "y", "iPad", 3],
        ["2026-09-06", "z", "iPad", 4],
        ["2026-09-05", "keep-2", "iPad", 5],
    ]})

    result = publish([], wb, layout(), run_date="2026-09-06")

    assert result["sheets"][0]["deleted"] == 3
    assert data_rows(wb) == [
        ["2026-09-05", "keep-1", "iPad", 2],
        ["2026-09-05", "keep-2", "iPad", 5],
    ]


def test_a_date_formatted_run_date_column_is_still_recognised():
    """Excel hands a real date back as a serial number, not "2026-09-06"."""
    wb = FakeWorkbook({"Summary": [HEADER, [46271, "stale.xlsx", "iPad", 2]]})

    result = publish([case(result="OK")], wb, layout(), run_date="2026-09-06")

    assert result["sheets"][0]["deleted"] == 1


def test_a_run_date_written_with_a_time_on_it_is_still_recognised():
    wb = FakeWorkbook({"Summary": [HEADER, ["2026-09-06 00:00:00", "stale", "iPad", 2]]})

    assert publish([], wb, layout(), run_date="2026-09-06")["sheets"][0]["deleted"] == 1


def test_a_blank_run_date_cell_is_never_treated_as_a_match():
    wb = FakeWorkbook({"Summary": [HEADER, ["", "manual note", "", ""]]})

    publish([], wb, layout(), run_date="2026-09-06")

    assert data_rows(wb) == [["", "manual note", "", ""]]


# --- tables ----------------------------------------------------------------

def test_a_sheet_backed_by_a_table_is_appended_through_the_table():
    wb = FakeWorkbook({"Summary": [HEADER]}, tables={"Summary": ("SummaryTable", 1)})

    publish([case(result="OK")], wb, layout(), run_date="2026-09-06")

    assert data_rows(wb) == [["2026-09-06", "TC.xlsx", "iPhone", 1]]


def test_a_table_replaces_the_same_days_rows_too():
    wb = FakeWorkbook(
        {"Summary": [HEADER, ["2026-09-05", "keep", "iPad", 1],
                     ["2026-09-06", "stale", "iPad", 2]]},
        tables={"Summary": ("SummaryTable", 1)},
    )

    result = publish([case(result="OK")], wb, layout(), run_date="2026-09-06")

    assert result["sheets"][0]["deleted"] == 1
    assert data_rows(wb) == [
        ["2026-09-05", "keep", "iPad", 1],
        ["2026-09-06", "TC.xlsx", "iPhone", 1],
    ]


def test_publishing_twice_into_a_table_is_idempotent_as_well():
    wb = FakeWorkbook({"Summary": [HEADER]}, tables={"Summary": ("SummaryTable", 1)})

    publish([case(result="OK")], wb, layout(), run_date="2026-09-06")
    once = [list(row) for row in wb.grids["Summary"]]
    publish([case(result="OK")], wb, layout(), run_date="2026-09-06")

    assert wb.grids["Summary"] == once


# --- all three datasets ----------------------------------------------------

def test_every_sheet_in_the_layout_is_published():
    from report.layout import ReportLayout as RL

    wb = FakeWorkbook({"Summary": [["h"]], "Daily": [["h"]], "Issues": [["h"]]})
    cases = [case(result="NG", test_date="2026-08-05", pic="lee", case_no="TC-2")]

    result = publish(cases, wb, RL.load(), run_date="2026-09-06")

    assert [s["sheet"] for s in result["sheets"]] == ["Summary", "Daily", "Issues"]
    assert [s["appended"] for s in result["sheets"]] == [1, 1, 1]


def test_the_issues_sheet_holds_only_the_cases_the_taxonomy_flags():
    from report.layout import ReportLayout as RL

    wb = FakeWorkbook({"Summary": [["h"]], "Daily": [["h"]], "Issues": [["h"]]})
    cases = [case(result="OK", case_no="TC-1", test_date="2026-08-05"),
             case(result="NG", case_no="TC-2", test_date="2026-08-05")]

    publish(cases, wb, RL.load(), run_date="2026-09-06")

    assert [row[3] for row in data_rows(wb, "Issues")] == ["TC-2"]


# --- failure ---------------------------------------------------------------

def test_a_sheet_the_report_file_does_not_have_is_named_in_the_error():
    wb = FakeWorkbook({"Something Else": [HEADER]})

    with pytest.raises(SheetMissing, match="Summary"):
        publish([case(result="OK")], wb, layout(), run_date="2026-09-06")


def test_a_missing_sheet_is_noticed_before_anything_is_written():
    """Half a report is worse than none, so every sheet is checked up front."""
    raw = {"sheets": [
        SUMMARY_ONLY["sheets"][0],
        {"dataset": "daily", "sheet": "Daily", "header_row": 1, "first_column": "A",
         "columns": [{"field": "run_date"}, {"field": "date"}]},
    ]}
    wb = FakeWorkbook({"Summary": [HEADER]})

    with pytest.raises(SheetMissing, match="Daily"):
        publish([case(result="OK")], wb, layout(raw), run_date="2026-09-06")

    assert data_rows(wb) == []


def test_the_run_date_defaults_to_today_when_none_is_given():
    wb = FakeWorkbook({"Summary": [HEADER]})

    result = publish([case(result="OK")], wb, layout())

    assert result["run_date"] == datetime.now().strftime("%Y-%m-%d")


def test_nothing_loaded_still_clears_the_days_stale_rows():
    """Publishing an empty load is how a mistaken publish gets taken back."""
    wb = FakeWorkbook({"Summary": [HEADER, ["2026-09-06", "stale", "iPad", 2]]})

    result = publish([], wb, layout(), run_date="2026-09-06")

    assert result["sheets"] == [{"sheet": "Summary", "deleted": 1, "appended": 0}]
    assert data_rows(wb) == []


# --- tying the link, the session and the publish together -------------------

def test_publishing_to_a_url_resolves_the_link_and_names_the_file():
    from report import publisher

    opened = []

    class StubGraph:
        def get(self, path, **kw):
            return {"id": "01ITEM", "name": "QA Report.xlsx",
                    "webUrl": "https://contoso.sharepoint.com/r.xlsx",
                    "parentReference": {"driveId": "b!DRIVE"}}

    wb = FakeWorkbook({"Summary": [HEADER]})

    class StubWorkbook:
        def __init__(self, client, ref):
            opened.append(ref)

        def __enter__(self):
            return wb

        def __exit__(self, *exc):
            return False

    result = publisher.publish_to_url(
        [case(result="OK")], StubGraph(),
        "https://contoso.sharepoint.com/:x:/r/sites/qa/r.xlsx",
        run_date="2026-09-06", layout=layout(), workbook_factory=StubWorkbook,
    )

    assert opened[0].drive_id == "b!DRIVE"
    assert result["file"] == "QA Report.xlsx"
    assert result["sheets"][0]["appended"] == 1
    assert data_rows(wb) == [["2026-09-06", "TC.xlsx", "iPhone", 1]]
