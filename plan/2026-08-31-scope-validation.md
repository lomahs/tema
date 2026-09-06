# Scope Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: dùng superpowers:subagent-driven-development (khuyến nghị) hoặc superpowers:executing-plans để thực thi plan này theo từng task. Các bước dùng cú pháp checkbox (`- [ ]`) để theo dõi.

**Goal:** Thêm một file config liệt kê các giá trị Scope hợp lệ; row nào có Scope không nằm trong danh sách đó thì bị bỏ qua ngay ở parser, không trở thành test case.

**Architecture:** Lặp lại đúng pattern của taxonomy kết quả đang có — một file JSON (`parser/scope_config.json`), một class validate lúc import (`ScopeSet` trong `parser/scope.py`, đối xứng với `StatusSet` trong `parser/status.py`), một singleton `SCOPE`, và một env var override trong `config.py`. Điểm lọc duy nhất nằm trong `read_test_cases`: row có scope không hợp lệ thì `continue` trước khi dựng `TestCase`. Vì lọc ở tầng parser, `api/routes.py`, mọi endpoint và toàn bộ frontend **không phải sửa một dòng nào** — chúng chỉ đơn giản nhận ít case hơn.

**Tech Stack:** Python 3.14, pandas + openpyxl (đọc .xlsx), Flask, pytest. Không có bước build, không có test JS.

**Spec:** Chốt trong phiên brainstorming ngày 2026-08-31 với người dùng; toàn bộ quyết định được ghi lại trong mục "Context & quyết định" ngay dưới đây (không có file spec riêng — đây là thay đổi bounded).

## Global Constraints

- Chạy mọi lệnh bằng venv của project: `.venv/bin/python` (Python 3.14). Không dùng `python` trần.
- **Không hard-code giá trị scope trong Python hay JS.** Mọi giá trị đọc từ file JSON, y như luật đang áp dụng cho status keys (xem CLAUDE.md).
- So khớp scope: **trim khoảng trắng + không phân biệt hoa thường** (dùng `str.casefold()`, giống `StatusSet.classify`).
- Ô Scope rỗng = **không hợp lệ** → row bị bỏ qua.
- Danh sách hợp lệ mặc định, đúng thứ tự này: `FPT`, `FPT (JM Support)`, `JP`, `Cancel`.
- Không thêm endpoint mới, không sửa `api/routes.py`, không sửa file nào trong `static/js/` hay `templates/`.
- Project **chưa init git** (`git rev-parse` báo "not a git repository"), nên mỗi task kết thúc bằng chạy full test suite thay vì commit. Nếu người dùng `git init` sau này thì mỗi task tương ứng một commit.
- Không có linter/formatter. Bám sát style hiện có: docstring kiểu Google, comment giải thích *tại sao* chứ không phải *làm gì*.

---

## Context & quyết định

Hiện tại `read_test_cases` biến **mọi** row trong khoảng `start_row..end_row` thành một `TestCase`, kể cả row trống và row tiêu đề nhóm. Vì vậy `total` ở tab Summary bị thổi phồng bởi các row filler.

Quyết định của người dùng trong phiên brainstorming:

1. Row có scope không hợp lệ bị **loại ngay ở parser** — không xuất hiện ở Summary, Daily hay Detail.
2. Ô scope rỗng cũng tính là không hợp lệ.
3. Phạm vi đợt này **chỉ gồm** phân loại hợp lệ/không hợp lệ + skip row. Không làm báo cáo cảnh báo, không sửa UI.

**Nằm ngoài phạm vi (đã bàn nhưng hoãn lại):** báo cáo "row bị loại nhưng có dữ liệu" (phân biệt row filler rỗng hoàn toàn với test case thật quên điền scope) qua `/api/summary` + bảng trên tab Summary. Đừng làm trong plan này. Bước 3 của Task 2 có ghi log số row bị skip — đó là công cụ chẩn đoán tạm thời cho tới khi tính năng kia được làm.

## File Structure

