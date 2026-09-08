from datetime import datetime

import pytest

from api import routes
from app import create_app
from parser.scope import SCOPES
from parser.status import STATUS
from tests.conftest import config_row, write_workbook


@pytest.fixture
def client():
    app = create_app()
    app.config.update(TESTING=True)
    routes._data.update({"cases": [], "file_results": [], "source": None})
    with app.test_client() as c:
        yield c


@pytest.fixture
def workbook_dir(tmp_path):
    """One sheet, two devices, covering every interesting result shape."""
    write_workbook(
        tmp_path / "TC.xlsx",
        [
            config_row("Login", "iPhone", 4, 8, cols="A B C D E F G"),
            config_row("Login", "iPad", 4, 8, cols="A B H I J K L"),
        ],
        {"Login": {
            # iPhone: OK, NG with a ticket, NG without one, an unknown result, blank
            (4, "A"): "TC-1", (4, "C"): "OK", (4, "D"): datetime(2026, 8, 5), (4, "E"): "lee",
            (5, "A"): "TC-2", (5, "C"): "NG", (5, "D"): "2026-08-05 00:00:00", (5, "E"): "lee",
            (5, "F"): "BUG-1",
            (6, "A"): "TC-3", (6, "C"): "NG", (6, "D"): "2026-08-05", (6, "E"): "lee",
            (7, "A"): "TC-4", (7, "C"): "TBD", (7, "D"): "2026-08-06", (7, "E"): "kim",
            (8, "A"): "TC-5",
            # iPad
            (4, "H"): "保留", (4, "I"): "2026-08-05", (4, "J"): "kim", (4, "K"): "BUG-2",
            (5, "H"): "OK", (5, "I"): "2026-08-05", (5, "J"): "kim",
        }},
    )
    return str(tmp_path)


@pytest.fixture
def out_of_scope_dir(tmp_path):
    """Two cases reading 対象外, separated only by whether a PIC owns them."""
    write_workbook(
        tmp_path / "OOS.xlsx",
        [config_row("Login", "iPhone", 4, 6, cols="A B C D E F G")],
        {"Login": {
            (4, "A"): "TC-1", (4, "C"): "OK", (4, "D"): "2026-08-05", (4, "E"): "lee",
            # owned: a decision someone made, and still owing a reason
            (5, "A"): "TC-2", (5, "C"): "対象外", (5, "D"): "2026-08-05", (5, "E"): "lee",
            # unowned: never in the plan
            (6, "A"): "TC-3", (6, "C"): "対象外", (6, "D"): "2026-08-05",
        }},
    )
    return str(tmp_path)


@pytest.fixture
def productivity_dir(tmp_path):
    """One PIC over several days, plus the rows productivity must leave out."""
    write_workbook(
        tmp_path / "Perf.xlsx",
        [config_row("Perf", "iPhone", 4, 11)],
        {"Perf": {
            # alice: 2 executed cases on 08-03, 3 on 08-04 -> 5 over 2 days
            (4, "A"): "TC-1", (4, "C"): "OK", (4, "D"): "2026-08-03", (4, "E"): "alice",
            (5, "A"): "TC-2", (5, "C"): "NG", (5, "D"): "2026-08-03", (5, "E"): "alice",
            (6, "A"): "TC-3", (6, "C"): "NG-OK", (6, "D"): "2026-08-04", (6, "E"): "alice",
            (7, "A"): "TC-4", (7, "C"): "OK", (7, "D"): "2026-08-04", (7, "E"): "alice",
            (8, "A"): "TC-5", (8, "C"): "OK", (8, "D"): "2026-08-04", (8, "E"): "alice",
            # 08-05 holds nothing but a Pending, so it is not a working day
            (9, "A"): "TC-6", (9, "C"): "保留", (9, "D"): "2026-08-05", (9, "E"): "alice",
            # executed, but undated: countable to no day, so counted nowhere
            (10, "A"): "TC-7", (10, "C"): "OK", (10, "E"): "alice",
            # nobody owns this one
            (11, "A"): "TC-8", (11, "C"): "OK", (11, "D"): "2026-08-03",
        }},
    )
    return str(tmp_path)


def load(client, folder):
    res = client.post("/api/load", json={"folder": folder})
    assert res.status_code == 200, res.get_json()
    return res.get_json()


def test_statuses_endpoint_mirrors_the_config(client):
    body = client.get("/api/statuses").get_json()
    assert [s["key"] for s in body["statuses"]] == STATUS.keys
    assert body["needs_reason"] == STATUS.needs_reason
    assert body["executed"] == STATUS.executed
    assert body["excluded"] == STATUS.excluded
    assert body["review"] == STATUS.review
    assert all({"key", "label", "badge", "text", "tone"} <= set(s) for s in body["statuses"])


