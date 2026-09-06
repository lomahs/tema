"""Editing one Excel workbook in place, through Graph's workbook API.

Everything here writes to the file where it lives on SharePoint. The workbook is
never downloaded and re-uploaded, so charts, pivots, formulas and conditional
formatting in the report survive a publish untouched.

The surface is deliberately small — seven operations — because the publisher is
tested against a stand-in that implements exactly this much.
"""
import logging
from dataclasses import dataclass, field

from openpyxl.utils import get_column_letter

from sharepoint.client import GraphError
from sharepoint.links import DriveItemRef

log = logging.getLogger(__name__)

#: Rows per call. Graph rejects very large payloads, and its own guidance is to
#: batch rather than send one row at a time.
DEFAULT_CHUNK_SIZE = 500

#: Error codes Graph uses when a persistent session has aged out. A session goes
#: stale after a few idle minutes, which a long publish can easily reach.
SESSION_GONE_CODES = {"invalidsessionid", "sessionnotfound", "invalidsession"}


@dataclass(frozen=True)
class UsedRange:
    """The smallest rectangle of a sheet that holds anything."""

    row_index: int          # 0-based, as Graph reports it
    column_index: int
    row_count: int
    column_count: int
    values: list = field(default_factory=list)

    @property
    def first_row(self) -> int:
        """1-based Excel row number of the top of the range."""
        return self.row_index + 1

    @property
    def last_row(self) -> int:
        """1-based Excel row number of the bottom of the range."""
        return self.row_index + self.row_count


class Workbook:
    """A workbook open for editing, for the duration of a `with` block.

    Args:
        client: A `GraphClient`, or anything with the same get/post/patch/delete.
        ref: Which file, from `sharepoint.links.share_url_to_item`.
        chunk_size: Rows per write call.
    """

    def __init__(self, client, ref: DriveItemRef, chunk_size: int = DEFAULT_CHUNK_SIZE):
        self._client = client
        self._ref = ref
        self._chunk_size = chunk_size
        self._session_id = None

    # --- session ----------------------------------------------------------

    @property
    def _base(self) -> str:
        return f"{self._ref.path}/workbook"

    def __enter__(self) -> "Workbook":
        self._open_session()
        return self

    def __exit__(self, exc_type, exc, tb):
        # Closing is best-effort: a session left open expires on its own, and
        # letting a close failure mask the real exception would be worse.
        try:
            self._client.post(f"{self._base}/closeSession", headers=self._headers())
        except Exception as e:
            log.warning("Could not close the workbook session: %s", e)
        self._session_id = None
        return False

    def _open_session(self):
        body = self._client.post(f"{self._base}/createSession",
                                 json={"persistChanges": True}) or {}
        self._session_id = body.get("id")

    def _headers(self):
        return {"Workbook-Session-Id": self._session_id} if self._session_id else {}

    def _call(self, method: str, path: str, **kwargs):
        """Send one call in this session, reopening the session if it has expired."""
        try:
            return self._client.request(method, path, headers=self._headers(), **kwargs)
        except GraphError as e:
            if e.status != 404 or e.code.lower() not in SESSION_GONE_CODES:
                raise
            log.info("Workbook session expired — opening a new one")
            self._open_session()
            return self._client.request(method, path, headers=self._headers(), **kwargs)

    # --- reading ----------------------------------------------------------

    def worksheet_names(self) -> list[str]:
        body = self._call("GET", f"{self._base}/worksheets?$select=name") or {}
        return [sheet["name"] for sheet in body.get("value", [])]

    def used_range(self, sheet: str) -> UsedRange:
        """The occupied rectangle of `sheet`, read by value.

        `valuesOnly=true` matters: without it a column that is merely formatted
        to the bottom of the sheet would report thousands of empty rows, and the
        append would land far below the real data.
        """
        body = self._call(
            "GET",
            f"{self._base}/worksheets('{sheet}')/usedRange(valuesOnly=true)"
            "?$select=address,rowIndex,columnIndex,rowCount,columnCount,values",
        ) or {}
        return UsedRange(
            row_index=body.get("rowIndex", 0),
            column_index=body.get("columnIndex", 0),
            row_count=body.get("rowCount", 0),
            column_count=body.get("columnCount", 0),
            values=body.get("values") or [],
        )

    # --- writing ----------------------------------------------------------

    def write_values(self, sheet: str, first_row: int, first_column: int, rows: list[list]):
        """Write `rows` starting at (`first_row`, `first_column`), in chunks."""
        for offset in range(0, len(rows), self._chunk_size):
            chunk = rows[offset:offset + self._chunk_size]
            address = _address(sheet, first_row + offset, first_column,
                               len(chunk), len(chunk[0]))
            self._call("PATCH", f"{self._base}/worksheets('{sheet}')/range(address='{address}')",
                       json={"values": chunk})

    def delete_rows(self, sheet: str, first_row: int, count: int,
                    first_column: int, width: int):
        """Remove `count` rows, pulling everything below them up."""
        if count <= 0:
            return
        address = _address(sheet, first_row, first_column, count, width)
        self._call("POST",
                   f"{self._base}/worksheets('{sheet}')/range(address='{address}')/delete",
                   json={"shift": "Up"})

    # --- tables -----------------------------------------------------------

    def table_at(self, sheet: str, header_row: int):
        """Name of the table whose header sits on `header_row`, or None.

        A real Excel table extends its own formatting and formulas over rows
        added to it, which a plain range write cannot do — so when the report
        was built with one, it is worth using.
        """
        body = self._call("GET", f"{self._base}/worksheets('{sheet}')/tables?$select=name") or {}
        for table in body.get("value", []):
            name = table["name"]
            header = self._call(
                "GET", f"{self._base}/tables('{name}')/headerRowRange?$select=rowIndex"
            ) or {}
            if header.get("rowIndex", -1) + 1 == header_row:
                return name
        return None

    def table_rows(self, table: str) -> list[tuple[int, list]]:
        """Every data row of `table`, as (index, values) — the index deletes it."""
        body = self._call("GET", f"{self._base}/tables('{table}')/rows?$select=index,values") or {}
        rows = []
        for row in body.get("value", []):
            values = row.get("values") or [[]]
            rows.append((row["index"], values[0]))
        return rows

    def table_add_rows(self, table: str, rows: list[list]):
        """Append `rows` to the end of `table`, in chunks."""
        for offset in range(0, len(rows), self._chunk_size):
            self._call("POST", f"{self._base}/tables('{table}')/rows",
                       json={"values": rows[offset:offset + self._chunk_size], "index": None})

    def table_delete_row(self, table: str, index: int):
        """Delete one row of `table` by its zero-based index."""
        self._call("DELETE", f"{self._base}/tables('{table}')/rows/{index}")


def _address(sheet: str, first_row: int, first_column: int,
             row_count: int, column_count: int) -> str:
    start = f"{get_column_letter(first_column)}{first_row}"
    end = f"{get_column_letter(first_column + column_count - 1)}{first_row + row_count - 1}"
    return f"{sheet}!{start}:{end}"