| File | Trách nhiệm | Task |
|---|---|---|
| `parser/scope_config.json` | **Tạo mới.** Danh sách giá trị Scope hợp lệ. | 1 |
| `parser/scope.py` | **Tạo mới.** `ScopeSet` (load + validate + `is_valid`) và singleton `SCOPE`. | 1 |
| `config.py` | **Sửa.** Thêm env var `SCOPE_CONFIG`. | 1 |
| `tests/test_scope.py` | **Tạo mới.** Test cho `ScopeSet`. | 1 |
| `parser/excel_reader.py` | **Sửa.** `read_test_cases` skip row có scope không hợp lệ. | 2 |
| `tests/test_excel_reader.py` | **Sửa.** Thêm test skip; cập nhật fixture cũ vốn không điền Scope. | 2 |
| `tests/test_api.py` | **Sửa.** Fixture `workbook_dir` phải điền Scope, nếu không mọi row biến mất. | 2 |
| `tools/generate_samples.py` | **Sửa.** Validate `scopes` theo `SCOPE`; thêm `Cancel` vào mặc định. | 3 |
| `tools/sample_config.json` | **Sửa.** Thêm `Cancel`. | 3 |
| `tests/test_generate_samples.py` | **Sửa.** Row tiêu đề nhóm giờ bị skip. | 3 |
| `README.md`, `CLAUDE.md` | **Sửa.** Tài liệu. | 3 |

---

## Task 1: Config scope + `ScopeSet`

Tự chứa hoàn toàn: chưa có gì gọi tới nó, nên test suite phải xanh 100% sau task này mà không cần đụng file nào khác.

**Files:**
- Create: `parser/scope_config.json`
- Create: `parser/scope.py`
- Modify: `config.py`
- Test: `tests/test_scope.py`

**Interfaces:**
- Consumes: không có (task đầu tiên).
- Produces:
  - `parser.scope.SCOPE` — instance `ScopeSet` dùng chung, dựng lúc import.
  - `ScopeSet.is_valid(scope) -> bool` — nhận `str | None`.
  - `ScopeSet.from_dict(raw: dict, source: str = "<dict>") -> ScopeSet`, `ScopeSet.load(path: str) -> ScopeSet`, `ScopeSet.to_dict() -> dict`.
  - `ScopeSet.scopes -> list[str]` — các giá trị hợp lệ, đúng thứ tự trong file config.
  - `config.SCOPE_CONFIG -> str`.

- [ ] **Step 1: Viết file test trước (chưa có code, test sẽ fail)**

Tạo `tests/test_scope.py`. Nội dung này mô phỏng cấu trúc `tests/test_status.py` để hai file đọc giống nhau:

```python
import json

import pytest

from parser.scope import SCOPE, ScopeSet

MINIMAL = {"valid": ["FPT", "JP"]}


def test_configured_scopes_are_valid():
    assert SCOPE.is_valid("FPT")
    assert SCOPE.is_valid("FPT (JM Support)")
    assert SCOPE.is_valid("JP")
    assert SCOPE.is_valid("Cancel")


def test_matching_ignores_case_and_surrounding_whitespace():
    assert SCOPE.is_valid("  fpt  ")
    assert SCOPE.is_valid("fpt (jm support)")


def test_unknown_scopes_are_invalid():
    assert not SCOPE.is_valid("VN")
    assert not SCOPE.is_valid("FPT2")


def test_a_blank_scope_is_invalid():
    """A row with no scope is not a test case — it is a filler or a heading row."""
    assert not SCOPE.is_valid(None)
    assert not SCOPE.is_valid("")
    assert not SCOPE.is_valid("   ")


def test_scopes_keep_their_configured_order():
    assert SCOPE.scopes == ["FPT", "FPT (JM Support)", "JP", "Cancel"]


def test_a_custom_config_changes_the_valid_set(tmp_path):
    path = tmp_path / "custom.json"
    path.write_text(json.dumps(MINIMAL), encoding="utf-8")
    custom = ScopeSet.load(str(path))

    assert custom.is_valid("JP")
    assert not custom.is_valid("Cancel")     # not configured here
    assert custom.scopes == ["FPT", "JP"]


def test_to_dict_round_trips_the_config():
    assert ScopeSet.from_dict(MINIMAL).to_dict() == {"valid": ["FPT", "JP"]}


@pytest.mark.parametrize("cfg, message", [
    ({"valid": []}, "non-empty list"),
    ({}, "non-empty list"),
    ({"valid": "FPT"}, "non-empty list"),
    ({"valid": ["FPT", "fpt"]}, "duplicate"),
    ({"valid": ["FPT", "  "]}, "non-empty string"),
    ({"valid": ["FPT", 3]}, "non-empty string"),
])
def test_invalid_configs_are_rejected(cfg, message):
    with pytest.raises(ValueError, match=message):
        ScopeSet.from_dict(cfg)
```