def test_reload_before_any_load_is_rejected(client):
    res = client.post("/api/reload")
    assert res.status_code == 400
    assert "No data loaded" in res.get_json()["error"]


def test_load_rejects_a_missing_folder(client):
    res = client.post("/api/load", json={"folder": "/nope/not/here"})
    assert res.status_code == 400
    assert routes._data["source"] is None, "a failed load must not become the reload source"


def test_load_without_a_source_is_rejected(client):
    assert client.post("/api/load", json={}).status_code == 400


# --- /api/browse -----------------------------------------------------------
# The OS dialog is stubbed; `tests/test_filedialog.py` covers the dialog itself.

def test_browse_returns_the_folder_the_user_picked(client, monkeypatch):
    monkeypatch.setattr(routes, "pick_folder", lambda initial=None: ["/data/project1"])
    res = client.post("/api/browse", json={"mode": "folder"})
    assert res.status_code == 200
    assert res.get_json()["paths"] == ["/data/project1"]


def test_browse_returns_every_file_the_user_picked(client, monkeypatch):
    picked = ["/data/TC one.xlsx", "/data/TC two.xlsx"]
    monkeypatch.setattr(routes, "pick_files", lambda initial=None: list(picked))
    res = client.post("/api/browse", json={"mode": "files"})
    assert res.status_code == 200
    assert res.get_json()["paths"] == picked


def test_browse_passes_the_current_input_as_the_starting_directory(client, monkeypatch):
    seen = {}

    def fake_pick(initial=None):
        seen["initial"] = initial
        return []

    monkeypatch.setattr(routes, "pick_folder", fake_pick)
    client.post("/api/browse", json={"mode": "folder", "initial": "/data/last-used"})
    assert seen["initial"] == "/data/last-used"


def test_a_cancelled_browse_is_not_an_error(client, monkeypatch):
    monkeypatch.setattr(routes, "pick_folder", lambda initial=None: [])
    res = client.post("/api/browse", json={"mode": "folder"})
    assert res.status_code == 200
    assert res.get_json()["paths"] == []


def test_browse_rejects_an_unknown_mode(client):
    res = client.post("/api/browse", json={"mode": "sideways"})
    assert res.status_code == 400


def test_browse_reports_a_dialog_that_cannot_open(client, monkeypatch):
    def boom(initial=None):
        raise routes.DialogError("tkinter unavailable")

    monkeypatch.setattr(routes, "pick_folder", boom)
    res = client.post("/api/browse", json={"mode": "folder"})
    assert res.status_code == 500
    assert "tkinter unavailable" in res.get_json()["error"]


def test_browsing_does_not_disturb_the_loaded_source(client, workbook_dir, monkeypatch):
    """Browse only fills in the input; loading stays an explicit second step."""
    load(client, workbook_dir)
    monkeypatch.setattr(routes, "pick_folder", lambda initial=None: ["/data/elsewhere"])

    client.post("/api/browse", json={"mode": "folder"})

    assert routes._data["source"] == {"type": "folder", "value": workbook_dir}


def test_data_carries_a_server_computed_status(client, workbook_dir):
    load(client, workbook_dir)
    cases = client.get("/api/data").get_json()
    by_case = {(c["device"], c["case_no"]): c["status"] for c in cases}

    assert by_case[("iPhone", "TC-1")] == "OK"
    assert by_case[("iPhone", "TC-2")] == "NG"
    assert by_case[("iPhone", "TC-4")] == "Other"     # unrecognised result
    assert by_case[("iPhone", "TC-5")] == "NYS"       # blank result
    assert by_case[("iPad", "TC-1")] == "Pending"


def test_summary_totals_reconcile_including_unknown_results(client, workbook_dir):
    load(client, workbook_dir)
    body = client.get("/api/summary").get_json()

    assert body["groups"], "expected at least one group"
    for group in body["groups"]:
        assert set(STATUS.keys) <= set(group), "every status must be a column"
        assert sum(group[key] for key in STATUS.counted) == group["total"]

    iphone = next(g for g in body["groups"] if g["device"] == "iPhone")
    assert iphone["OK"] == 1 and iphone["NG"] == 2
    assert iphone["Other"] == 1, "TBD must land in the fallback bucket, not vanish"
    assert iphone["NYS"] == 1


