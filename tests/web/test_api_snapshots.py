"""`/api/workspace` and `/api/snapshots` — keeping a load, and starting on it."""
import pytest

from tcm.web.app import create_app
from tests.conftest import config_row, write_workbook


def make_client():
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.fixture
def source(tmp_path):
    folder = tmp_path / "src"
    folder.mkdir()
    write_workbook(folder / "TC.xlsx", [config_row("Login", "iPhone", 4, 5)], {"Login": {
        (4, "A"): "TC-1", (4, "B"): "FPT", (4, "C"): "OK", (4, "D"): "2026-08-05", (4, "E"): "lee",
        (5, "A"): "TC-2", (5, "B"): "FPT",
    }})
    return str(folder)


def test_nothing_loaded_and_nothing_saved():
    c = make_client()
    assert c.get("/api/workspace").get_json()["loaded"] == 0
    assert c.get("/api/snapshots").get_json() == {"snapshots": [], "origin": None}
    assert c.post("/api/snapshots", json={}).status_code == 400


def test_a_restart_starts_on_the_latest_snapshot(source):
    c = make_client()
    c.post("/api/load", json={"folder": source})
    saved = c.post("/api/snapshots", json={"label": "day 1"})
    assert saved.status_code == 201
    sid = saved.get_json()["id"]

    again = make_client()                         # same database file
    state = again.get("/api/workspace").get_json()
    assert state["loaded"] == 2 and state["origin"]["id"] == sid
    assert again.get("/api/summary").status_code == 200


def test_open_delete_and_compare(source):
    c = make_client()
    c.post("/api/load", json={"folder": source})
    a = c.post("/api/snapshots", json={"label": "a"}).get_json()["id"]
    b = c.post("/api/snapshots", json={"label": "b"}).get_json()["id"]

    opened = c.post(f"/api/snapshots/{a}/open")
    assert opened.status_code == 200 and opened.get_json()["origin"]["label"] == "a"

    cmp = c.get(f"/api/snapshots/compare?base={a}&head={b}").get_json()
    assert cmp["base"]["id"] == a and cmp["head"]["id"] == b
    assert cmp["transitions"] == [] and cmp["unchanged"] == 2

    assert c.get("/api/snapshots/compare?base=x").status_code == 400
    assert c.delete(f"/api/snapshots/{b}").status_code == 200
    assert c.get(f"/api/snapshots/compare?base={a}&head={b}").status_code == 404
    assert c.post(f"/api/snapshots/{b}/open").status_code == 404
    assert [s["label"] for s in c.get("/api/snapshots").get_json()["snapshots"]] == ["a"]


def test_a_label_must_be_text(source):
    c = make_client()
    c.post("/api/load", json={"folder": source})
    assert c.post("/api/snapshots", json={"label": 5}).status_code == 400


def test_compare_lists_the_cases_behind_one_move(tmp_path, source):
    c = make_client()
    c.post("/api/load", json={"folder": source})
    a = c.post("/api/snapshots", json={"label": "a"}).get_json()["id"]
    write_workbook(tmp_path / "src" / "TC.xlsx", [config_row("Login", "iPhone", 4, 5)], {"Login": {
        (4, "A"): "TC-1", (4, "B"): "JP", (4, "C"): "OK", (4, "D"): "2026-08-05", (4, "E"): "lee",
        (5, "A"): "TC-2", (5, "B"): "FPT",
    }})
    c.post("/api/load", json={"folder": source})
    b = c.post("/api/snapshots", json={"label": "b"}).get_json()["id"]

    [move] = c.get(f"/api/snapshots/compare?base={a}&head={b}").get_json()["transitions"]
    assert move["plan"] == "left"
    frm, to = move["from"], move["to"]
    url = (f"/api/snapshots/compare/cases?base={a}&head={b}"
           f"&from_scope={frm['scope']}&from_status={frm['status']}"
           f"&to_scope={to['scope']}&to_status={to['status']}")
    listed = c.get(url).get_json()["cases"]
    assert [(r["row"], r["case_no"], r["base"]["scope"], r["head"]["scope"]) for r in listed] \
        == [(4, "TC-1", "FPT", "JP")]


def test_compare_cases_refuses_a_half_named_or_unknown_side(source):
    c = make_client()
    c.post("/api/load", json={"folder": source})
    a = c.post("/api/snapshots", json={"label": "a"}).get_json()["id"]
    url = f"/api/snapshots/compare/cases?base={a}&head={a}"
    assert c.get(url).status_code == 400                                   # no side at all
    assert c.get(url + "&from_scope=FPT").status_code == 400                # scope, no status
    assert c.get(url + "&to_scope=FPT&to_status=Nope").status_code == 400    # unknown status
    assert c.get(url + "&to_scope=Nope&to_status=OK").status_code == 400     # unknown scope
    assert c.get(url + "&to_scope=FPT&to_status=OK").get_json() == {"cases": []}
    assert c.get(f"/api/snapshots/compare/cases?base={a}&head=999"
                 "&to_scope=FPT&to_status=OK").status_code == 404
