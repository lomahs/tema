"""The labels that locate a test case sheet's columns, driven by a JSON config.

`parser/tool_data_builder.py` reads a sheet's layout the way a person would:
it looks for "No." to find the test case number column, "結果" to find the
result column, and a cell saying "Pad" or "Phone" to find where a device's
block starts. Those labels are one team's spreadsheet vocabulary, so - like
the result taxonomy in `parser/status.py` and the scope groups in
`parser/scope.py` - they are data. A team whose sheets say "Status" instead of
"結果" edits `parser/sheet_labels.json` and nothing else.

*How* each label is matched stays in code, because it is behaviour rather than
vocabulary, and each of the three kinds needs a different rule:

- `header` labels match **exactly**. "No." must not also match a "Note" column.
- `device_keywords` match as a **substring**, case-insensitively - a device
  cell reads "Pad(Flex)" or "27系Phone", never a bare "Pad".
- `result_columns` labels match as a **prefix**, so "チケット" finds both
  "チケット" and "チケットNo." without configuring each spelling.
"""

import json
import logging
import os
from dataclasses import dataclass


log = logging.getLogger(__name__)

DEFAULT_LABELS_PATH = os.path.join(os.path.dirname(__file__), "sheet_labels.json")

# The two columns every device block on a sheet shares, as `SheetConfig` names them.
HEADER_FIELDS = ("test_no_col", "scope_col")

# The five columns each device block carries of its own, in TOOL_DATA order.
RESULT_FIELDS = ("result_col", "test_date_col", "pic_col", "ticket_id_col", "note_col")


def _keywords(raw: dict, field: str, source: str, where: str) -> tuple[str, ...]:
    values = raw.get(field)
    if not isinstance(values, list) or not values:
        raise ValueError(f"{source}: {where}.{field} must be a non-empty list")

    out = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{source}: {where}.{field} has an empty keyword")
        out.append(value.strip())

    return tuple(out)


def _positive_int(raw: dict, field: str, source: str) -> int:
    value = raw.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{source}: '{field}' must be an integer >= 1, got {value!r}")
    return value


@dataclass
class SheetLabels:
    """The vocabulary `tool_data_builder` matches sheet cells against.

    Not frozen, because `adopt` changes it in place: the Config view can edit
    these labels while the app is running, and config you can edit at runtime
    is not frozen. Nothing else writes to an instance.
    """

    header: dict[str, tuple[str, ...]]
    result_columns: dict[str, tuple[str, ...]]
    device_keywords: tuple[str, ...]
    max_header_scan_rows: int
    device_row_window: int

    @classmethod
    def load(cls, path: str = DEFAULT_LABELS_PATH) -> "SheetLabels":
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return cls.from_dict(raw, source=path)

    def adopt(self, other: "SheetLabels") -> None:
        """Become `other`, in place — see `StatusSet.adopt` for why."""
        self.__dict__.update(other.__dict__)

    @classmethod
    def from_dict(cls, raw: dict, source: str = "<dict>") -> "SheetLabels":
        header_raw = raw.get("header")
        if not isinstance(header_raw, dict):
            raise ValueError(f"{source}: 'header' must be an object")

        result_raw = raw.get("result_columns")
        if not isinstance(result_raw, dict):
            raise ValueError(f"{source}: 'result_columns' must be an object")

        # Every field is required and no extra ones are allowed: these keys are
        # SheetConfig attributes, so a typo here would surface as a missing
        # column much later, in a detection that silently found nothing.
        for name, section, fields in (
            ("header", header_raw, HEADER_FIELDS),
            ("result_columns", result_raw, RESULT_FIELDS),
        ):
            unknown = set(section) - set(fields)
            if unknown:
                raise ValueError(
                    f"{source}: '{name}' has unknown field(s) {', '.join(sorted(unknown))}; "
                    f"expected {', '.join(fields)}"
                )

            missing = set(fields) - set(section)
            if missing:
                raise ValueError(
                    f"{source}: '{name}' is missing field(s) {', '.join(sorted(missing))}"
                )

        return cls(
            header={
                f: _keywords(header_raw, f, source, "header")
                for f in HEADER_FIELDS
            },
            result_columns={
                f: _keywords(result_raw, f, source, "result_columns")
                for f in RESULT_FIELDS
            },
            device_keywords=tuple(
                k.casefold()
                for k in _keywords(raw, "device_keywords", source, "<root>")
            ),
            max_header_scan_rows=_positive_int(raw, "max_header_scan_rows", source),
            device_row_window=_positive_int(raw, "device_row_window", source),
        )

    def matches_header(self, field: str, text: str) -> bool:
        """Whether `text` is exactly one of `field`'s header labels."""

        folded = text.casefold()
        return any(folded == kw.casefold() for kw in self.header[field])

    def matches_result_column(self, field: str, text: str) -> bool:
        """Whether `text` starts with one of `field`'s result-column labels."""

        return any(text.startswith(kw) for kw in self.result_columns[field])

    def is_device(self, text: str) -> bool:
        """Whether `text` names a device (contains a device keyword)."""

        folded = text.casefold()
        return any(kw in folded for kw in self.device_keywords)


def _load_default() -> SheetLabels:
    from config import SHEET_LABELS_CONFIG

    path = SHEET_LABELS_CONFIG
    try:
        return SheetLabels.load(path)
    except Exception as e:
        if path == DEFAULT_LABELS_PATH:
            raise
        log.error("Failed to load tool data columns config '%s': %s - using defaults", path, e)
        return SheetLabels.load(DEFAULT_LABELS_PATH)


LABELS = _load_default()
