"""Generate sample test case .xlsx files that the parser can read.

Usage:
    python -m tools.generate_samples --out samples/generated
    python -m tools.generate_samples --config my_config.json --files 5 --devices 3
"""
import argparse
import json
import logging
import os
import random
from datetime import date, timedelta

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from parser.excel_reader import TOOL_DATA_SHEET, TOOL_DATA_COLUMNS
from parser.status import STATUS

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "sample_config.json")

# Sheet layout: A=Test No, B=Scope, then one 5-column block per device.
SHARED_COLS = 2
BLOCK_WIDTH = 5
BLOCK_HEADERS = ["Result", "Test Date", "PIC", "Ticket ID", "Note"]
DATA_START_ROW = 4

GROUP_TITLES = [
    "normal case", "abnormal case", "boundary", "error handling",
    "permission", "offline", "migration", "performance",
]

NOTE_TEXTS = [
    "Confirmed with dev team",
    "Re-test after fix",
    "Spec changed, out of scope",
    "Blocked by environment issue",
]

DEFAULTS = {
    "seed": None,
    "file_count": 3,
    "sheets_per_file": 3,
    "devices_per_sheet": 2,
    "cases_per_sheet": {"min": 20, "max": 40},
    "pic_names": ["lee", "kim", "tanaka", "minh", "baro"],
    "file_prefix": "TC_Sample",
    "sheet_names": ["Login", "Payment", "Search", "Settings", "Profile", "Sync"],
    "device_names": ["iPhone", "iPad", "Android", "TabletA"],
    "scopes": ["FPT", "FPT (JM Support)", "JP"],
    "result_weights": {"OK": 50, "NG": 12, "NG-OK": 8, "保留": 5, "対象外": 5, "": 20},
    "missing_reason_rate": 0.25,
    "group_row_rate": 0.1,
    "date_range": ["2026-08-01", "2026-08-31"],
}

def _needs_reason(result: str) -> bool:
    """Whether a result needs a Ticket ID or Note (same rule as /api/summary)."""
    return STATUS.classify(result) in set(STATUS.needs_reason)


def load_config(path: str = DEFAULT_CONFIG_PATH) -> dict:
    """Read a JSON config, layered over `DEFAULTS`.

    Keys absent from the file keep their default, so a config only needs to
    name what it changes.

    Args:
        path: JSON config path; falsy to use `DEFAULTS` alone.

    Returns:
        The merged, validated config.
    """
    cfg = dict(DEFAULTS)
    if path:
        with open(path, encoding="utf-8") as f:
            cfg.update(json.load(f))
    return validate_config(cfg)


def validate_config(cfg: dict) -> dict:
    """Check a config and coerce its numeric fields in place.

    Called both after loading a file and after applying CLI overrides, so bad
    input is rejected before any workbook is written rather than part-way
    through.

    Returns:
        The same dict, with counts as `int` and rates as `float`.

    Raises:
        ValueError: On an out-of-range count, an inverted min/max or date
            range, an empty name pool, or non-positive result weights.
    """
    for key in ("file_count", "sheets_per_file", "devices_per_sheet"):
        if int(cfg[key]) < 1:
            raise ValueError(f"'{key}' must be >= 1, got {cfg[key]}")
        cfg[key] = int(cfg[key])

    cases = cfg["cases_per_sheet"]
    lo, hi = int(cases["min"]), int(cases["max"])
    if lo < 1:
        raise ValueError(f"'cases_per_sheet.min' must be >= 1, got {lo}")
    if lo > hi:
        raise ValueError(f"'cases_per_sheet.min' ({lo}) > 'cases_per_sheet.max' ({hi})")
    cfg["cases_per_sheet"] = {"min": lo, "max": hi}

    for key in ("pic_names", "scopes", "sheet_names", "device_names"):
        if not cfg[key]:
            raise ValueError(f"'{key}' must not be empty")

    weights = cfg["result_weights"]
    if not weights or sum(weights.values()) <= 0:
        raise ValueError("'result_weights' must have at least one positive weight")

    for key in ("missing_reason_rate", "group_row_rate"):
        rate = float(cfg[key])
        if not 0.0 <= rate <= 1.0:
            raise ValueError(f"'{key}' must be between 0 and 1, got {rate}")
        cfg[key] = rate

    start, end = (date.fromisoformat(d) for d in cfg["date_range"])
    if start > end:
        raise ValueError(f"'date_range' start ({start}) is after end ({end})")
    return cfg


def _unique_names(pool: list[str], count: int) -> list[str]:
    """Take `count` names from `pool`, adding a suffix once the pool runs out."""
    names = []
    for i in range(count):
        name = pool[i % len(pool)]
        cycle = i // len(pool)
        names.append(name if cycle == 0 else f"{name}_{cycle + 1}")
    return names


def _block_start_col(device_index: int) -> int:
    """1-based first column of a device block: C, H, M, ..."""
    return SHARED_COLS + 1 + device_index * BLOCK_WIDTH


def _random_date(rng: random.Random, date_range: list[str]) -> str:
    start, end = (date.fromisoformat(d) for d in date_range)
    return (start + timedelta(days=rng.randrange((end - start).days + 1))).isoformat()


