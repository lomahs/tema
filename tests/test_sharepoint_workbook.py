"""The workbook wrapper: which Graph calls it makes, and the addresses it builds."""
import re

import pytest

from sharepoint.client import GraphError
from sharepoint.links import DriveItemRef
from sharepoint.workbook import Workbook

REF = DriveItemRef(drive_id="b!DRIVE", item_id="01ITEM", name="Report.xlsx")
PREFIX = "/drives/b!DRIVE/items/01ITEM/workbook"


class FakeGraph:
    """Routes calls by regex, and remembers every one of them."""

    def __init__(self, routes=None):
        # Session handling is on every test's path, so it is wired by default.
        self.routes = [
            (r"POST .*/workbook/createSession$", {"id": "SESSION-1"}),
            (r"POST .*/workbook/closeSession$", None),
            *(routes or []),
        ]
        self.calls = []

    def request(self, method, path, headers=None, json=None, **kwargs):
        self.calls.append({"method": method, "path": path,
                           "headers": headers or {}, "json": json})
        for pattern, reply in self.routes:
            if re.match(pattern, f"{method} {path}"):
                return reply(self) if callable(reply) else reply
        raise AssertionError(f"no fake route for {method} {path}")

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, **kw):
        return self.request("POST", path, **kw)

    def patch(self, path, **kw):
        return self.request("PATCH", path, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)

    def paths(self, method=None):
        return [c["path"] for c in self.calls if method in (None, c["method"])]

    def bodies(self, method):
        return [c["json"] for c in self.calls if c["method"] == method]


def used_range(values, row_index=0):
    return {
        "address": "Summary!A1:D9",
        "rowIndex": row_index,
        "columnIndex": 0,
        "rowCount": len(values),
        "columnCount": len(values[0]) if values else 0,
        "values": values,
    }


# --- sessions --------------------------------------------------------------

def test_a_persistent_session_is_opened_and_closed_around_the_work():
    graph = FakeGraph()

    with Workbook(graph, REF):
        pass

    assert graph.paths("POST") == [f"{PREFIX}/createSession", f"{PREFIX}/closeSession"]
    assert graph.bodies("POST")[0] == {"persistChanges": True}


def test_every_call_inside_the_session_carries_its_id():
    graph = FakeGraph([(r"GET .*/worksheets\?", {"value": [{"name": "Summary"}]})])

    with Workbook(graph, REF) as wb:
        wb.worksheet_names()

    assert graph.calls[1]["headers"]["Workbook-Session-Id"] == "SESSION-1"


def test_the_session_is_closed_even_when_the_work_fails():
    graph = FakeGraph()

    with pytest.raises(RuntimeError):
        with Workbook(graph, REF):
            raise RuntimeError("boom")

    assert f"{PREFIX}/closeSession" in graph.paths("POST")


def test_an_expired_session_is_reopened_and_the_call_retried():
    """Graph drops a persistent session after a few idle minutes."""
    attempts = []

    def flaky(_graph):
        attempts.append(1)
        if len(attempts) == 1:
            raise GraphError(404, "invalidSessionId", "Session does not exist")
        return {"value": [{"name": "Summary"}]}

    graph = FakeGraph([(r"GET .*/worksheets\?", flaky)])

    with Workbook(graph, REF) as wb:
        assert wb.worksheet_names() == ["Summary"]

    assert graph.paths("POST").count(f"{PREFIX}/createSession") == 2


def test_a_missing_sheet_is_not_mistaken_for_an_expired_session():
    def missing(_graph):
        raise GraphError(404, "ItemNotFound", "Worksheet not found")

    graph = FakeGraph([(r"GET .*/worksheets\?", missing)])

    with Workbook(graph, REF) as wb:
        with pytest.raises(GraphError):
            wb.worksheet_names()

    assert graph.paths("POST").count(f"{PREFIX}/createSession") == 1


# --- reading ---------------------------------------------------------------

def test_worksheet_names_come_back_in_workbook_order():
    graph = FakeGraph([(r"GET .*/worksheets\?",
                        {"value": [{"name": "Summary"}, {"name": "Daily"}]})])

    with Workbook(graph, REF) as wb:
        assert wb.worksheet_names() == ["Summary", "Daily"]


def test_used_range_is_read_by_value_so_stray_formatting_is_ignored():
    graph = FakeGraph([(r"GET .*/usedRange", used_range([["Run date", "File"]]))])

    with Workbook(graph, REF) as wb:
        rng = wb.used_range("Summary")

    assert "valuesOnly=true" in graph.paths("GET")[0]
    assert rng.last_row == 1
    assert rng.values == [["Run date", "File"]]


def test_an_empty_sheet_reports_the_header_row_as_its_last_row():
    """Graph answers a blank sheet with a single empty cell, not nothing."""
    graph = FakeGraph([(r"GET .*/usedRange", used_range([[""]]))])

    with Workbook(graph, REF) as wb:
        assert wb.used_range("Summary").last_row == 1


def test_a_used_range_that_starts_below_row_one_reports_its_real_last_row():
    graph = FakeGraph([(r"GET .*/usedRange", used_range([["a"], ["b"]], row_index=4))])

    with Workbook(graph, REF) as wb:
        assert wb.used_range("Summary").last_row == 6


