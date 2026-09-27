"""Snapshots in the database: what goes in comes back out, in order."""
import pytest

from tcm.domain.case import TestCase as Case
from tcm.domain.ports import Snapshot, SnapshotRepository
from tcm.infrastructure.db.bootstrap import open_database
from tcm.infrastructure.db.snapshots import SqlSnapshotRepository


@pytest.fixture
def db(tmp_path):
    return open_database(str(tmp_path / "tcm.db"))


def clock(*stamps):
    it = iter(stamps)
    return lambda: next(it)


def snap():
    cases = [
        Case("A.xlsx", "Login", "iPhone", 4, "TC-1", "FPT", "OK", "2026-09-01", "An", None, None),
        Case("A.xlsx", "Login", "iPad", 4, "TC-1", "FPT", None, None, None, None, None),
        Case("B.xlsx", "Pay", "iPhone", 9, "TC-9", "JP", "NG", "2026-09-02", "Bo", "BUG-1", "note ✓"),
    ]
    files = [
        {"file": "A.xlsx", "path": "/src/A.xlsx", "status": "ok", "cases": 2},
        {"file": "B.xlsx", "path": "/src/B.xlsx", "status": "ok", "cases": 1},
        {"file": "C.xlsx", "path": "/src/C.xlsx", "status": "error", "error": "bad TOOL_DATA"},
    ]
    return Snapshot(cases=cases, file_results=files, source={"type": "folder", "value": "/src"})


def test_it_answers_the_port():
    assert issubclass(SqlSnapshotRepository, SnapshotRepository)


def test_a_snapshot_round_trips_exactly(db):
    repo = SqlSnapshotRepository(db, now=clock("2026-09-27T14:02:00"))
    meta = repo.save(snap(), " end of day ")
    assert meta == {"id": meta["id"], "taken_at": "2026-09-27T14:02:00", "label": "end of day",
                    "source": {"type": "folder", "value": "/src"},
                    "case_count": 3, "file_count": 3}
    back = repo.load(meta["id"])
    assert back.cases == snap().cases
    assert back.file_results == snap().file_results
    assert back.source == snap().source
    assert back.origin == {"id": meta["id"], "taken_at": "2026-09-27T14:02:00", "label": "end of day"}


def test_duplicate_basenames_survive_a_round_trip(db):
    s = Snapshot(
        cases=[Case("TC.xlsx", "S", "iPhone", 1), Case("TC.xlsx", "S", "iPhone", 2)],
        file_results=[{"file": "TC.xlsx", "path": "/a/TC.xlsx", "status": "ok"},
                      {"file": "TC.xlsx", "path": "/b/TC.xlsx", "status": "ok"}],
        source={"type": "folder", "value": "/"})
    repo = SqlSnapshotRepository(db)
    back = repo.load(repo.save(s, "")["id"])
    assert back.file_results == s.file_results
    assert back.cases == s.cases


def test_a_case_whose_file_has_no_result_row_still_comes_back(db):
    s = Snapshot(cases=[Case("X.xlsx", "S", "iPhone", 1)], file_results=[], source=None)
    repo = SqlSnapshotRepository(db)
    back = repo.load(repo.save(s, "")["id"])
    assert back.cases == s.cases
    assert back.file_results == []


def test_list_is_newest_first_and_latest_is_the_newest(db):
    repo = SqlSnapshotRepository(db, now=clock("2026-09-26T09:00:00", "2026-09-27T09:00:00"))
    first = repo.save(snap(), "one")
    second = repo.save(snap(), "two")
    assert [m["label"] for m in repo.list()] == ["two", "one"]
    assert repo.latest_id() == second["id"] != first["id"]


def test_same_second_snapshots_order_by_id(db):
    repo = SqlSnapshotRepository(db, now=lambda: "2026-09-27T09:00:00")
    repo.save(snap(), "one")
    later = repo.save(snap(), "two")
    assert repo.list()[0]["label"] == "two"
    assert repo.latest_id() == later["id"]


def test_delete_removes_every_row_it_owned(db):
    repo = SqlSnapshotRepository(db)
    sid = repo.save(snap(), "")["id"]
    assert repo.delete(sid) is True
    assert repo.load(sid) is None
    assert repo.delete(sid) is False
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM test_case").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM snapshot_file").fetchone()[0] == 0


def test_an_empty_database_has_no_latest(db):
    assert SqlSnapshotRepository(db).latest_id() is None
    assert SqlSnapshotRepository(db).list() == []
