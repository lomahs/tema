"""Validation of report_layout.json — the file that says which column holds what."""
import json

import pytest

from report.layout import ReportLayout

MINIMAL = {
    "sheets": [
        {
            "dataset": "summary",
            "sheet": "Summary",
            "header_row": 1,
            "first_column": "A",
            "columns": [
                {"field": "run_date"},
                {"field": "file"},
                {"expand": "statuses"},
            ],
        },
    ],
}


def layout(**overrides):
    """MINIMAL with its single sheet patched, so a test names only what it changes."""
    cfg = json.loads(json.dumps(MINIMAL))
    cfg["sheets"][0].update(overrides)
    return cfg


def test_the_shipped_default_covers_all_three_datasets():
    default = ReportLayout.load()
    assert [s.dataset for s in default.sheets] == ["summary", "daily", "issues"]


def test_a_status_expansion_becomes_one_column_per_status_in_taxonomy_order():
    from parser.status import STATUS

    sheet = ReportLayout.from_dict(MINIMAL).sheets[0]

    assert [c.field for c in sheet.columns] == ["run_date", "file", *STATUS.keys]
    assert [c.is_status for c in sheet.columns] == [False, False, *[True] * len(STATUS.keys)]


def test_the_run_date_column_is_located_by_position():
    sheet = ReportLayout.from_dict(layout(columns=[
        {"field": "file"}, {"field": "run_date"}, {"field": "total"},
    ])).sheets[0]

    assert sheet.run_date_index == 1


def test_a_sheet_knows_the_excel_column_its_run_date_lands_in():
    sheet = ReportLayout.from_dict(layout(
        first_column="C",
        columns=[{"field": "file"}, {"field": "run_date"}],
    )).sheets[0]

    assert sheet.first_column == "C"
    assert sheet.run_date_column == "D"


def test_each_dataset_accepts_its_own_fields():
    cfg = {"sheets": [
        {"dataset": "daily", "sheet": "Daily", "header_row": 1, "first_column": "A",
         "columns": [{"field": "run_date"}, {"field": "date"}, {"field": "pic"}]},
        {"dataset": "issues", "sheet": "Issues", "header_row": 1, "first_column": "A",
         "columns": [{"field": "run_date"}, {"field": "ticket_id"}, {"field": "note"}]},
    ]}

    assert [s.sheet for s in ReportLayout.from_dict(cfg).sheets] == ["Daily", "Issues"]


@pytest.mark.parametrize("mutate, message", [
    (lambda c: c["sheets"][0].update(dataset="weekly"), "unknown dataset"),
    (lambda c: c["sheets"][0].update(sheet=""), "non-empty 'sheet'"),
    (lambda c: c["sheets"].append(c["sheets"][0]), "duplicate sheet"),
    (lambda c: c["sheets"][0].update(header_row=0), "header_row"),
    (lambda c: c["sheets"][0].update(first_column="4"), "first_column"),
    (lambda c: c["sheets"][0].update(columns=[]), "non-empty list"),
    (lambda c: c["sheets"][0].update(columns=[{"field": "run_date"}, {"field": "pic"}]),
     "'pic' is not a field of dataset 'summary'"),
    (lambda c: c["sheets"][0].update(columns=[{"field": "file"}]), "exactly one 'run_date'"),
    (lambda c: c["sheets"][0]["columns"].append({"field": "run_date"}), "exactly one 'run_date'"),
    (lambda c: c["sheets"][0]["columns"].append({"expand": "devices"}), "unknown expansion"),
    (lambda c: c["sheets"][0]["columns"].append({}), "either 'field' or 'expand'"),
    (lambda c: c.__setitem__("sheets", []), "non-empty list"),
])
def test_invalid_layouts_are_rejected(mutate, message):
    cfg = json.loads(json.dumps(MINIMAL))
    mutate(cfg)
    with pytest.raises(ValueError, match=message):
        ReportLayout.from_dict(cfg)


def test_statuses_cannot_be_expanded_on_the_issues_dataset():
    """An issue row is one case, not a bucket — it has no per-status counts."""
    cfg = {"sheets": [
        {"dataset": "issues", "sheet": "Issues", "header_row": 1, "first_column": "A",
         "columns": [{"field": "run_date"}, {"expand": "statuses"}]},
    ]}

    with pytest.raises(ValueError, match="cannot expand statuses"):
        ReportLayout.from_dict(cfg)


def test_a_custom_layout_can_be_loaded_from_a_file(tmp_path):
    path = tmp_path / "custom.json"
    path.write_text(json.dumps(MINIMAL), encoding="utf-8")

    assert ReportLayout.load(str(path)).sheets[0].sheet == "Summary"


def test_the_error_message_names_the_file_it_came_from(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text(json.dumps({"sheets": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="broken.json"):
        ReportLayout.load(str(path))