def _device_cells(rng: random.Random, cfg: dict) -> list:
    """One device's 5 cells for a test case row: result, date, pic, ticket, note."""
    results = list(cfg["result_weights"].keys())
    weights = list(cfg["result_weights"].values())
    result = rng.choices(results, weights=weights)[0]

    if not result:
        return [None] * BLOCK_WIDTH

    test_date = _random_date(rng, cfg["date_range"])
    pic = rng.choice(cfg["pic_names"])

    ticket_id = note = None
    if _needs_reason(result) and rng.random() >= cfg["missing_reason_rate"]:
        if rng.random() < 0.7:
            ticket_id = f"BUG-{rng.randrange(1000, 9999)}"
        else:
            note = rng.choice(NOTE_TEXTS)

    return [result, test_date, pic, ticket_id, note]


def build_sheet(wb: Workbook, sheet_name: str, devices: list[str],
                rng: random.Random, cfg: dict) -> int:
    """Write one test case sheet. Returns the last row used."""
    ws = wb.create_sheet(sheet_name)

    # Row 2: sheet name + a device name above each block. Row 3: headers.
    ws.cell(row=2, column=1, value=sheet_name)
    ws.cell(row=3, column=1, value="Test No")
    ws.cell(row=3, column=2, value="Scope")
    for i, device in enumerate(devices):
        col = _block_start_col(i)
        ws.cell(row=2, column=col, value=device)
        for j, header in enumerate(BLOCK_HEADERS):
            ws.cell(row=3, column=col + j, value=header)

    case_count = rng.randint(cfg["cases_per_sheet"]["min"], cfg["cases_per_sheet"]["max"])
    row = DATA_START_ROW
    case_no = 0

    for _ in range(case_count):
        # A group row separates blocks of related cases; it holds only a title.
        if rng.random() < cfg["group_row_rate"]:
            title = f"{sheet_name} - {rng.choice(GROUP_TITLES)}"
            ws.cell(row=row, column=1, value=f"[{title}]")
            row += 1

        case_no += 1
        ws.cell(row=row, column=1, value=case_no)
        ws.cell(row=row, column=2, value=rng.choice(cfg["scopes"]))
        for i in range(len(devices)):
            col = _block_start_col(i)
            for j, value in enumerate(_device_cells(rng, cfg)):
                if value is not None:
                    ws.cell(row=row, column=col + j, value=value)
        row += 1

    return row - 1


def build_workbook(cfg: dict, rng: random.Random) -> tuple[Workbook, int]:
    """Build one workbook. Returns (workbook, total data rows across sheets)."""
    wb = Workbook()
    tool_data = wb.active
    tool_data.title = TOOL_DATA_SHEET
    tool_data.append(TOOL_DATA_COLUMNS)

    sheet_names = _unique_names(cfg["sheet_names"], cfg["sheets_per_file"])
    devices = _unique_names(cfg["device_names"], cfg["devices_per_sheet"])

    total_rows = 0
    for sheet_name in sheet_names:
        end_row = build_sheet(wb, sheet_name, devices, rng, cfg)
        total_rows += end_row - DATA_START_ROW + 1
        for i, device in enumerate(devices):
            col = _block_start_col(i)
            tool_data.append([
                sheet_name, device, DATA_START_ROW, end_row,
                "A", "B",
                *(get_column_letter(col + j) for j in range(BLOCK_WIDTH)),
            ])
    return wb, total_rows


def generate(cfg: dict, out_dir: str) -> list[str]:
    """Write `cfg["file_count"]` sample workbooks into `out_dir`.

    All files draw from one seeded `Random`, so a config with a fixed `seed`
    reproduces the whole set byte for byte.

    Returns:
        The paths written, in order.
    """
    os.makedirs(out_dir, exist_ok=True)
    rng = random.Random(cfg["seed"])
    width = max(2, len(str(cfg["file_count"])))

    paths = []
    for index in range(1, cfg["file_count"] + 1):
        wb, total_rows = build_workbook(cfg, rng)
        name = f"{cfg['file_prefix']}_{index:0{width}d}.xlsx"
        path = os.path.join(out_dir, name)
        wb.save(path)
        paths.append(path)
        log.info("%s  %d sheet(s), %d device(s), %d row(s) x device",
                 name, cfg["sheets_per_file"], cfg["devices_per_sheet"], total_rows)
    return paths


def main():
    p = argparse.ArgumentParser(description="Generate sample test case .xlsx files")
    p.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="JSON config path")
    p.add_argument("--out", default="samples/generated", help="output folder")
    p.add_argument("--seed", type=int, help="override config seed")
    p.add_argument("--files", type=int, help="number of .xlsx files")
    p.add_argument("--sheets", type=int, help="number of test case sheets per file")
    p.add_argument("--devices", type=int, help="number of devices per sheet")
    p.add_argument("--min-cases", type=int, help="min test cases per sheet")
    p.add_argument("--max-cases", type=int, help="max test cases per sheet")
    p.add_argument("--pics", help="comma-separated PIC names")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cfg = dict(load_config(args.config))
    overrides = {
        "seed": args.seed, "file_count": args.files,
        "sheets_per_file": args.sheets, "devices_per_sheet": args.devices,
    }
    cfg.update({k: v for k, v in overrides.items() if v is not None})
    if args.min_cases is not None:
        cfg["cases_per_sheet"] = {**cfg["cases_per_sheet"], "min": args.min_cases}
    if args.max_cases is not None:
        cfg["cases_per_sheet"] = {**cfg["cases_per_sheet"], "max": args.max_cases}
    if args.pics:
        cfg["pic_names"] = [n.strip() for n in args.pics.split(",") if n.strip()]
    try:
        cfg = validate_config(cfg)
    except (ValueError, KeyError) as e:
        p.error(f"invalid config: {e}")

    paths = generate(cfg, args.out)
    log.info("Done: %d file(s) -> %s", len(paths), os.path.abspath(args.out))


if __name__ == "__main__":
    main()
