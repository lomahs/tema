"""`/api/plan` — what the Planning view reads and writes.

The endpoints are `jsonify` wrappers around `PlanningService`, so what is
asserted here is the request-shaped part: the plan repository reaching the app
through the factory, the domain's own message surviving as a 400, and the
actuals being joined from the cases the workspace happens to hold.
"""
import pytest

from tcm.domain.plan import DayPlan, PlanSettings
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

    _settings = None

    def settings(self):
        return self._settings or PlanSettings()

    def put_settings(self, settings):
        self._settings = settings


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


# --- the suggestion --------------------------------------------------------


# --- the phase, the board and the settings ------------------------------------

def test_phase_answers_with_nothing_loaded(client):
    r = client.get("/api/plan/phase")
    assert r.status_code == 200 and r.get_json()["kpis"]["remaining"] == 0


def test_phase_refuses_an_unknown_window(client):
    assert client.get("/api/plan/phase?window=7").status_code == 400


def test_phase_reads_the_loaded_cases(loaded):
    body = loaded.get("/api/plan/phase?window=all").get_json()
    assert body["kpis"]["at_start"] > 0


def test_board_answers_with_nothing_loaded(client):
    r = client.get("/api/plan/board/2026-08-05")
    assert r.status_code == 200 and r.get_json()["slots"] == []


def test_board_refuses_a_date_that_is_not_a_day(client):
    assert client.get("/api/plan/board/tomorrow").status_code == 400


def test_settings_round_trip_and_refusal(client):
    ok = client.put("/api/plan/settings", json={"phase_start": "2026-08-03",
                                                "phase_end": "2026-08-14", "daily_target": 25})
    assert ok.status_code == 200
    assert client.get("/api/plan/settings").get_json()["daily_target"] == 25
    bad = client.put("/api/plan/settings",
                     json={"phase_start": "2026-08-14", "phase_end": "2026-08-03"})
    assert bad.status_code == 400 and "before it starts" in bad.get_json()["error"]
    assert client.get("/api/plan/settings").get_json()["phase_start"] == "2026-08-03"


def test_the_removed_cuts_are_gone(client):
    assert client.get("/api/plan/person/An").status_code == 404
    assert client.post("/api/plan/2026-08-05/baseline").status_code in (404, 405)
    # "suggest" now reads as a date and is refused as one.
    assert client.get("/api/plan/suggest?date=2026-08-05").status_code == 400