# --- writing ---------------------------------------------------------------

def test_values_are_patched_into_the_address_they_belong_at():
    graph = FakeGraph([(r"PATCH .*/range\(address=", None)])

    with Workbook(graph, REF) as wb:
        wb.write_values("Summary", first_row=5, first_column=1, rows=[[1, 2, 3], [4, 5, 6]])

    assert "range(address='Summary!A5:C6')" in graph.paths("PATCH")[0]
    assert graph.bodies("PATCH")[0] == {"values": [[1, 2, 3], [4, 5, 6]]}


def test_writing_starts_at_the_column_it_is_told_to():
    graph = FakeGraph([(r"PATCH .*/range\(address=", None)])

    with Workbook(graph, REF) as wb:
        wb.write_values("Daily", first_row=2, first_column=3, rows=[["x", "y"]])

    assert "range(address='Daily!C2:D2')" in graph.paths("PATCH")[0]


def test_a_long_write_is_split_into_several_calls():
    graph = FakeGraph([(r"PATCH .*/range\(address=", None)])
    rows = [[i] for i in range(1200)]

    with Workbook(graph, REF, chunk_size=500) as wb:
        wb.write_values("Summary", first_row=2, first_column=1, rows=rows)

    addresses = graph.paths("PATCH")
    assert len(addresses) == 3
    assert "A2:A501" in addresses[0]
    assert "A502:A1001" in addresses[1]
    assert "A1002:A1201" in addresses[2]


def test_writing_nothing_makes_no_call_at_all():
    graph = FakeGraph()

    with Workbook(graph, REF) as wb:
        wb.write_values("Summary", first_row=5, first_column=1, rows=[])

    assert graph.paths("PATCH") == []


def test_deleting_rows_shifts_the_ones_below_upwards():
    graph = FakeGraph([(r"POST .*/range\(address=.*/delete$", None)])

    with Workbook(graph, REF) as wb:
        wb.delete_rows("Summary", first_row=4, count=3, first_column=1, width=4)

    delete_call = [c for c in graph.calls if c["path"].endswith("/delete")][0]
    assert "range(address='Summary!A4:D6')" in delete_call["path"]
    assert delete_call["json"] == {"shift": "Up"}


# --- tables ----------------------------------------------------------------

def test_a_table_whose_header_sits_on_the_layouts_header_row_is_found():
    graph = FakeGraph([
        (r"GET .*/worksheets\('Summary'\)/tables", {"value": [{"name": "SummaryTable"}]}),
        (r"GET .*/tables\('SummaryTable'\)/headerRowRange", {"rowIndex": 0}),
    ])

    with Workbook(graph, REF) as wb:
        assert wb.table_at("Summary", header_row=1) == "SummaryTable"


def test_a_table_that_starts_elsewhere_is_not_used():
    graph = FakeGraph([
        (r"GET .*/worksheets\('Summary'\)/tables", {"value": [{"name": "Other"}]}),
        (r"GET .*/tables\('Other'\)/headerRowRange", {"rowIndex": 20}),
    ])

    with Workbook(graph, REF) as wb:
        assert wb.table_at("Summary", header_row=1) is None


def test_a_sheet_with_no_table_falls_back_to_plain_ranges():
    graph = FakeGraph([(r"GET .*/worksheets\('Summary'\)/tables", {"value": []})])

    with Workbook(graph, REF) as wb:
        assert wb.table_at("Summary", header_row=1) is None


def test_table_rows_come_back_with_the_index_needed_to_delete_them():
    graph = FakeGraph([(r"GET .*/tables\('T'\)/rows", {"value": [
        {"index": 0, "values": [["2026-09-05", "a"]]},
        {"index": 1, "values": [["2026-09-06", "b"]]},
    ]})])

    with Workbook(graph, REF) as wb:
        assert wb.table_rows("T") == [
            (0, ["2026-09-05", "a"]),
            (1, ["2026-09-06", "b"]),
        ]


def test_rows_added_to_a_table_go_on_the_end():
    graph = FakeGraph([(r"POST .*/tables\('T'\)/rows$", {"index": 9})])

    with Workbook(graph, REF) as wb:
        wb.table_add_rows("T", [["x"], ["y"]])

    assert graph.bodies("POST")[1] == {"values": [["x"], ["y"]], "index": None}


def test_a_long_table_append_is_split_into_several_calls():
    graph = FakeGraph([(r"POST .*/tables\('T'\)/rows$", {"index": 0})])

    with Workbook(graph, REF, chunk_size=500) as wb:
        wb.table_add_rows("T", [[i] for i in range(1100)])

    assert len([p for p in graph.paths("POST") if p.endswith("/rows")]) == 3


def test_a_table_row_is_deleted_by_its_index():
    graph = FakeGraph([(r"DELETE .*/tables\('T'\)/rows/2$", None)])

    with Workbook(graph, REF) as wb:
        wb.table_delete_row("T", 2)

    assert graph.paths("DELETE")[0].endswith("/tables('T')/rows/2")
