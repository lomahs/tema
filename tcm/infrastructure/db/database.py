"""One SQLite file, opened a connection per unit of work.

A connection per call rather than one shared: Flask's dev server is threaded,
and a `sqlite3.Connection` belongs to the thread that made it. Opening one is
cheap next to anything the app does with it.
"""
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from tcm.infrastructure.db.schema import MIGRATIONS

log = logging.getLogger(__name__)


def now_iso() -> str:
    """The local time to the second, the way every timestamp here is written."""
    return datetime.now().isoformat(timespec="seconds")


class Database:
    """The database file at `path`."""

    def __init__(self, path: str):
        self.path = path

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        # Off by default in SQLite, per connection -- and every cascade and
        # RESTRICT in the schema depends on it.
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def connect(self):
        """A connection that commits when the block succeeds and rolls back when it raises."""
        conn = self._open()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def version(self) -> int:
        with self.connect() as conn:
            return conn.execute("PRAGMA user_version").fetchone()[0]

    def backup(self, dest: str) -> None:
        """Copy the database with SQLite's online backup, safe while it is open."""
        src, dst = self._open(), sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()

    def migrate(self) -> None:
        """Bring the schema up to date, backing up a database that already had one.

        Each migration runs in its own transaction together with the version
        bump, so a failure leaves the file at the last version that succeeded.
        """
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        current, target = self.version(), len(MIGRATIONS)
        if current > target:
            raise RuntimeError(
                f"{self.path} is schema version {current}, newer than this app "
                f"understands ({target}) -- was it written by a later version?")
        if current == target:
            return
        if current > 0:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            dest = f"{self.path}.v{current}-{stamp}.bak"
            self.backup(dest)
            log.info("Backed up %s to %s before migrating", self.path, dest)

        conn = self._open()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            for version in range(current, target):
                try:
                    conn.executescript(
                        "BEGIN;\n" + MIGRATIONS[version]
                        + f"\nPRAGMA user_version = {version + 1};\nCOMMIT;")
                except Exception:
                    if conn.in_transaction:
                        conn.rollback()
                    raise
        finally:
            conn.close()
