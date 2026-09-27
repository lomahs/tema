"""Snapshots: a load, kept.

A test case is stored as the raw cells it was read from and never as a status,
so an old snapshot re-classifies with whatever the taxonomy says today.

Cases hang off the file they came from. A case names its file by basename only,
so when two subfolders both hold a `TC.xlsx` the cases go under the first of
them -- they come back with the same `file_name` either way, which is all a
`TestCase` records. A case naming a file no load result describes gets a row
with `position = -1`, which `load` does not report as a file result.
"""
import json
from typing import Optional

from tcm.domain.case import TestCase
from tcm.domain.ports import Snapshot
from tcm.infrastructure.db.database import now_iso

_CASE_FIELDS = ("sheet", "device", "row_num", "case_no", "scope", "result",
                "test_date", "pic", "ticket_id", "note")


def _meta(row) -> dict:
    return {"id": row["id"], "taken_at": row["taken_at"], "label": row["label"],
            "source": json.loads(row["source"]) if row["source"] else None,
            "case_count": row["case_count"], "file_count": row["file_count"]}


class SqlSnapshotRepository:
    """Snapshots in the SQLite database."""

    def __init__(self, db, now=now_iso):
        self._db = db
        self._now = now

    def save(self, snapshot: Snapshot, label: str = "") -> dict:
        label = (label or "").strip()
        with self._db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO snapshot (taken_at, label, source, case_count, file_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (self._now(), label,
                 json.dumps(snapshot.source, ensure_ascii=False) if snapshot.source else None,
                 len(snapshot.cases), len(snapshot.file_results)))
            sid = cur.lastrowid

            file_ids = {}
            for pos, fr in enumerate(snapshot.file_results):
                c = conn.execute(
                    "INSERT INTO snapshot_file (snapshot_id, position, file, path, status, result) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (sid, pos, fr.get("file") or "", fr.get("path"), fr.get("status") or "",
                     json.dumps(fr, ensure_ascii=False)))
                file_ids.setdefault(fr.get("file"), c.lastrowid)
            for case in snapshot.cases:
                if case.file_name not in file_ids:
                    c = conn.execute(
                        "INSERT INTO snapshot_file (snapshot_id, position, file, status) "
                        "VALUES (?, -1, ?, '')", (sid, case.file_name))
                    file_ids[case.file_name] = c.lastrowid

            conn.executemany(
                "INSERT INTO test_case (snapshot_file_id, position, " + ", ".join(_CASE_FIELDS)
                + ") VALUES (?, ?" + ", ?" * len(_CASE_FIELDS) + ")",
                ((file_ids[c.file_name], i, *(getattr(c, f) for f in _CASE_FIELDS))
                 for i, c in enumerate(snapshot.cases)))
            row = conn.execute("SELECT * FROM snapshot WHERE id = ?", (sid,)).fetchone()
        return _meta(row)

    def list(self) -> list:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM snapshot ORDER BY taken_at DESC, id DESC").fetchall()
        return [_meta(r) for r in rows]

    def load(self, snapshot_id: int) -> Optional[Snapshot]:
        with self._db.connect() as conn:
            row = conn.execute("SELECT * FROM snapshot WHERE id = ?", (snapshot_id,)).fetchone()
            if row is None:
                return None
            files = conn.execute(
                "SELECT id, position, file, result FROM snapshot_file "
                "WHERE snapshot_id = ? ORDER BY position, id", (snapshot_id,)).fetchall()
            cases = conn.execute(
                "SELECT tc.* FROM test_case tc JOIN snapshot_file f ON f.id = tc.snapshot_file_id "
                "WHERE f.snapshot_id = ? ORDER BY tc.position", (snapshot_id,)).fetchall()
        names = {f["id"]: f["file"] for f in files}
        meta = _meta(row)
        return Snapshot(
            cases=[TestCase(file_name=names[r["snapshot_file_id"]],
                            **{f: r[f] for f in _CASE_FIELDS}) for r in cases],
            file_results=[json.loads(f["result"]) for f in files if f["position"] >= 0],
            source=meta["source"],
            origin={"id": meta["id"], "taken_at": meta["taken_at"], "label": meta["label"]},
        )

    def delete(self, snapshot_id: int) -> bool:
        with self._db.connect() as conn:
            return conn.execute("DELETE FROM snapshot WHERE id = ?",
                                (snapshot_id,)).rowcount > 0

    def latest_id(self) -> Optional[int]:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT id FROM snapshot ORDER BY taken_at DESC, id DESC LIMIT 1").fetchone()
        return row["id"] if row else None
