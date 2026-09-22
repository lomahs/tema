"""`/api/plan` — what the Planning view reads and writes.

The endpoints are `jsonify` wrappers around `PlanningService`, so what is
asserted here is the request-shaped part: the plan repository reaching the app
through the factory, the domain's own message surviving as a 400, and the
actuals being joined from the cases the workspace happens to hold.
"""
import pytest

from tcm.domain.plan import DayPlan
from tcm.infrastructure.excel.loader import ExcelCaseLoader
from tcm.infrastructure.store.memory import InMemoryCaseStore
from tcm.services.planning import PlanningService
from tcm.services.workspace import Workspace
from tcm.web.app import create_app
from tests.conftest import config_row, write_workbook


class FakePlanRepository:
    def __init__(self):
        self._days = {}

    def day(self, date):
        return self._days.get(date) or DayPlan.empty(date)

    def days(self):
        return [self._days[d] for d in sorted(self._days)]

    def put_day(self, day):
        self._days[day.date] = day


@pytest.fixture
def client():
    app = create_app(
        workspace=Workspace(ExcelCaseLoader(), InMemoryCaseStore()),
        planning=PlanningService(FakePlanRepository(), today=lambda: "2026-08-05"),
    )
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


@pytest.fixture
def loaded(client, tmp_path):
    """Two cases run by `lee` on 2026-08-05, and one nobody has started."""
    write_workbook(
        tmp_path / "TC.xlsx",
        [config_row("Login", "iPhone", 4, 6, cols="A B C D E F G")],
        {"Login": {
            (4, "A"): "TC-1", (4, "B"): "FPT",
            (4, "C"): "OK", (4, "D"): "2026-08-05", (4, "E"): "lee",
            (5, "A"): "TC-2", (5, "B"): "FPT",
            (5, "C"): "NG", (5, "D"): "2026-08-05", (5, "E"): "lee",
            (6, "A"): "TC-3", (6, "B"): "FPT",
        }},
    )
    client.post("/api/load", json={"folder": str(tmp_path)})
    return client


def entry(pic="lee", file="TC.xlsx", device="iPhone", planned=30):
    return {"pic": pic, "file": file, "device": device, "planned": planned}


# --- reading and writing ---------------------------------------------------

def test_a_day_nobody_planned_is_an_empty_table_not_a_404(client):
    res = client.get("/api/plan/2026-08-05")
    assert res.status_code == 200
    assert res.get_json()["rows"] == []


def test_a_saved_day_reads_back(client):
    client.put("/api/plan/2026-08-05", json={"entries": [entry(planned=25)]})
    body = client.get("/api/plan/2026-08-05").get_json()

    assert body["planned_total"] == 25
    assert body["rows"][0]["pic"] == "lee"


def test_the_domains_message_survives_as_a_400(client):
    res = client.put("/api/plan/2026-08-05", json={"entries": [entry(planned=0)]})
    assert res.status_code == 400
    assert "planned" in res.get_json()["error"]


def test_a_date_that_is_not_a_day_is_a_400(client):
    assert client.get("/api/plan/not-a-day").status_code == 400


def test_a_refused_edit_leaves_the_previous_plan_alone(client):
    client.put("/api/plan/2026-08-05", json={"entries": [entry(planned=25)]})
    client.put("/api/plan/2026-08-05", json={"entries": [entry(planned=-3)]})
    assert client.get("/api/plan/2026-08-05").get_json()["planned_total"] == 25


def test_the_plan_is_joined_to_what_was_actually_run(loaded):
    loaded.put("/api/plan/2026-08-05", json={"entries": [entry(planned=30)]})
    row = loaded.get("/api/plan/2026-08-05").get_json()["rows"][0]

    assert row["planned"] == 30
    assert row["actual"] == 2
    assert row["diff"] == -28


def test_rebaseline_refreezes_the_day(client):
    client.put("/api/plan/2026-08-05", json={"entries": [entry(planned=30)]})
    client.put("/api/plan/2026-08-05", json={"entries": [entry(planned=10)]})
    res = client.post("/api/plan/2026-08-05/baseline")

    assert res.status_code == 200
    assert client.get("/api/plan/2026-08-05").get_json()["baseline_total"] == 10


# --- the other two cuts ----------------------------------------------------

def test_the_calendar_lists_every_planned_day(client):
    client.put("/api/plan/2026-08-05", json={"entries": [entry()]})
    client.put("/api/plan/2026-08-06", json={"entries": [entry(planned=10)]})

    days = client.get("/api/plan").get_json()["days"]
    assert [(d["date"], d["planned"]) for d in days] == [
        ("2026-08-05", 30), ("2026-08-06", 10)]


def test_the_calendar_takes_a_range(client):
    client.put("/api/plan/2026-08-05", json={"entries": [entry()]})
    client.put("/api/plan/2026-08-06", json={"entries": [entry()]})

    days = client.get("/api/plan?from=2026-08-06").get_json()["days"]
    assert [d["date"] for d in days] == ["2026-08-06"]


def test_the_person_cut_reports_one_persons_days(loaded):
    loaded.put("/api/plan/2026-08-05", json={"entries": [entry(pic="lee", planned=30)]})
    body = loaded.get("/api/plan/person/lee").get_json()

    assert body["pic"] == "lee"
    assert body["planned_total"] == 30
    assert body["actual_total"] == 2


# --- the suggestion --------------------------------------------------------

def test_suggest_lists_the_blocks_with_cases_left(loaded):
    rows = loaded.get("/api/plan/suggest?date=2026-08-05").get_json()["rows"]

    assert len(rows) == 1
    assert rows[0]["file"] == "TC.xlsx"
    assert rows[0]["remaining"] == 1


def test_suggest_subtracts_what_the_day_already_gave_out(loaded):
    loaded.put("/api/plan/2026-08-05", json={"entries": [entry(planned=1)]})
    rows = loaded.get("/api/plan/suggest?date=2026-08-05").get_json()["rows"]

    assert rows[0]["assigned"] == 1
    assert rows[0]["free"] == 0


def test_suggest_narrows_to_a_device_family(loaded):
    rows = loaded.get(
        "/api/plan/suggest?date=2026-08-05&device_family=iPad").get_json()["rows"]
    assert rows == []


def test_suggest_without_a_date_is_a_400(client):
    assert client.get("/api/plan/suggest").status_code == 400


def test_suggest_with_nothing_loaded_is_an_empty_list_not_an_error(client):
    res = client.get("/api/plan/suggest?date=2026-08-05")
    assert res.status_code == 200
    assert res.get_json()["rows"] == []