- [ ] **Step 2: Chạy test để xác nhận nó fail**

Run: `.venv/bin/python -m pytest tests/test_scope.py -q`
Expected: FAIL khi collect — `ModuleNotFoundError: No module named 'parser.scope'`

- [ ] **Step 3: Tạo file config**

Tạo `parser/scope_config.json`:

```json
{
  "valid": ["FPT", "FPT (JM Support)", "JP", "Cancel"]
}
```

- [ ] **Step 4: Thêm env var vào `config.py`**

Thêm vào cuối `config.py`, ngay dưới khối `RESULT_STATUS_CONFIG`:

```python
# Scope hợp lệ. Row có Scope ngoài danh sách này không được coi là test case.
SCOPE_CONFIG = os.environ.get(
    "SCOPE_CONFIG",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "parser", "scope_config.json"),
)
```

- [ ] **Step 5: Viết `parser/scope.py`**

Tạo `parser/scope.py` với đúng nội dung sau:

```python
"""Scope -> valid / invalid, driven by a JSON config.

A row whose Scope cell is not one of the configured values is not a test case
at all: `parser.excel_reader` skips it instead of reading it into a `TestCase`.
Real sheets are full of such rows — group headings and blank filler at the end
of a block — and counting them inflates every total.
"""
import json
import logging
import os

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "scope_config.json")


class ScopeSet:
    """The Scope values that mark a row as a real test case."""

    def __init__(self, scopes: list[str]):
        self.scopes = scopes
        # Matching is case- and whitespace-insensitive, like StatusSet.classify.
        self._lookup = {s.casefold() for s in scopes}

    @classmethod
    def load(cls, path: str = DEFAULT_CONFIG_PATH) -> "ScopeSet":
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return cls.from_dict(raw, source=path)

    @classmethod
    def from_dict(cls, raw: dict, source: str = "<dict>") -> "ScopeSet":
        entries = raw.get("valid")
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"{source}: 'valid' must be a non-empty list")

        scopes: list[str] = []
        seen: set[str] = set()
        for i, entry in enumerate(entries):
            if not isinstance(entry, str) or not entry.strip():
                raise ValueError(f"{source}: valid[{i}] must be a non-empty string")
            value = entry.strip()
            token = value.casefold()
            if token in seen:
                raise ValueError(f"{source}: duplicate scope '{value}'")
            seen.add(token)
            scopes.append(value)

        return cls(scopes)

    def is_valid(self, scope) -> bool:
        """Whether a raw Scope cell names a configured scope.

        A blank cell is invalid: a row with no scope is not a test case.
        """
        if scope is None:
            return False
        return str(scope).strip().casefold() in self._lookup

    def to_dict(self) -> dict:
        return {"valid": list(self.scopes)}


def _load_default() -> ScopeSet:
    from config import SCOPE_CONFIG

    path = SCOPE_CONFIG
    try:
        return ScopeSet.load(path)
    except Exception as e:
        if path == DEFAULT_CONFIG_PATH:
            raise
        log.error("Failed to load scope config '%s': %s — using defaults", path, e)
        return ScopeSet.load(DEFAULT_CONFIG_PATH)


SCOPE = _load_default()
```

- [ ] **Step 6: Chạy test scope, xác nhận pass**

Run: `.venv/bin/python -m pytest tests/test_scope.py -q`
Expected: PASS — 12 test (7 test đơn + 6 case parametrize, trừ đi cách đếm của pytest: cứ xanh hết là đạt)

- [ ] **Step 7: Chạy full suite, xác nhận chưa có gì hỏng**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS toàn bộ. Chưa có gì import `parser.scope` nên hành vi chưa đổi. Nếu có test đỏ ở đây thì là do một lỗi khác — dừng lại và điều tra trước khi sang Task 2.

