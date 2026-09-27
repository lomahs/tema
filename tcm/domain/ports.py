"""The interfaces this application talks to the outside world through.

Each has one production implementation. The rule is that a port exists where a test
already needs a stand-in, or where a swap is genuinely planned -- not wherever
a boundary could be drawn. `ReportWorkbook` is the clearest case: the publisher
has been driven through a hand-written fake since it was first tested, so the
interface already existed and simply was not written down.
"""
from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

from tcm.domain.case import TestCase


@dataclass
class Snapshot:
    """One load: the cases read, and what each workbook contributed.

    Attributes:
        cases: Every case read, across every workbook.
        file_results: One `{"file", "path", "status", ...}` dict per workbook,
            including the ones that failed -- a malformed TOOL_DATA row must
            not sink the batch.
        source: What was loaded, as `{"type": "folder"|"files", "value": ...}`.
        origin: None for a live load; `{"id", "taken_at", "label"}` when the
            cases came out of a stored snapshot.
    """

    cases: list[TestCase] = field(default_factory=list)
    file_results: list[dict] = field(default_factory=list)
    source: Optional[dict] = None
    origin: Optional[dict] = None


@runtime_checkable
class CaseLoader(Protocol):
    """Reads test cases from somewhere. Excel today."""

    def load_from_folder(self, folder_path: str) -> tuple[list[TestCase], list[dict]]:
        ...

    def load_from_files(self, file_paths: list[str]) -> tuple[list[TestCase], list[dict]]:
        ...

    def find_workbooks(self, folder_path: str) -> list[str]:
        ...

    def exclude_lock_files(self, paths: list[str]) -> list[str]:
        ...


@runtime_checkable
class CaseStore(Protocol):
    """Holds the current load. In memory today; the database seam."""

    def put(self, snapshot: Snapshot) -> None:
        ...

    def get(self) -> Snapshot:
        ...


@runtime_checkable
class ReportWorkbook(Protocol):
    """The report workbook, edited in place.

    Exactly the eight methods `tests/services/test_publisher.py`'s FakeWorkbook
    implements. Widening this means widening the fake, which is the point:
    downloading the file, rewriting it and putting it back would destroy the
    charts and pivots in a hand-built report.
    """

    def worksheet_names(self) -> list[str]:
        ...

    def used_range(self, sheet: str):
        ...

    def write_values(self, sheet: str, first_row: int, first_column: int,
                     rows: list[list]) -> None:
        ...

    def delete_rows(self, sheet: str, first_row: int, count: int,
                    first_column: int, width: int) -> None:
        ...

    def table_at(self, sheet: str, header_row: int):
        ...

    def table_rows(self, table: str) -> list[tuple[int, list]]:
        ...

    def table_add_rows(self, table: str, rows: list[list]) -> None:
        ...

    def table_delete_row(self, table: str, index: int) -> None:
        ...


@runtime_checkable
class ConfigRepository(Protocol):
    """Reads and writes the editable config files.

    A write must be atomic: a half-written result_status.json does not make the
    taxonomy wrong, it stops the app booting.
    """

    def read_text(self, path: str) -> str:
        ...

    def write_text(self, path: str, text: str) -> None:
        ...


@runtime_checkable
class TokenProvider(Protocol):
    """A Microsoft Graph identity. One per process today; per user later."""

    def status(self) -> dict:
        ...

    def token(self) -> str:
        ...

    def begin_device_login(self) -> dict:
        ...

    def complete_device_login(self, flow: dict) -> dict:
        ...

    def sign_out(self) -> None:
        ...


@runtime_checkable
class FilePicker(Protocol):
    """A native folder / file dialog on the machine running the server."""

    def pick_folder(self, initial: Optional[str] = None) -> list[str]:
        ...

    def pick_files(self, initial: Optional[str] = None) -> list[str]:
        ...


@runtime_checkable
class PlanRepository(Protocol):
    """Where the test plan is kept: the active phase's days and settings.

    Per-day methods rather than a whole-document read and write, because a day
    is a row: `SqlPlanRepository` fetching one is a `WHERE date = ?` rather than
    a full load. The plan is the one thing in the app that is authored rather
    than read out of a workbook, so it is the one thing a store has to keep.

    `day` answers for a date nobody planned with an empty `DayPlan`, never None,
    so no caller has to ask whether the store had heard of the date.

    `settings` / `put_settings` hold the one record that is not per day -- the
    phase and the daily target -- and `settings` answers with the defaults when
    nothing was saved, for the same reason `day` never answers None.

    `members` is the active phase's roster; an empty list means nobody has
    made one.
    """

    def day(self, date: str):
        ...

    def days(self) -> list:
        ...

    def put_day(self, day) -> None:
        ...

    def settings(self):
        ...

    def put_settings(self, settings) -> None:
        ...

    def members(self) -> list:
        ...


@runtime_checkable
class SnapshotRepository(Protocol):
    """Saved loads. A snapshot is the cases and file results as they were read.

    `save` answers the stored snapshot's metadata --
    `{"id", "taken_at", "label", "source", "case_count", "file_count"}` -- which
    is also what each item of `list` is, newest first. `load` answers None for an
    id it does not know, and `delete` False.
    """

    def save(self, snapshot: Snapshot, label: str) -> dict:
        ...

    def list(self) -> list:
        ...

    def load(self, snapshot_id: int) -> Optional[Snapshot]:
        ...

    def delete(self, snapshot_id: int) -> bool:
        ...

    def latest_id(self) -> Optional[int]:
        ...


@runtime_checkable
class PhaseRepository(Protocol):
    """Phases, the member roster, and which phase is active.

    An unknown id raises `tcm.domain.phase.NotFound`; a rule broken -- a
    duplicate name, the last phase, a member still planned -- raises ValueError.
    """

    def phases(self) -> list:
        ...

    def phase(self, phase_id: int):
        ...

    def create(self, phase):
        ...

    def update(self, phase):
        ...

    def delete(self, phase_id: int) -> None:
        ...

    def active_id(self) -> int:
        ...

    def set_active(self, phase_id: int) -> None:
        ...

    def members(self) -> list:
        ...

    def add_member(self, name: str):
        ...

    def delete_member(self, member_id: int) -> None:
        ...
