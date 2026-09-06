"""Aggregate rows -> the grid of cell values one sheet's layout asks for.

Pure and offline: everything that decides *what* gets written lives here, so the
Graph code downstream only has to decide *where*.
"""
from report.layout import RUN_DATE, SheetLayout


def build_rows(dataset_rows, layout: SheetLayout, run_date: str) -> list[list]:
    """Lay `dataset_rows` out in `layout`'s column order, stamping `run_date`.

    Args:
        dataset_rows: Row dicts from `aggregate` — keys match the layout's fields.
        layout: The destination sheet's column order.
        run_date: The day this publish represents, "YYYY-MM-DD". It is written as
            text so the publisher can compare it back exactly; a date-formatted
            column would come back from Graph as a serial number instead.

    Returns:
        One list of cell values per row, each `layout.width` long.
    """
    grid = []
    for row in dataset_rows:
        cells = []
        for column in layout.columns:
            if column.is_status:
                # A bucket that saw none of a status still owes a 0, or the row's
                # status columns would stop adding up to its total.
                cells.append(row.get(column.field, 0))
            elif column.field == RUN_DATE:
                cells.append(run_date)
            else:
                value = row.get(column.field)
                cells.append("" if value is None else value)
        grid.append(cells)
    return grid