- [ ] **Step 8: Checkpoint**

Chưa có git repo nên không commit. Ghi lại: Task 1 xong, config + `ScopeSet` đã có, chưa ai dùng.

---

## Task 2: Skip row có scope không hợp lệ trong parser

Đây là task đổi hành vi. Nó **sẽ làm đỏ các test đang có** — vì gần như mọi fixture trong `tests/` để trống cột Scope. Việc sửa các fixture đó là một phần của task này; suite phải xanh trở lại trước khi kết thúc.

**Files:**
- Modify: `parser/excel_reader.py:160-196` (`read_test_cases`), thêm import ở đầu file
- Test: `tests/test_excel_reader.py` (thêm test mới + sửa fixture cũ)
- Test: `tests/test_api.py:20-42` (sửa fixture `workbook_dir`)

**Interfaces:**
- Consumes: `parser.scope.SCOPE` và `SCOPE.is_valid(scope) -> bool` từ Task 1.
- Produces: không có API mới. `read_test_cases`, `load_file`, `load_files`, `load_from_folder`, `load_from_files` giữ **nguyên** signature và kiểu trả về — chỉ là list case trả về ngắn hơn.

- [ ] **Step 1: Viết các test fail cho hành vi skip**

Thêm vào cuối `tests/test_excel_reader.py`:

```python
def test_a_row_with_an_unconfigured_scope_is_not_a_test_case(make_workbook):
    path = make_workbook(
        tool_data=[config_row("Login", "iPhone", 4, 6)],
        cells={"Login": {
            (4, "A"): "TC-1", (4, "B"): "FPT", (4, "C"): "OK",
            (5, "A"): "TC-2", (5, "B"): "VN", (5, "C"): "OK",     # not configured
            (6, "A"): "TC-3", (6, "B"): "JP", (6, "C"): "NG",
        }},
    )
    assert [c.case_no for c in load_file(path)] == ["TC-1", "TC-3"]


def test_a_row_with_no_scope_is_not_a_test_case(make_workbook):
    """Blank filler rows and group heading rows both land here."""
    path = make_workbook(
        tool_data=[config_row("Login", "iPhone", 4, 7)],
        cells={"Login": {
            (4, "A"): "TC-1", (4, "B"): "FPT", (4, "C"): "OK",
            (5, "A"): "[Login - boundary]",                        # group heading
            (6, "A"): "TC-2", (6, "C"): "OK",                      # forgot the scope
                                                                   # row 7 is blank
        }},
    )
    assert [c.case_no for c in load_file(path)] == ["TC-1"]


def test_scope_matching_ignores_case_and_whitespace(make_workbook):
    path = make_workbook(
        tool_data=[config_row("Login", "iPhone", 4, 5)],
        cells={"Login": {
            (4, "A"): "TC-1", (4, "B"): "  fpt (jm support) ", (4, "C"): "OK",
            (5, "A"): "TC-2", (5, "B"): "cancel", (5, "C"): "対象外",
        }},
    )
    cases = load_file(path)
    assert [c.case_no for c in cases] == ["TC-1", "TC-2"]
    # The scope is stored exactly as the sheet wrote it, only trimmed.
    assert cases[0].scope == "fpt (jm support)"


def test_a_sheet_with_no_valid_scope_yields_no_cases(make_workbook):
    path = make_workbook(
        tool_data=[config_row("Login", "iPhone", 4, 5)],
        cells={"Login": {(4, "A"): "TC-1", (4, "B"): "VN", (5, "A"): "TC-2"}},
    )
    cases, file_results = load_from_files([path])
    assert cases == []
    # An empty sheet is not an error: the file still loads successfully.
    assert file_results[0]["status"] == "OK"
    assert file_results[0]["cases"] == 0
```

- [ ] **Step 2: Chạy các test mới để xác nhận fail**

Run: `.venv/bin/python -m pytest tests/test_excel_reader.py -q -k "scope"`
Expected: FAIL — parser hiện đọc mọi row, nên `test_a_row_with_an_unconfigured_scope_is_not_a_test_case` trả về `["TC-1", "TC-2", "TC-3"]` chứ không phải `["TC-1", "TC-3"]`.