def test_summary_flags_only_cases_that_need_a_reason_and_lack_one(client, workbook_dir):
    load(client, workbook_dir)
    body = client.get("/api/summary").get_json()
    flagged = {(m["device"], m["case_no"]) for m in body["missing_reason"]}

    assert ("iPhone", "TC-3") in flagged      # NG, no ticket and no note
    assert ("iPhone", "TC-4") in flagged      # Other is in needs_reason
    assert ("iPhone", "TC-2") not in flagged  # NG but has BUG-1
    assert ("iPhone", "TC-1") not in flagged  # OK
    assert ("iPhone", "TC-5") not in flagged  # not yet started
    assert ("iPad", "TC-1") not in flagged    # Pending but has BUG-2


def test_daily_groups_real_and_text_dates_onto_the_same_day(client, workbook_dir):
    load(client, workbook_dir)
    rows = client.get("/api/daily").get_json()

    same_day = [r for r in rows
                if r["device"] == "iPhone" and r["pic"] == "lee" and r["date"] == "2026-08-05"]
    assert len(same_day) == 1, "a datetime cell and a text date must not split the day"
    assert same_day[0]["total"] == 3
    assert same_day[0]["OK"] == 1 and same_day[0]["NG"] == 2


def test_daily_rows_reconcile_and_skip_cases_without_a_date(client, workbook_dir):
    load(client, workbook_dir)
    rows = client.get("/api/daily").get_json()

    for row in rows:
        assert sum(row[key] for key in STATUS.counted) == row["total"]
    # TC-5 has no date at all, so it appears nowhere in the daily view.
    assert sum(r["total"] for r in rows) == 6


# --- /api/productivity -----------------------------------------------------

def rows_by_pic(client):
    return {r["pic"]: r for r in client.get("/api/productivity").get_json()}


def test_productivity_is_executed_cases_over_working_days(client, productivity_dir):
    load(client, productivity_dir)
    alice = rows_by_pic(client)["alice"]

    assert alice["executed"] == 5
    assert alice["days"] == 2
    assert alice["productivity"] == 2.5


def test_productivity_breaks_the_executed_total_down_by_status(client, productivity_dir):
    load(client, productivity_dir)
    alice = rows_by_pic(client)["alice"]

    assert alice["OK"] == 3 and alice["NG"] == 1 and alice["NG-OK"] == 1
    assert sum(alice[key] for key in STATUS.executed) == alice["executed"]


def test_a_day_with_no_executed_case_is_not_a_working_day(client, productivity_dir):
    """alice logged a Pending on 08-05; that must not dilute her rate."""
    load(client, productivity_dir)
    assert rows_by_pic(client)["alice"]["days"] == 2


def test_productivity_skips_cases_without_a_date(client, productivity_dir):
    """TC-7 is an OK with no date — it belongs to no day, so it counts to none."""
    load(client, productivity_dir)
    assert rows_by_pic(client)["alice"]["executed"] == 5


def test_productivity_gathers_unassigned_cases_under_one_label(client, productivity_dir):
    load(client, productivity_dir)
    unassigned = rows_by_pic(client)["N/A"]
    assert unassigned["executed"] == 1 and unassigned["days"] == 1


def test_productivity_ignores_statuses_that_are_not_work_done(client, workbook_dir):
    """kim has a Pending, an unrecognised result and one OK: only the OK counts."""
    load(client, workbook_dir)
    kim = rows_by_pic(client)["kim"]

    assert kim["executed"] == 1
    assert kim["days"] == 1
    assert kim["productivity"] == 1.0


def test_a_pic_with_no_executed_case_reports_zero_instead_of_dividing(client, tmp_path):
    write_workbook(
        tmp_path / "Pending.xlsx",
        [config_row("S", "iPhone", 4, 4)],
        {"S": {(4, "A"): "TC-1", (4, "C"): "保留", (4, "D"): "2026-08-03", (4, "E"): "bob"}},
    )
    load(client, str(tmp_path))
    bob = rows_by_pic(client)["bob"]

    assert bob["days"] == 0
    assert bob["productivity"] == 0


def test_reload_reuses_the_remembered_source(client, workbook_dir):
    first = load(client, workbook_dir)
    res = client.post("/api/reload")
    assert res.status_code == 200
    assert res.get_json()["loaded"] == first["loaded"]


def test_empty_store_returns_empty_aggregates(client):
    assert client.get("/api/data").get_json() == []
    assert client.get("/api/daily").get_json() == []
    assert client.get("/api/productivity").get_json() == []
    body = client.get("/api/summary").get_json()
    assert body["groups"] == [] and body["missing_reason"] == []
    # The scope groups describe the tables, not the data, so they are served
    # even with nothing loaded — the view draws its empty state from them.
    assert [g["key"] for g in body["scopes"]] == SCOPES.keys


