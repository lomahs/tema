"""Turning aggregate rows into the cell grid a sheet's layout asks for."""
from report.builder import build_rows
from report.layout import ReportLayout


def sheet_layout(dataset, columns, **overrides):
    cfg = {"sheets": [{
        "dataset": dataset, "sheet": "S", "header_row": 1, "first_column": "A",
        "columns": columns, **overrides,
    }]}
    return ReportLayout.from_dict(cfg).sheets[0]


def test_values_come_out_in_the_declared_column_order():
    layout = sheet_layout("summary", [
        {"field": "device"}, {"field": "run_date"}, {"field": "file"},
    ])

    rows = build_rows(
        [{"file": "TC.xlsx", "device": "iPhone", "total": 3}],
        layout, run_date="2026-09-06",
    )

    assert rows == [["iPhone", "2026-09-06", "TC.xlsx"]]


def test_the_run_date_is_stamped_on_every_row():
    layout = sheet_layout("summary", [{"field": "run_date"}, {"field": "file"}])

    rows = build_rows(
        [{"file": "a.xlsx"}, {"file": "b.xlsx"}], layout, run_date="2026-09-06",
    )

    assert [r[0] for r in rows] == ["2026-09-06", "2026-09-06"]


def test_status_columns_carry_the_counts_in_taxonomy_order():
    from parser.status import STATUS

    layout = sheet_layout("summary", [{"field": "run_date"}, {"expand": "statuses"}])
    counts = {**STATUS.zero_counts(), "OK": 5, "NG": 2}

    rows = build_rows([{"file": "TC.xlsx", **counts}], layout, run_date="2026-09-06")

    assert rows[0][1:] == [counts[key] for key in STATUS.counted]


def test_a_missing_status_count_is_written_as_zero_not_blank():
    """Totals must still reconcile if an aggregate row ever omits a key."""
    layout = sheet_layout("summary", [{"field": "run_date"}, {"expand": "statuses"}])

    rows = build_rows([{"file": "TC.xlsx"}], layout, run_date="2026-09-06")

    assert set(rows[0][1:]) == {0}


def test_empty_cells_are_written_as_blanks_rather_than_the_word_none():
    layout = sheet_layout("issues", [
        {"field": "run_date"}, {"field": "ticket_id"}, {"field": "note"},
    ])

    rows = build_rows([{"ticket_id": None, "note": None}], layout, run_date="2026-09-06")

    assert rows == [["2026-09-06", "", ""]]


def test_a_field_absent_from_the_row_becomes_a_blank():
    layout = sheet_layout("issues", [{"field": "run_date"}, {"field": "scope"}])

    assert build_rows([{}], layout, run_date="2026-09-06") == [["2026-09-06", ""]]


def test_numbers_stay_numbers_so_excel_can_total_them():
    layout = sheet_layout("issues", [{"field": "run_date"}, {"field": "row"}])

    rows = build_rows([{"row": 7}], layout, run_date="2026-09-06")

    assert rows[0][1] == 7 and isinstance(rows[0][1], int)


def test_no_aggregate_rows_means_no_cells_to_write():
    layout = sheet_layout("summary", [{"field": "run_date"}, {"field": "file"}])

    assert build_rows([], layout, run_date="2026-09-06") == []