- [ ] **Step 3: Cài đặt bộ lọc trong `read_test_cases`**

Trong `parser/excel_reader.py`, thêm import cạnh import `parser.models` đang có (dòng 11):

```python
from parser.models import SheetConfig, TestCase
from parser.scope import SCOPE
```

Rồi thay vòng lặp dựng case ở cuối `read_test_cases` (dòng 179-196) bằng:

```python
    cases = []
    skipped = 0
    for offset, (_, row) in enumerate(rows.iterrows()):
        scope = _clean(cell(row, "scope"))
        # A row whose Scope isn't configured is not a test case: group heading
        # rows, blank filler at the end of a block, and typos all land here.
        # Counting them would inflate every total.
        if not SCOPE.is_valid(scope):
            skipped += 1
            continue
        cases.append(TestCase(
            file_name=file_name,
            sheet=config.sheet,
            device=config.device,
            row_num=config.start_row + offset,
            case_no=_clean(cell(row, "case_no")),
            scope=scope,
            result=_clean(cell(row, "result")),
            test_date=_clean_date(cell(row, "test_date")),
            pic=_clean(cell(row, "pic")),
            ticket_id=_clean(cell(row, "ticket_id")),
            note=_clean(cell(row, "note")),
        ))
    if skipped:
        log.info("[%s] Sheet '%s' / device '%s': skipped %d row(s) with an invalid scope",
                 file_name, config.sheet, config.device, skipped)
    log.info("[%s] Read %d case(s) from sheet '%s' / device '%s'",
             file_name, len(cases), config.sheet, config.device)
    return cases
```

- [ ] **Step 4: Chạy lại các test scope, xác nhận pass**

Run: `.venv/bin/python -m pytest tests/test_excel_reader.py -q -k "scope"`
Expected: PASS

- [ ] **Step 5: Chạy full suite để lộ ra các fixture cũ bị hỏng**

Run: `.venv/bin/python -m pytest -q`
Expected: FAIL nhiều test trong `tests/test_excel_reader.py`, `tests/test_api.py`, `tests/test_generate_samples.py` — chủ yếu là `IndexError: list index out of range` khi làm `load_file(path)[0]`. Đúng như dự kiến: các fixture đó không điền Scope. Step 6-8 sửa chúng. (`tests/test_generate_samples.py` để sang Task 3.)

- [ ] **Step 6: Sửa fixture trong `tests/test_excel_reader.py`**

Thêm ô Scope vào các test đang có. Sửa từng chỗ, đúng như sau:

`test_a_real_date_cell_reads_back_as_an_iso_date`, `test_a_date_cell_with_a_time_keeps_only_the_date`, `test_a_text_date_with_a_midnight_time_is_trimmed`, `test_numeric_cells_do_not_gain_a_decimal_suffix` — thêm `(4, "B"): "FPT",` vào dict `cells` của từng test.

`test_blank_cells_become_none` — giờ Scope bắt buộc phải có, nên bỏ `scope` khỏi phần assert:

```python
def test_blank_cells_become_none(make_workbook):
    path = make_workbook(
        tool_data=[config_row("Login", "iPhone", 4, 4)],
        cells={"Login": {(4, "A"): "TC-1", (4, "B"): "FPT"}},
    )
    case = load_file(path)[0]
    assert (case.result, case.test_date, case.pic) == (None,) * 3
```

`test_two_device_blocks_on_one_sheet_read_their_own_columns` — row 4 đã có `(4, "B"): "FPT"`; thêm `(5, "B"): "JP",` cho row 5, nếu không `TC-2` bị loại và test tra `by_device[("iPad", "TC-2")]` sẽ `KeyError`.

`test_row_numbers_map_back_to_the_excel_rows` — thêm Scope cho cả ba row:

```python
        cells={"Login": {(4, "A"): "TC-1", (4, "B"): "FPT",
                         (5, "A"): "TC-2", (5, "B"): "FPT",
                         (6, "A"): "TC-3", (6, "B"): "FPT"}},
```

