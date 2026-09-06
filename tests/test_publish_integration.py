"""The whole publish stack over a fake Graph service.

The unit tests drive the publisher through `FakeWorkbook`, which could drift
from the real `Workbook`. Here everything but the socket is real — `GraphClient`,
`share_url_to_item` and `Workbook` included — and the fake service parses the
addresses it is sent, so wrong row arithmetic shows up as wrong cells.
"""
import re

from openpyxl.utils import column_index_from_string

from parser import models
from report.layout import ReportLayout
from report.publisher import publish_to_url
from sharepoint.client import GraphClient

LAYOUT = ReportLayout.from_dict({"sheets": [{
    "dataset": "summary", "sheet": "Summary", "header_row": 2, "first_column": "B",
    "columns": [{"field": "run_date"}, {"field": "file"}, {"field": "device"},
                {"field": "total"}],
}]})

ADDRESS = re.compile(r"range\(address='(?P<sheet>[^!]+)!(?P<start>[A-Z]+)(?P<top>\d+):"
                     r"(?P<end>[A-Z]+)(?P<bottom>\d+)'\)")


class Reply:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.headers = {}
        self._body = body

    def json(self):
        return self._body


class FakeGraphService:
    """A workbook behind Graph's URL shapes. `grid[0]` is Excel row 1."""

    def __init__(self, grid):
        self.grid = [list(row) for row in grid]
        self.sessions = 0

    def request(self, method, url, headers=None, json=None, **kwargs):
        route = f"{method} {url}"

        if "/shares/" in url:
            return Reply(200, {"id": "01ITEM", "name": "QA Report.xlsx",
                               "webUrl": "https://contoso.sharepoint.com/r.xlsx",
                               "parentReference": {"driveId": "b!DRIVE"}})
        if route.endswith("/createSession"):
            self.sessions += 1
            return Reply(200, {"id": f"SESSION-{self.sessions}"})
        if route.endswith("/closeSession"):
            return Reply(204)
        if "/worksheets?" in url:
            return Reply(200, {"value": [{"name": "Summary"}]})
        if "/tables?" in url:
            return Reply(200, {"value": []})
        if "/usedRange" in url:
            return Reply(200, self._used_range())
        if method == "PATCH":
            return self._write(url, json["values"])
        if route.endswith("/delete"):
            return self._delete(url)

        raise AssertionError(f"the fake service was not expecting {route}")

    def _used_range(self):
        rows = list(self.grid)
        while rows and all(c in (None, "") for c in rows[-1]):
            rows.pop()
        width = max((len(r) for r in rows), default=0)
        return {"address": "Summary!A1", "rowIndex": 0, "columnIndex": 0,
                "rowCount": len(rows), "columnCount": width,
                "values": [r + [""] * (width - len(r)) for r in rows]}

    def _write(self, url, values):
        m = ADDRESS.search(url)
        first_row, first_col = int(m["top"]), column_index_from_string(m["start"])
        for offset, row in enumerate(values):
            index = first_row - 1 + offset
            while len(self.grid) <= index:
                self.grid.append([])
            target = self.grid[index]
            while len(target) < first_col - 1 + len(row):
                target.append("")
            for i, value in enumerate(row):
                target[first_col - 1 + i] = value
        return Reply(200, {})

    def _delete(self, url):
        m = ADDRESS.search(url)
        top, bottom = int(m["top"]), int(m["bottom"])
        del self.grid[top - 1:bottom]
        return Reply(204)


def case(**kwargs):
    return models.TestCase(**{"file_name": "TC.xlsx", "sheet": "Login",
                              "device": "iPhone", "row_num": 4, **kwargs})


def publish_against(service, cases, run_date="2026-09-06"):
    client = GraphClient(lambda: "TOKEN", transport=service, sleep=lambda _s: None)
    return publish_to_url(cases, client, "https://contoso.sharepoint.com/:x:/r/qa/r.xlsx",
                          run_date=run_date, layout=LAYOUT)


def test_a_publish_lands_in_the_cells_the_layout_points_at():
    service = FakeGraphService([
        ["Quarterly QA report"],
        ["", "Run date", "File", "Device", "Total"],
    ])

    result = publish_against(service, [case(result="OK")])

    assert result["file"] == "QA Report.xlsx"
    assert service.grid[2] == ["", "2026-09-06", "TC.xlsx", "iPhone", 1]


def test_the_same_day_is_replaced_not_repeated_across_the_real_stack():
    service = FakeGraphService([
        ["Quarterly QA report"],
        ["", "Run date", "File", "Device", "Total"],
        ["", "2026-09-05", "old.xlsx", "iPad", 9],
    ])
    cases = [case(result="OK"), case(device="iPad", result="NG")]

    publish_against(service, cases)
    after_one = [list(row) for row in service.grid]
    publish_against(service, cases)

    assert service.grid == after_one
    assert service.grid[2] == ["", "2026-09-05", "old.xlsx", "iPad", 9]


def test_everything_runs_inside_a_single_workbook_session():
    service = FakeGraphService([["x"], ["", "Run date", "File", "Device", "Total"]])

    publish_against(service, [case(result="OK")])

    assert service.sessions == 1
