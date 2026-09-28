"""`/api/member/*` — what the Member tab reads.

The four endpoints are `jsonify` wrappers around `MemberService`, which the
factory builds over the app's own `PlanningService`; what is asserted here is
the request-shaped part. Today is 2026-08-06, so `lee`'s work on the 5th is
yesterday's and inside every total.
"""
import pytest

from tcm.infrastructure.excel.loader import ExcelCaseLoader
from tcm.infrastructure.store.memory import InMemoryCaseStore
from tcm.services.planning import PlanningService
from tcm.services.workspace import Workspace
from tcm.web.app import create_app
from tests.conftest import config_row, write_workbook
from tests.web.test_api_planning import FakePlanRepository


@pytest.fixture
def client():
    app = create_app(
        workspace=Workspace(ExcelCaseLoader(), InMemoryCaseStore()),
        planning=PlanningService(FakePlanRepository(), today=lambda: "2026-08-06"),
    )
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


@pytest.fixture
def loaded(client, tmp_path):
    """`lee` ran an OK, an NG and cancelled one on 2026-08-05 (a Wednesday)."""
    write_workbook(
        tmp_path / "TC.xlsx",
        [config_row("Login", "iPhone", 4, 6, cols="A B C D E F G")],
        {"Login": {
            (4, "A"): "TC-1", (4, "B"): "FPT",
            (4, "C"): "OK", (4, "D"): "2026-08-05", (4, "E"): "lee",
            (5, "A"): "TC-2", (5, "B"): "FPT",
            (5, "C"): "NG", (5, "D"): "2026-08-05", (5, "E"): "lee",
            (6, "A"): "TC-3", (6, "B"): "FPT",
            (6, "C"): "対象外", (6, "D"): "2026-08-05", (6, "E"): "lee",
        }},
    )
    client.post("/api/load", json={"folder": str(tmp_path)})
    client.put("/api/plan/2026-08-05", json={"entries": [
        {"pic": "lee", "file": "TC.xlsx", "device": "iPhone", "planned": 4}]})
    return client


def test_productivity_is_served_with_the_plan_beside_it(loaded):
    body = loaded.get("/api/member/productivity").get_json()
    lee = body["rows"][0]
    assert (lee["executed"], lee["Cancel"], lee["planned"]) == (2, 1, 4)
    assert lee["attainment"] == 0.75
    assert body["through"] == "2026-08-05"


def test_totals_measure_each_member_against_the_plan(loaded):
    body = loaded.get("/api/member/totals").get_json()
    lee = body["members"][0]
    assert (lee["pic"], lee["planned"], lee["actual"], lee["delta"]) == ("lee", 4, 3, -1)
    assert body["team"]["actual"] == 3


def test_weeks_list_the_week_that_holds_the_work(loaded):
    body = loaded.get("/api/member/weeks").get_json()
    assert "2026-08-03" in [w["start"] for w in body["weeks"]]


def test_a_week_serves_its_cells(loaded):
    body = loaded.get("/api/member/week/2026-08-03").get_json()
    cell = body["cells"]["lee"]["2026-08-05"]
    assert (cell["planned"], cell["actual"], cell["delta"]) == (4, 3, -1)
    assert cell["short"] == [{"file": "TC.xlsx", "device": "iPhone", "planned": 4, "actual": 3}]


@pytest.mark.parametrize("week", ["2026-08-04", "not-a-date"])
def test_a_week_that_is_not_a_monday_is_a_400(client, week):
    res = client.get(f"/api/member/week/{week}")
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_with_nothing_loaded_every_endpoint_answers_empty(client):
    assert client.get("/api/member/productivity").get_json()["rows"] == []
    assert client.get("/api/member/totals").get_json()["members"] == []
    assert client.get("/api/member/week/2026-08-03").get_json()["cells"] == {}


def test_the_old_productivity_endpoint_is_gone(client):
    assert client.get("/api/productivity").status_code == 404