`test_a_bad_row_fails_only_its_own_file` — thêm `(4, "B"): "FPT",` vào dict cells của `good.xlsx` (test assert `[c.file_name for c in cases] == ["good.xlsx"]`).

`test_excel_lock_files_are_skipped_in_files_mode` — thêm `(4, "B"): "FPT",` vào cả hai workbook cho nhất quán.

`test_a_sheet_named_in_tool_data_but_absent_is_skipped` — thêm `(4, "B"): "FPT",`.

`test_columns_beyond_the_sheet_width_read_as_none` — thêm `(4, "B"): "FPT",`.

`test_a_malformed_tool_data_row_is_reported_with_its_row_number` — **không đổi**. Nó fail ngay ở `parse_tool_data`, chưa đọc tới row nào.

- [ ] **Step 7: Sửa fixture `workbook_dir` trong `tests/test_api.py`**

Cột `B` là Scope cho **cả hai** device block (`"A B C D E F G"` và `"A B H I J K L"` dùng chung `B`). Thay dict `cells` trong fixture bằng:

```python
        {"Login": {
            # iPhone: OK, NG with a ticket, NG without one, an unknown result, blank
            (4, "A"): "TC-1", (4, "B"): "FPT",
            (4, "C"): "OK", (4, "D"): datetime(2026, 8, 5), (4, "E"): "lee",
            (5, "A"): "TC-2", (5, "B"): "FPT",
            (5, "C"): "NG", (5, "D"): "2026-08-05 00:00:00", (5, "E"): "lee",
            (5, "F"): "BUG-1",
            (6, "A"): "TC-3", (6, "B"): "JP",
            (6, "C"): "NG", (6, "D"): "2026-08-05", (6, "E"): "lee",
            (7, "A"): "TC-4", (7, "B"): "JP",
            (7, "C"): "TBD", (7, "D"): "2026-08-06", (7, "E"): "kim",
            (8, "A"): "TC-5", (8, "B"): "FPT",
            # iPad
            (4, "H"): "保留", (4, "I"): "2026-08-05", (4, "J"): "kim", (4, "K"): "BUG-2",
            (5, "H"): "OK", (5, "I"): "2026-08-05", (5, "J"): "kim",
        }},
```

Số liệu mong đợi không đổi: cả 5 row đều có scope hợp lệ nên vẫn được đếm y như trước (iPhone: 1 OK, 2 NG, 1 Other, 1 NYS; tổng daily 6).

- [ ] **Step 8: Thêm một test API chứng minh row bị skip không lọt vào thống kê**

Thêm vào cuối `tests/test_api.py`:

```python
def test_rows_with_an_invalid_scope_never_reach_the_api(client, tmp_path):
    write_workbook(
        tmp_path / "TC.xlsx",
        [config_row("Login", "iPhone", 4, 6)],
        {"Login": {
            (4, "A"): "TC-1", (4, "B"): "FPT", (4, "C"): "OK",
            (5, "A"): "TC-2", (5, "B"): "VN", (5, "C"): "OK",   # scope not configured
            (6, "A"): "TC-3",                                    # no scope at all
        }},
    )
    assert load(client, str(tmp_path))["loaded"] == 1

    assert [c["case_no"] for c in client.get("/api/data").get_json()] == ["TC-1"]
    groups = client.get("/api/summary").get_json()["groups"]
    assert [g["total"] for g in groups] == [1]
```

- [ ] **Step 9: Chạy hai file test đó, xác nhận pass**

Run: `.venv/bin/python -m pytest tests/test_excel_reader.py tests/test_api.py -q`
Expected: PASS toàn bộ. `tests/test_generate_samples.py` vẫn đỏ — đó là việc của Task 3.

- [ ] **Step 10: Checkpoint**

Ghi lại: parser đã lọc; `test_generate_samples.py` vẫn đang đỏ và Task 3 sẽ xử lý.

---

## Task 3: Đồng bộ tool sinh file mẫu + tài liệu

Sau task này toàn bộ suite phải xanh.

