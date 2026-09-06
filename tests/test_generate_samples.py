import os
from collections import defaultdict

import pytest

from parser.excel_reader import load_from_folder, parse_tool_data
from tools.generate_samples import DEFAULTS, generate, validate_config

CONFIG = validate_config({
    **DEFAULTS,
    "seed": 7,
    "file_count": 2,
    "sheets_per_file": 3,
    "devices_per_sheet": 2,
    "cases_per_sheet": {"min": 10, "max": 15},
    "pic_names": ["lee", "kim"],
})


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("generated")
    paths = generate(CONFIG, str(out))
    cases, file_results = load_from_folder(str(out))
    return paths, cases, file_results


def test_writes_requested_number_of_files(generated):
    paths, _, file_results = generated
    assert len(paths) == CONFIG["file_count"]
    assert all(os.path.isfile(p) for p in paths)
    assert [r["status"] for r in file_results] == ["OK"] * CONFIG["file_count"]


def test_tool_data_has_one_row_per_sheet_and_device(generated):
    paths, _, _ = generated
    expected = CONFIG["sheets_per_file"] * CONFIG["devices_per_sheet"]
    for path in paths:
        assert len(parse_tool_data(path)) == expected


def test_case_numbers_restart_per_sheet_with_no_gaps(generated):
    _, cases, _ = generated
    by_sheet = defaultdict(list)
    for c in cases:
        if c.case_no is not None and c.case_no.isdigit():
            by_sheet[(c.file_name, c.sheet, c.device)].append(int(c.case_no))

    assert by_sheet
    for numbers in by_sheet.values():
        assert numbers == list(range(1, len(numbers) + 1))
        assert CONFIG["cases_per_sheet"]["min"] <= len(numbers) <= CONFIG["cases_per_sheet"]["max"]


def test_group_rows_carry_only_a_title(generated):
    _, cases, _ = generated
    group_rows = [c for c in cases if c.case_no and c.case_no.startswith("[")]
    assert group_rows, "expected at least one group row"
    for c in group_rows:
        assert (c.scope, c.result, c.test_date, c.pic, c.ticket_id, c.note) == (None,) * 6


def test_values_stay_inside_the_configured_sets(generated):
    _, cases, _ = generated
    data_rows = [c for c in cases if c.case_no and c.case_no.isdigit()]

    assert {c.scope for c in data_rows} <= set(CONFIG["scopes"])
    allowed_results = {r or None for r in CONFIG["result_weights"]}
    assert {c.result for c in data_rows} <= allowed_results
    assert {c.pic for c in data_rows if c.pic} <= set(CONFIG["pic_names"])

    start, end = CONFIG["date_range"]
    assert all(start <= c.test_date <= end for c in data_rows if c.test_date)


def test_untested_rows_have_no_date_or_pic(generated):
    _, cases, _ = generated
    for c in cases:
        if c.result is None:
            assert (c.test_date, c.pic, c.ticket_id, c.note) == (None,) * 4


def test_same_seed_reproduces_the_same_data(tmp_path):
    generate(CONFIG, str(tmp_path / "a"))
    generate(CONFIG, str(tmp_path / "b"))
    cases_a, _ = load_from_folder(str(tmp_path / "a"))
    cases_b, _ = load_from_folder(str(tmp_path / "b"))

    assert [c.to_dict() for c in cases_a] == [c.to_dict() for c in cases_b]
