"""The database file: opening, migrating, backing up, and the first phase."""
import sqlite3

import pytest

from tcm.infrastructure.db import database as database_module
from tcm.infrastructure.db.bootstrap import open_database
from tcm.infrastructure.db.database import Database
from tcm.infrastructure.db.schema import MIGRATIONS


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "tcm.db"))
    d.migrate()
    return d


def tables(db):
    with db.connect() as conn:
        return {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}


def test_a_fresh_file_migrates_to_the_latest_version(db):
    assert db.version() == len(MIGRATIONS)
    assert {"app_state", "member", "phase", "phase_member", "plan_day", "plan_entry",
            "snapshot", "snapshot_file", "test_case"} <= tables(db)


def test_migrate_creates_the_missing_folder(tmp_path):
    d = Database(str(tmp_path / "nested" / "deeper" / "tcm.db"))
    d.migrate()
    assert d.version() == len(MIGRATIONS)


def test_migrating_twice_is_a_no_op_and_backs_nothing_up(db, tmp_path):
    db.migrate()
    assert not list(tmp_path.glob("*.bak"))


def test_an_older_database_is_backed_up_before_migrating(db, tmp_path, monkeypatch):
    monkeypatch.setattr(database_module, "MIGRATIONS",
                        MIGRATIONS + ["CREATE TABLE extra (x INTEGER);"])
    db.migrate()
    backups = list(tmp_path.glob("tcm.db.v1-*.bak"))
    assert len(backups) == 1
    assert db.version() == len(MIGRATIONS) + 1
    # The backup is the database as it was: version 1, no `extra` table.
    old = Database(str(backups[0]))
    assert old.version() == 1
    assert "extra" not in tables(old)


def test_a_failed_migration_changes_nothing(db, monkeypatch):
    monkeypatch.setattr(database_module, "MIGRATIONS",
                        MIGRATIONS + ["CREATE TABLE ok (x); CREATE TABLE ok (x);"])
    with pytest.raises(sqlite3.OperationalError):
        db.migrate()
    assert db.version() == len(MIGRATIONS)
    assert "ok" not in tables(db)


def test_a_newer_database_is_refused(db):
    with db.connect() as conn:
        conn.execute("PRAGMA user_version = 99")
    with pytest.raises(RuntimeError, match="newer"):
        db.migrate()


def test_foreign_keys_are_enforced(db):
    with pytest.raises(sqlite3.IntegrityError):
        with db.connect() as conn:
            conn.execute("INSERT INTO phase_member (phase_id, member_id) VALUES (1, 1)")


def test_open_database_creates_phase_1_once(tmp_path):
    path = str(tmp_path / "tcm.db")
    open_database(path)
    db = open_database(path)
    with db.connect() as conn:
        rows = conn.execute("SELECT id, name FROM phase").fetchall()
        active = conn.execute(
            "SELECT value FROM app_state WHERE key = 'active_phase_id'").fetchone()
    assert [r["name"] for r in rows] == ["Phase 1"]
    assert active["value"] == str(rows[0]["id"])