**Files:**
- Modify: `tools/generate_samples.py` (`DEFAULTS`, `validate_config`)
- Modify: `tools/sample_config.json`
- Test: `tests/test_generate_samples.py`
- Modify: `README.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: `parser.scope.SCOPE` và `SCOPE.is_valid(scope)` từ Task 1; hành vi skip từ Task 2.
- Produces: không có API mới. `validate_config(cfg) -> dict` giữ nguyên signature, chỉ thêm một luật kiểm tra.

- [ ] **Step 1: Viết các test fail cho generator**

Trong `tests/test_generate_samples.py`, **thay** `test_group_rows_carry_only_a_title` (đang assert group row được đọc thành case rỗng — giờ chúng bị skip) bằng:

```python
def test_group_rows_are_skipped(generated):
    """Group heading rows carry no scope, so they are not test cases."""
    _, cases, _ = generated
    assert cases, "expected the generated files to produce cases"
    assert not [c for c in cases if c.case_no and c.case_no.startswith("[")]


def test_every_parsed_case_has_a_valid_scope(generated):
    _, cases, _ = generated
    assert all(SCOPE.is_valid(c.scope) for c in cases)
```

Thêm import ở đầu file, cạnh các import đang có:

```python
from parser.scope import SCOPE
```

Và thêm một test cho luật validate mới, ở cuối file:

```python
def test_a_config_scope_the_parser_would_drop_is_rejected():
    with pytest.raises(ValueError, match="not a valid scope"):
        validate_config({**DEFAULTS, "scopes": ["FPT", "VN"]})
```

- [ ] **Step 2: Chạy để xác nhận fail**

Run: `.venv/bin/python -m pytest tests/test_generate_samples.py -q`
Expected: FAIL — `test_a_config_scope_the_parser_would_drop_is_rejected` fail vì `validate_config` chưa có luật đó; `NameError`/import error nếu quên thêm import `SCOPE`.

- [ ] **Step 3: Thêm `Cancel` vào scope mặc định của generator**

Trong `tools/generate_samples.py`, sửa dòng `DEFAULTS["scopes"]`:

```python
    "scopes": ["FPT", "FPT (JM Support)", "JP", "Cancel"],
```

Trong `tools/sample_config.json`, sửa dòng `"scopes"` tương ứng:

```json
  "scopes": ["FPT", "FPT (JM Support)", "JP", "Cancel"],
```

- [ ] **Step 4: Validate scope của generator theo `SCOPE`**

Trong `tools/generate_samples.py`, thêm import cạnh `from parser.status import STATUS`:

```python
from parser.scope import SCOPE
```

Trong `validate_config`, ngay sau vòng lặp kiểm tra pool rỗng (`for key in ("pic_names", "scopes", ...)`), chèn:

```python
    # A scope the parser doesn't recognise would make every generated row vanish
    # on load, which looks like a broken tool rather than a config mistake.
    for scope in cfg["scopes"]:
        if not SCOPE.is_valid(scope):
            raise ValueError(
                f"'scopes' contains {scope!r}, which is not a valid scope "
                f"(see parser/scope_config.json)"
            )
```

Bổ sung một dòng vào docstring `Raises:` của `validate_config`: `một scope không có trong parser/scope_config.json`.

- [ ] **Step 5: Chạy test generator, xác nhận pass**

Run: `.venv/bin/python -m pytest tests/test_generate_samples.py -q`
Expected: PASS

- [ ] **Step 6: Chạy full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS toàn bộ, không có test nào bị bỏ qua.

- [ ] **Step 7: Cập nhật `README.md`**

(a) Trong cây thư mục ở mục "Cấu trúc", thêm hai dòng vào khối `parser/`, ngay dưới `result_status.json`:

```
│   ├── scope.py            # ScopeSet: scope hợp lệ / không hợp lệ
│   ├── scope_config.json   # cấu hình scope hợp lệ
```

Và thêm `test_scope.py` vào danh sách trong khối `tests/`.

(b) Thêm một mục mới ngay sau mục "## Phân loại kết quả" (trước "## Test"):

````markdown
## Phạm vi (Scope)

Cột Scope quyết định một dòng có phải test case hay không. Danh sách giá trị hợp lệ nằm
trong `parser/scope_config.json`:

```json
{
  "valid": ["FPT", "FPT (JM Support)", "JP", "Cancel"]
}
```

So khớp **không phân biệt hoa thường** và tự cắt khoảng trắng thừa, nên `  fpt  ` vẫn khớp `FPT`.

Dòng có Scope **không nằm trong danh sách** — bao gồm cả **ô rỗng** — sẽ bị **bỏ qua ngay khi
đọc file**: nó không xuất hiện ở Summary, Daily hay Detail và không được tính vào `total`.
Nhờ vậy các dòng tiêu đề nhóm và dòng trống ở cuối mỗi khối không làm phồng số liệu.

> Lưu ý: test case thật nhưng quên điền Scope cũng bị bỏ qua. Số dòng bị bỏ qua được ghi ở
> log của server (`Sheet '...' / device '...': skipped N row(s) with an invalid scope`).

Dùng file cấu hình khác:

```bash
SCOPE_CONFIG=/path/to/my_scope.json python app.py
```
```