def test_missing_reason_rows_carry_their_status(client, workbook_dir):
    """The UI colours these rows from the taxonomy, so it needs the status key.

    Re-deriving it in JavaScript would mean naming status keys there, which the
    taxonomy exists to keep in one place.
    """
    load(client, workbook_dir)
    rows = client.get("/api/summary").get_json()["missing_reason"]
    assert rows, "fixture should produce at least one case owing a reason"
    assert all(r["status"] in STATUS.keys for r in rows)
    by_case = {r["case_no"]: r["status"] for r in rows}
    assert by_case["TC-3"] == "NG"
    assert by_case["TC-4"] == "Other"


# --- Out Of Scope, end to end ---------------------------------------------

def test_an_unowned_cancel_is_reported_as_out_of_scope(client, out_of_scope_dir):
    load(client, out_of_scope_dir)
    by_case = {c["case_no"]: c["status"] for c in client.get("/api/data").get_json()}

    assert by_case["TC-2"] == "Cancel"
    assert by_case["TC-3"] == "OOS"


def test_summary_shows_out_of_scope_without_counting_it(client, out_of_scope_dir):
    load(client, out_of_scope_dir)
    group = client.get("/api/summary").get_json()["groups"][0]

    assert group["OOS"] == 1 and group["Cancel"] == 1
    assert group["total"] == 2, "three cases loaded, one of them out of scope"
    assert sum(group[key] for key in STATUS.counted) == group["total"]


def test_an_unowned_cancel_is_not_a_missing_reason(client, out_of_scope_dir):
    load(client, out_of_scope_dir)
    flagged = {m["case_no"] for m in client.get("/api/summary").get_json()["missing_reason"]}

    assert "TC-2" in flagged, "an owned Cancel still owes a ticket or a note"
    assert "TC-3" not in flagged


# --- Summary split by scope ------------------------------------------------

@pytest.fixture
def scoped_dir(tmp_path):
    """One device carrying all three scope groups, including a blank Scope."""
    write_workbook(
        tmp_path / "Scoped.xlsx",
        [config_row("Login", "iPhone", 4, 8, cols="A B C D E F G")],
        {"Login": {
            (4, "A"): "TC-1", (4, "B"): "FPT", (4, "C"): "OK",
            (4, "D"): "2026-08-05", (4, "E"): "lee",
            (5, "A"): "TC-2", (5, "B"): "FPT (JM Support)", (5, "C"): "NG",
            (5, "D"): "2026-08-05", (5, "E"): "lee", (5, "F"): "BUG-1",
            (6, "A"): "TC-3", (6, "B"): "JP", (6, "C"): "OK",
            (6, "D"): "2026-08-05", (6, "E"): "kim",
            (7, "A"): "TC-4", (7, "B"): "Vendor", (7, "C"): "OK",
            (7, "D"): "2026-08-05", (7, "E"): "kim",
            # No Scope at all — a spreadsheet section heading.
            (8, "A"): "[Login - normal case]",
        }},
    )
    return str(tmp_path)


def test_summary_rows_carry_the_scope_group_they_belong_to(client, scoped_dir):
    load(client, scoped_dir)
    rows = client.get("/api/summary").get_json()["groups"]

    assert {r["scope"]: r["total"] for r in rows} == {"FPT": 2, "JP": 1, "Other": 2}


def test_the_two_fpt_scopes_share_one_table(client, scoped_dir):
    """FPT and FPT (JM Support) are one commitment, reported together."""
    load(client, scoped_dir)
    fpt = next(r for r in client.get("/api/summary").get_json()["groups"]
               if r["scope"] == "FPT")

    assert fpt["OK"] == 1 and fpt["NG"] == 1


def test_the_scope_tables_account_for_every_loaded_case(client, scoped_dir):
    load(client, scoped_dir)
    body = client.get("/api/summary").get_json()

    counted = sum(r["total"] for r in body["groups"])
    excluded = sum(r[k] for r in body["groups"] for k in STATUS.excluded)
    assert counted + excluded == len(client.get("/api/data").get_json())


def test_the_scope_group_list_is_served_for_the_view_to_title_its_tables(client, scoped_dir):
    load(client, scoped_dir)
    body = client.get("/api/summary").get_json()

    assert [g["key"] for g in body["scopes"]] == SCOPES.keys
    assert all(g["label"] for g in body["scopes"])


def test_missing_reason_survives_the_scope_split(client, scoped_dir):
    """Kept in the payload though Summary no longer draws it."""
    load(client, scoped_dir)
    body = client.get("/api/summary").get_json()

    assert "missing_reason" in body
