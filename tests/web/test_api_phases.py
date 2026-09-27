"""`/api/phases` and `/api/members`, and the plan following the active phase."""
import pytest

from tcm.web.app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def entry(pic="An", planned=5):
    return {"pic": pic, "file": "TC.xlsx", "device": "iPhone", "planned": planned}


def test_a_fresh_database_has_phase_1(client):
    body = client.get("/api/phases").get_json()
    assert [p["name"] for p in body["phases"]] == ["Phase 1"]
    assert body["active_id"] == body["phases"][0]["id"]


def test_create_update_activate_delete(client):
    res = client.post("/api/phases", json={"name": "Sprint 2", "members": ["An"]})
    assert res.status_code == 201
    new = [p for p in res.get_json()["phases"] if p["name"] == "Sprint 2"][0]

    res = client.put(f"/api/phases/{new['id']}", json={"name": "Sprint 2b", "daily_target": 9,
                                                       "members": ["An", "Bo"]})
    assert res.status_code == 200
    assert client.post(f"/api/phases/{new['id']}/activate").get_json()["active_id"] == new["id"]
    assert client.delete(f"/api/phases/{new['id']}").status_code == 200
    assert client.delete(f"/api/phases/{new['id']}").status_code == 404


def test_rules_come_back_as_400s(client):
    only = client.get("/api/phases").get_json()["active_id"]
    assert client.delete(f"/api/phases/{only}").status_code == 400
    assert client.post("/api/phases", json={"name": ""}).status_code == 400
    assert client.post("/api/phases", json={"name": "Phase 1"}).status_code == 400
    assert client.put("/api/phases/999", json={"name": "X"}).status_code == 404


def test_members(client):
    active = client.get("/api/phases").get_json()["active_id"]
    body = client.post("/api/members", json={"name": "An", "phase_id": active}).get_json()
    [an] = body["members"]
    assert body["phases"][0]["members"] == ["An"]
    client.put("/api/plan/2026-09-30", json={"entries": [entry("An")]})
    res = client.delete(f"/api/members/{an['id']}")
    assert res.status_code == 400 and "still planned" in res.get_json()["error"]
    assert client.delete("/api/members/999").status_code == 404
    assert client.post("/api/members", json={}).status_code == 400


def test_the_plan_follows_the_active_phase(client):
    first = client.get("/api/phases").get_json()["active_id"]
    client.put("/api/plan/2026-09-30", json={"entries": [entry(planned=7)]})
    client.put("/api/plan/settings", json={"phase_start": "2026-09-01",
                                           "phase_end": "2026-09-30", "daily_target": 11})
    body = client.post("/api/phases", json={"name": "Sprint 2", "activate": True}).get_json()
    assert body["active_id"] != first
    assert client.get("/api/plan/2026-09-30").get_json()["planned_total"] == 0
    client.post(f"/api/phases/{first}/activate")
    assert client.get("/api/plan/2026-09-30").get_json()["planned_total"] == 7
    [p1] = [p for p in client.get("/api/phases").get_json()["phases"] if p["id"] == first]
    assert (p1["phase_start"], p1["daily_target"]) == ("2026-09-01", 11)
