"""Give a workbook the TOOL_DATA sheet the reader needs, or check the one it has.

`tcm.infrastructure.excel.detection` works out where a sheet keeps its test
numbers, scopes and per-device result columns. This module is the workbook end
of that: it runs the detection over a file, writes the result in as a TOOL_DATA
sheet, and — once a workbook already has one — compares the two so a person can
see what detection would change before allowing it.

The comparison is what makes re-running safe. A TOOL_DATA sheet someone
corrected by hand is the authority on that workbook; detection is a best-effort
first pass. So nothing here overwrites without being asked twice.
"""

from dataclasses import dataclass, field

from openpyxl import load_workbook

from tcm.infrastructure.excel.reader import TOOL_DATA_COLUMNS, TOOL_DATA_SHEET
from tcm.domain.case import SheetConfig
from tcm.infrastructure.excel.detection import Unresolved, detect_workbook_configs
from tcm.infrastructure.excel.workbook import read_sheets


#: The SheetConfig fields a diff compares — everything but the two that
#: identify the block, which is what the blocks are matched on.
COMPARED_FIELDS = tuple(f for f in TOOL_DATA_COLUMNS if f not in ("sheet", "device"))


def detect_file(path: str) -> tuple[list[SheetConfig], list[Unresolved]]:
    """Detect TOOL_DATA rows for one workbook on disk."""

    return detect_workbook_configs(read_sheets(path))


def write_tool_data_sheet(path: str, configs: list[SheetConfig],
                          out_path: str | None = None) -> str:
    """Replace (or add) the TOOL_DATA sheet, leaving every other sheet alone.

    Loaded without `data_only`, so the test case sheets keep their formulas,
    formatting and charts — only TOOL_DATA is rewritten.
    """

    wb = load_workbook(path)
    try:
        if TOOL_DATA_SHEET in wb.sheetnames:
            del wb[TOOL_DATA_SHEET]
        ws = wb.create_sheet(TOOL_DATA_SHEET)
        ws.append(TOOL_DATA_COLUMNS)
        for cfg in configs:
            ws.append([getattr(cfg, name) for name in TOOL_DATA_COLUMNS])

        dest = out_path or path
        wb.save(dest)
    finally:
        wb.close()

    return dest


@dataclass
class ConfigDiff:
    """What detection would change about a TOOL_DATA sheet that already exists.

    Blocks are matched on `(sheet, device)` — the pair that names one device's
    column block — so a block whose columns moved shows up as `changed`, while
    one that was added or dropped shows up on its own list.
    """

    same: list[tuple[str, str]] = field(default_factory=list)
    changed: list[dict] = field(default_factory=list)
    only_existing: list[tuple[str, str]] = field(default_factory=list)
    only_detected: list[tuple[str, str]] = field(default_factory=list)

    @property
    def differs(self) -> bool:
        """Whether anything at all would change."""
        return bool(self.changed or self.only_existing or self.only_detected)

    def to_dict(self) -> dict:
        return {
            "differs": self.differs,
            "same": [{"sheet": s, "device": d} for s, d in self.same],
            "changed": self.changed,
            "only_existing": [{"sheet": s, "device": d} for s, d in self.only_existing],
            "only_detected": [{"sheet": s, "device": d} for s, d in self.only_detected],
        }


def diff_configs(existing: list[SheetConfig],
                 detected: list[SheetConfig]) -> ConfigDiff:
    """Compare a workbook's own TOOL_DATA rows against freshly detected ones."""

    def key(cfg):
        return (cfg.sheet, cfg.device)

    have = {key(c): c for c in existing}
    found = {key(c): c for c in detected}

    diff = ConfigDiff()

    # Existing order first: it is the order a person reading the sheet expects.
    for k, mine in have.items():
        theirs = found.get(k)
        if theirs is None:
            diff.only_existing.append(k)
            continue

        fields = [
            {"field": name,
             "existing": getattr(mine, name),
             "detected": getattr(theirs, name)}
            for name in COMPARED_FIELDS
            if getattr(mine, name) != getattr(theirs, name)
        ]
        if fields:
            diff.changed.append({"sheet": k[0], "device": k[1], "fields": fields})
        else:
            diff.same.append(k)

    diff.only_detected.extend(k for k in found if k not in have)
    return diff
