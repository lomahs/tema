"""The interfaces this application talks to the outside world through.

Each has one implementation today. The rule is that a port exists where a test
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
    """

    cases: list[TestCase] = field(default_factory=list)
    file_results: list[dict] = field(default_factory=list)
    source: Optional[dict] = None


@runtime_checkable
class CaseLoader(Protocol):
    """Reads test cases from somewhere. Excel today."""

    def load_from_folder(self, folder_path: str) -> tuple[list[TestCase], list[dict]]:
        ...

    def load_from_files(self, file_paths: list[str]) -> tuple[list[TestCase], list[dict]]:
        ...

    def find_workbooks(self, folder_path: str) -> list[str]:
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
    implements. (CLAUDE.md has long said "seven methods wide" -- it is wrong,
    and Task 15 corrects it.) Widening this means widening the fake, which is the point:
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