(c) Trong mục "Tạo file mẫu", bảng config có dòng `scopes` — cập nhật mô tả thành:
`Giá trị cột Scope — mặc định FPT, FPT (JM Support), JP, Cancel; mọi giá trị phải có trong parser/scope_config.json`

- [ ] **Step 8: Cập nhật `CLAUDE.md`**

Thêm đoạn sau ngay dưới đoạn "**The status taxonomy is data, not code.**" (trước đoạn "**Frontend state ownership.**"):

```markdown
**Scope decides what counts as a test case.** [parser/scope_config.json](parser/scope_config.json)
lists the valid Scope values and `ScopeSet` in [parser/scope.py](parser/scope.py) validates it at
import time. `read_test_cases` skips any row whose Scope isn't on the list — a blank cell included —
so group heading rows and trailing filler never become `TestCase`s. The filter lives in the parser
alone: `api/routes.py` and the frontend just see fewer cases. Matching is case-insensitive and
trimmed. `tools/generate_samples.py` validates its own `scopes` pool against it, so a sample file
can't be generated with rows the parser would silently drop. Never hard-code scope values in Python
or JS. Note this means every test fixture must fill the Scope column, or its rows vanish.
```

- [ ] **Step 9: Kiểm tra lại end-to-end với dữ liệu thật**

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m tools.generate_samples --out samples/generated --seed 1
.venv/bin/python app.py     # http://127.0.0.1:5000
```

Trong trình duyệt, load thư mục `samples/generated`:
- Tab **Summary** — `total` mỗi dòng giờ **nhỏ hơn** trước đúng bằng số dòng tiêu đề nhóm mà generator sinh ra (`group_row_rate` mặc định 0.1). Tổng các cột status vẫn phải bằng `total`.
- Tab **Detail** — filter Scope chỉ còn các giá trị trong `scope_config.json`, không còn lựa chọn rỗng.
- **Log server** — nếu có dòng bị bỏ qua sẽ thấy `skipped N row(s) with an invalid scope`.
- Sửa `parser/scope_config.json`, bỏ `"JP"` đi rồi bấm **Reload** — số case phải giảm, chứng tỏ config có tác dụng mà không cần sửa code. Nhớ khôi phục lại file sau khi thử.

- [ ] **Step 10: Checkpoint cuối**

Toàn bộ suite xanh, tài liệu đã cập nhật, app chạy đúng. Chuyển `plan/plan.md` sang `plan/done/2026-08-31-scope-validation.md` theo đúng quy ước của thư mục `plan/`.

---

## Verification

Điều kiện hoàn thành của cả plan:

```bash
.venv/bin/python -m pytest -q                    # tất cả xanh, không skip
.venv/bin/python -m tools.generate_samples --out samples/generated --seed 1
.venv/bin/python app.py
```

Ba điều bắt buộc phải đúng:

1. Dòng có Scope là `FPT` / `FPT (JM Support)` / `JP` / `Cancel` (hoa thường tùy ý) → được đọc thành test case.
2. Mọi dòng khác — kể cả Scope rỗng — không xuất hiện ở bất kỳ endpoint nào và không tính vào `total`.
3. Sửa `parser/scope_config.json` là đủ để đổi tập scope hợp lệ; không có giá trị scope nào bị hard-code trong Python hay JS.
