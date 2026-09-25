# Planning Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Planning view's Day / Person / Calendar cuts with the design canvas's single
page — phase bar, five KPIs, a Day plan (matrix + list) with a per-slot editor dialog, a burndown,
and a phase grid — on top of the plan storage that already exists.

**Architecture:** The stored plan does not change shape: a day is still `PlanEntry(pic, file,
device, planned)` rows written whole through `PUT /api/plan/<date>`. What is new is (a) a
taxonomy flag saying which statuses are *remaining*, (b) plan settings (phase start/end, daily
target) stored in the same `plan.json`, and (c) two read endpoints — `/api/plan/phase` and
`/api/plan/board/<date>` — whose figures are computed in `tcm/services/planning.py` from
`daily_rows` / `remaining_rows`, never counted afresh. The browser does layout and cell-state
classification only. The view becomes a four-module package `static/js/views/planning/` shaped
like `views/detail/`.

**Tech Stack:** Python 3.14, Flask, pytest; vanilla ES modules, hand-written CSS (no framework).

**Spec:** The design canvas `design/Planning.html`, unpacked for reading into
`design/planning/component.js` (the logic — `planVals()` at lines 266–668 is the Planning view) and
`design/planning/planning-markup.html` (its template). Plus the four decisions taken with the
user on 2026-09-25:

1. **Replace** the three cuts with the design. Person cut and the suggestion table go; the
   baseline keeps being frozen and stored but is not shown.
2. **Remaining is a taxonomy flag**: `"remaining": true` in `result_status.json`, shipped on NYS
   and Pending (the design's `pendingIsRemaining` default).
3. **The daily target comes back**, as a plan setting, used only for the member day-load warning.
   Daily and Productivity keep drawing from the plan calendar — the target does *not* return there.
4. **The editor is a native `<dialog>` modal**, as designed.

## Global Constraints

- Run everything with `.venv/bin/python`; tests with `.venv/bin/python -m pytest -q`. Full suite green after every task.
- Layering (`tests/test_layering.py`): `tcm/domain/` imports only `tcm.domain` / `tcm.settings`; only `tcm/web/` imports flask.
- Never hard-code status keys (`"NYS"`, `"Pending"`, …) in Python or JS — ask `STATUS` / `/api/statuses`.
- Every `fetch` lives in `static/js/api.js`.
- **No accent colour.** The design's green `#1F6F5C` (buttons, actual line, "exceeded") is replaced by ink; colour on screen means status and comes from `--tone-*` tokens in `static/css/tokens.css`. No literal hex in CSS or JS.
- No literal `border-radius`; use `--r-xs/sm/md/lg/full`.
- A row/cell addresses itself by integer index into a render-local array, never by a file name or PIC in a `data-` attribute.
- New CSS goes at the end of the Planning section of `static/css/views.css` (the `.plan-*` rules around line 472), not in a new file.
- Working days are Mon–Fri; there is no holiday calendar. Today is always a phase day even on a weekend (design `phaseDays`).
- Commit after each task; end each commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Nothing loaded** — `/api/plan/phase` and `/api/plan/board/<date>` with an empty workspace answer zeros, not a 500; the plan is still editable. (Task 4, Task 5 tests.)
2. **A plan row for a file/device the load no longer has** (renamed workbook) — it still appears as a slot with remaining 0 and is flagged over-remaining; nothing crashes. (Task 4 test.)
3. **Phase end before phase start, or no settings saved yet** — the PUT is refused with the domain's message; with nothing saved the defaults are start = earliest test date (or today), end = today + 5 working days. (Task 2, Task 4 tests.)
4. **No execution in the forecast window** — forecast finish is `null` and the note says so; no infinite loop in working-day arithmetic. (Task 4 test.)
5. **Cases with no PIC** (`daily_rows` reports them as `"N/A"`) — they count toward a slot's done total and the burndown, but never become a member column. (Task 4 test.)

---

## File Structure

| File | Responsibility |
|---|---|
| `config/result_status.json` | add `"remaining": true` to NYS and Pending |
| `tcm/domain/status.py` | parse/validate `remaining`; expose `STATUS.remaining`, `STATUS.worked` |
| `tcm/domain/plan.py` | add `PlanSettings` + working-day helpers (`workdays`, `add_workdays`, `phase_days`) |
| `tcm/domain/ports.py` | widen `PlanRepository` with `settings()` / `put_settings()` |
| `tcm/infrastructure/plan/json_store.py` | store `settings` beside `days` in `plan.json` |
| `tcm/services/aggregation.py` | `remaining_rows` reads `STATUS.remaining`; `keep_finished` option |
| `tcm/services/planning.py` | add `phase_view`, `board_view`, settings get/save; drop `person_view`, `suggest`, `rebaseline` |
| `tcm/web/blueprints/plan.py` | add `/api/plan/phase`, `/api/plan/board/<date>`, `/api/plan/settings`; drop person/suggest/baseline routes |
| `static/js/api.js` | add `getPlanPhase`, `getPlanBoard`, `getPlanSettings`, `putPlanSettings`; drop `getPlanPerson`, `getPlanSuggest`, `postPlanBaseline` |
| `static/js/views/planning/state.js` | mutable state only |
| `static/js/views/planning/cells.js` | pure derivations (cell state, behind labels, slot rows) — no DOM |
| `static/js/views/planning/render.js` | every DOM write: phase bar, KPIs, matrix, list, burndown, grid, tooltip |
| `static/js/views/planning/editor.js` | the `<dialog>` slot editor |
| `static/js/views/planning/index.js` | listeners, refresh cycle; the only module `main.js` imports |
| `static/js/views/planning.js` | **deleted** |
| `templates/views/planning.html` | rewritten skeleton for the new page |
| `static/css/views.css` | Planning section rewritten |
| `static/js/main.js` | import path, view subtitle, `initPlanning` call |
| `static/js/views/config.js` | a "Remaining" flag column beside "exec" |
| `CLAUDE.md`, `README.md` | Planning section rewritten to match |

---

### Task 1: `remaining` taxonomy flag

**Files:**
- Modify: `tcm/domain/status.py` (constructor ~line 91, `from_dict` ~145–285, `to_dict` ~319)
- Modify: `config/result_status.json` (NYS and Pending entries)
- Modify: `tcm/services/aggregation.py` (`remaining_rows`, end of file)
- Modify: `static/js/views/config.js:175` and `:516`
- Test: `tests/domain/test_status.py`, `tests/services/test_aggregate.py`

**Interfaces:**
- Produces: `STATUS.remaining: list[str]` (taxonomy order, always contains the empty key);
  `STATUS.worked: list[str]` = `[k for k in STATUS.counted if k not in STATUS.remaining]`;
  `STATUS.to_dict()["remaining"]`; `remaining_rows(cases, keep_finished=False)`.

Rules: the empty status is **always** remaining, flagged or not (a blank Result cell is by
definition work not done — a config that predates the flag keeps behaving as before). A status
may not be both `remaining` and `excluded` (work outside the plan is not work to hand out), nor
both `remaining` and `executed` (the burndown would count it on both sides).

- [ ] **Step 1: Write the failing tests** — append to `tests/domain/test_status.py`:

```python
def test_the_empty_status_is_remaining_even_unflagged():
    assert StatusSet.from_dict(MINIMAL).remaining == ["NYS"]


def test_flagged_statuses_are_remaining_in_taxonomy_order():
    cfg = json.loads(json.dumps(MINIMAL))
    cfg["statuses"].insert(1, {"key": "Pending", "match": ["HOLD"], "remaining": True})
    s = StatusSet.from_dict(cfg)
    assert s.remaining == ["Pending", "NYS"]
    # MINIMAL's fallback is not excluded, so it counts, and it is not remaining.
    assert s.worked == ["OK", "Other"]


def test_worked_is_counted_minus_remaining():
    cfg = json.loads(json.dumps(MINIMAL))
    cfg["statuses"][2]["excluded"] = True           # Other outside the plan
    s = StatusSet.from_dict(cfg)
    assert s.worked == ["OK"]


@pytest.mark.parametrize("flag", ["excluded", "executed"])
def test_remaining_cannot_be_combined_with(flag):
    cfg = json.loads(json.dumps(MINIMAL))
    cfg["statuses"][0]["remaining"] = True
    cfg["statuses"][0][flag] = True
    with pytest.raises(ValueError, match="remaining"):
        StatusSet.from_dict(cfg)


def test_shipped_taxonomy_counts_pending_as_remaining():
    assert STATUS.remaining == ["Pending", "NYS"]
    assert "remaining" in STATUS.to_dict()
```

Append to `tests/services/test_aggregate.py` (`case(...)` below stands for that file's existing
`TestCase` builder — use its real name; the defaults put every case on one file and device, scope FPT):

```python
def test_remaining_rows_counts_every_remaining_status():
    rows = remaining_rows([case(result=None), case(result="保留"), case(result="OK", pic="An")])
    assert rows[0]["remaining"] == 2 and rows[0]["total"] == 3


def test_remaining_rows_can_keep_finished_blocks():
    cs = [case(result="OK", pic="An")]
    assert remaining_rows(cs) == []
    assert remaining_rows(cs, keep_finished=True)[0]["remaining"] == 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_status.py tests/services/test_aggregate.py -q`
Expected: FAIL — `AttributeError: 'StatusSet' object has no attribute 'remaining'`.

- [ ] **Step 3: Implement**

In `StatusSet.__init__` add a `remaining: list[str]` parameter (after `review`) and:

```python
        #: Statuses whose cases are still to be run — what the plan hands out
        #: and the burndown counts down. Always includes the empty status.
        self.remaining = remaining
        #: Work that has left the remaining pile: counted, and not remaining.
        #: The planner's "done". Wider than `executed` on purpose — a Cancel
        #: with a PIC is off the pile even though nobody passed or failed it.
        self.worked = [k for k in self.counted if k not in set(remaining)]
```

In `from_dict`, collect `remaining_keys` beside `review_keys` (`if entry.get("remaining"):`), and
after the `excluded_in_review` check:

```python
        for flag, keys in (("excluded", excluded_keys), ("executed", executed_keys)):
            clash = [k for k in remaining_keys if k in set(keys)]
            if clash:
                raise ValueError(
                    f"{source}: status(es) {clash} are both 'remaining' and '{flag}'; "
                    f"a case cannot be work still to do and {flag} at once")
        if empty_keys[0] not in remaining_keys:
            remaining_keys.append(empty_keys[0])
        remaining_keys.sort(key=[s.key for s in statuses].index)
```

Pass `remaining_keys` to `cls(...)`; add `"remaining": list(self.remaining)` to `to_dict()`.

In `config/result_status.json` add `"remaining": true` to the `Pending` and `NYS` objects (keys
stay alphabetical as the file has them).

In `remaining_rows`, replace `unstarted = STATUS.classify(None)` / the `== unstarted` test with
`remaining = set(STATUS.remaining)` / `in remaining`, add the `keep_finished=False` parameter, and
change the filter to `if remaining or keep_finished`. Update its docstring's "Not run is whichever
status the taxonomy marks `empty`" paragraph to say `remaining`.

In `static/js/views/config.js`, after line 175 add
`${flag(i, "remaining", "left", s.remaining, "Still to run — the plan hands it out")}` and add
`case "remaining":` to the `case "executed": …` list at line 516. Add the matching `<th>` in the
config table head wherever the `exec` header is written (grep `"exec"`).

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (fix any test that constructed `StatusSet(...)` positionally).

- [ ] **Step 5: Commit**

```bash
git add config/result_status.json tcm/domain/status.py tcm/services/aggregation.py static/js/views/config.js tests/
git commit -m "Name the statuses that are still to run in the taxonomy"
```

---

### Task 2: Plan settings and working-day arithmetic (domain)

**Files:**
- Modify: `tcm/domain/plan.py`
- Test: `tests/domain/test_plan.py`

**Interfaces:**
- Produces:
  - `PlanSettings(phase_start: str|None, phase_end: str|None, daily_target: int)` frozen dataclass,
    `PlanSettings.from_dict(raw, source="settings")`, `.to_dict()`, `PlanSettings.DEFAULT_TARGET = 30`.
  - `is_workday(iso: str) -> bool`, `workdays(start: str, end: str) -> list[str]` (inclusive, Mon–Fri, capped at 500 days),
    `phase_days(start, end, today) -> list[str]` (workdays plus `today` if it lies in range),
    `add_workdays(iso: str, n: int) -> str`, `shift_workday(iso: str, direction: int) -> str`.

- [ ] **Step 1: Write the failing tests** — append to `tests/domain/test_plan.py`:

```python
from tcm.domain.plan import (PlanSettings, add_workdays, phase_days,
                             shift_workday, workdays)


def test_workdays_skip_weekends():
    # 2026-09-25 is a Friday
    assert workdays("2026-09-25", "2026-09-29") == ["2026-09-25", "2026-09-28", "2026-09-29"]


def test_phase_days_include_today_even_on_a_weekend():
    assert "2026-09-26" in phase_days("2026-09-24", "2026-09-30", today="2026-09-26")


def test_add_workdays_and_shift():
    assert add_workdays("2026-09-25", 1) == "2026-09-28"
    assert shift_workday("2026-09-28", -1) == "2026-09-25"


def test_settings_defaults_and_round_trip():
    s = PlanSettings.from_dict({})
    assert (s.phase_start, s.phase_end, s.daily_target) == (None, None, 30)
    raw = {"phase_start": "2026-09-01", "phase_end": "2026-09-30", "daily_target": 25}
    assert PlanSettings.from_dict(raw).to_dict() == raw


@pytest.mark.parametrize("raw", [
    {"phase_start": "2026-09-30", "phase_end": "2026-09-01"},
    {"daily_target": 0},
    {"daily_target": True},
    {"phase_start": "30/09/2026"},
])
def test_settings_refuse_nonsense(raw):
    with pytest.raises(ValueError):
        PlanSettings.from_dict(raw)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_plan.py -q`
Expected: FAIL — ImportError on `PlanSettings`.

- [ ] **Step 3: Implement** — append to `tcm/domain/plan.py`:

```python
from datetime import timedelta

#: A guard, not a rule: no phase is two years long, and a loop over dates that
#: a typo'd year sent to 9999 must end.
_MAX_DAYS = 500


def is_workday(iso: str) -> bool:
    return _date.fromisoformat(iso).weekday() < 5


def workdays(start: str, end: str) -> list[str]:
    """Every Mon–Fri from `start` to `end` inclusive. No holiday calendar."""
    if not start or not end:
        return []
    d, stop, out = _date.fromisoformat(start), _date.fromisoformat(end), []
    for _ in range(_MAX_DAYS):
        if d > stop:
            break
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def phase_days(start: str, end: str, today: str) -> list[str]:
    """The phase's working days, plus today when today falls inside the phase.

    Somebody testing on a Saturday did work on a phase day as far as the
    burndown is concerned; leaving the day off the axis would drop their cases.
    """
    days = workdays(start, end)
    if start and end and start <= today <= end and today not in days:
        days = sorted(days + [today])
    return days


def add_workdays(iso: str, n: int) -> str:
    d, k = _date.fromisoformat(iso), 0
    for _ in range(_MAX_DAYS * 2):
        if k >= n:
            break
        d += timedelta(days=1)
        if d.weekday() < 5:
            k += 1
    return d.isoformat()


def shift_workday(iso: str, direction: int) -> str:
    d = _date.fromisoformat(iso) + timedelta(days=direction)
    while d.weekday() >= 5:
        d += timedelta(days=direction)
    return d.isoformat()


@dataclass(frozen=True)
class PlanSettings:
    """What the plan is measured against: the phase, and a day's fair load.

    `phase_start` / `phase_end` of None mean "not set yet"; the service fills a
    default rather than storing one, so opening the screen writes nothing.
    `daily_target` is cases per person per day — used only to flag a member
    whose planned day is heavier than that, never to invent a plan.
    """

    phase_start: Optional[str] = None
    phase_end: Optional[str] = None
    daily_target: int = 30

    DEFAULT_TARGET = 30

    @classmethod
    def from_dict(cls, raw, source: str = "settings") -> "PlanSettings":
        if not isinstance(raw, dict):
            raise ValueError(f"{source} must be an object")
        start = raw.get("phase_start")
        end = raw.get("phase_end")
        start = parse_date(start, f"{source}.phase_start") if start else None
        end = parse_date(end, f"{source}.phase_end") if end else None
        if start and end and end < start:
            raise ValueError(f"{source}: the phase ends ({end}) before it starts ({start})")
        target = raw.get("daily_target", cls.DEFAULT_TARGET)
        if isinstance(target, bool) or not isinstance(target, int) or target <= 0:
            raise ValueError(f"{source}: 'daily_target' must be a whole number of "
                             f"cases above zero, got {target!r}")
        return cls(start, end, target)

    def to_dict(self) -> dict:
        return {"phase_start": self.phase_start, "phase_end": self.phase_end,
                "daily_target": self.daily_target}
```

`to_dict` of the defaults returns `{"phase_start": None, "phase_end": None, "daily_target": 30}`;
the round-trip test uses a full dict, so that is consistent. Update the module docstring's opening
paragraph to mention settings.

- [ ] **Step 4: Run**

Run: `.venv/bin/python -m pytest tests/domain/test_plan.py tests/test_layering.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add tcm/domain/plan.py tests/domain/test_plan.py
git commit -m "Add plan settings and working-day arithmetic to the plan domain"
```

---

### Task 3: Store settings in `plan.json`

**Files:**
- Modify: `tcm/domain/ports.py` (`PlanRepository`, ~line 144)
- Modify: `tcm/infrastructure/plan/json_store.py`
- Modify: fakes in `tests/services/test_planning.py` and `tests/web/test_api_planning.py`
- Test: `tests/infrastructure/test_plan_store.py`, `tests/domain/test_ports.py` (unchanged assertion, must still pass)

**Interfaces:**
- Consumes: `PlanSettings` (Task 2).
- Produces: `PlanRepository.settings() -> PlanSettings`, `PlanRepository.put_settings(s: PlanSettings) -> None`.
  File shape becomes `{"version": 1, "days": {...}, "settings": {...}}`; a file without `settings` reads as defaults (no version bump — the key is additive).

- [ ] **Step 1: Write the failing tests** — append to `tests/infrastructure/test_plan_store.py`
  (use the file's existing repo-building fixture/helper):

```python
def test_settings_default_when_the_file_has_none(repo):
    assert repo.settings() == PlanSettings()


def test_settings_round_trip_without_touching_days(repo):
    repo.put_day(DayPlan.from_dict("2026-09-25", {"entries": [
        {"pic": "An", "file": "TC.xlsx", "device": "iPhone", "planned": 3}]}))
    repo.put_settings(PlanSettings("2026-09-01", "2026-09-30", 25))
    assert repo.settings() == PlanSettings("2026-09-01", "2026-09-30", 25)
    assert repo.day("2026-09-25").planned_total == 3


def test_saving_a_day_keeps_the_settings(repo):
    repo.put_settings(PlanSettings("2026-09-01", "2026-09-30", 25))
    repo.put_day(DayPlan.empty("2026-09-25"))
    assert repo.settings().daily_target == 25
```

(If the file has no `repo` fixture, add one: `JsonPlanRepository(JsonFileConfigRepository(), str(tmp_path / "plan.json"))`.)

- [ ] **Step 2: Run** → FAIL (`AttributeError: settings`).

- [ ] **Step 3: Implement**

`ports.py`: add to `PlanRepository`

```python
    def settings(self):
        ...

    def put_settings(self, settings) -> None:
        ...
```

and a sentence in its docstring: settings are one record, not per day.

`json_store.py`: change `_read` to return the whole document (`{"days": ..., "settings": ...}`)
and `_write(doc)` to write it, so neither save can drop the other's half:

```python
    def settings(self) -> PlanSettings:
        raw = self._read().get("settings") or {}
        return PlanSettings.from_dict(raw, source=f"{os.path.basename(self._path)}[settings]")

    def put_settings(self, settings: PlanSettings) -> None:
        doc = self._read()
        doc["settings"] = settings.to_dict()
        self._write(doc)
```

`day`, `days`, `put_day` read `self._read()["days"]` and `put_day` writes back via
`doc["days"] = days; self._write(doc)`. `_read` returns `{"days": raw.get("days", {}), "settings": raw.get("settings")}`
(validate `settings` is a dict or absent, same message style). `_write` emits
`{"version": SCHEMA_VERSION, "days": doc["days"], **({"settings": doc["settings"]} if doc.get("settings") else {})}`.
Update the "Shape on disk" docstring.

Both `FakePlanRepository` classes in the tests gain:

```python
    _settings = None

    def settings(self):
        return self._settings or PlanSettings()

    def put_settings(self, settings):
        self._settings = settings
```

- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add tcm/domain/ports.py tcm/infrastructure/plan/json_store.py tests/
git commit -m "Keep the plan settings in plan.json beside the days"
```

---

### Task 4: `phase_view` and `board_view` in the planning service

**Files:**
- Modify: `tcm/services/planning.py`
- Test: `tests/services/test_planning.py`

**Interfaces:**
- Consumes: `STATUS.remaining`, `STATUS.worked` (Task 1); `remaining_rows(cases, keep_finished=True)`;
  `daily_rows(cases)`; `PlanSettings`, `phase_days`, `add_workdays`, `workdays` (Task 2); `repo.settings()` (Task 3).
- Produces (all JSON-ready dicts; "slot" = `{"file", "device"}`):

`PlanningService.get_settings() -> dict` — the stored settings with defaults filled:
`{"phase_start", "phase_end", "daily_target", "stored": bool}`. Defaults: `phase_start` = earliest
`test_date` among the cases, else today; `phase_end` = `add_workdays(today, 5)`. Needs the cases, so
the signature is `get_settings(cases)`.

`PlanningService.save_settings(raw: dict) -> PlanSettings` — validates through
`PlanSettings.from_dict`, stores, returns.

`PlanningService.phase_view(cases, window="5") -> dict`:

```text
{
  "today": "YYYY-MM-DD",
  "settings": {...get_settings...},
  "phase": {"days": [..phase_days..], "left": int},          # left = days >= today
  "kpis": {
     "remaining": int, "at_start": int,                      # R0
     "planned_today": int, "done_today": int, "members_today": int,
     "needed_pace": int|None,                                # ceil(remaining/left), None if left == 0
     "plan_finish": "YYYY-MM-DD"|None, "unplanned": int,     # date the plan covers remaining; None = not covered
     "forecast_finish": "YYYY-MM-DD"|None, "rate": float, "window_days": int
  },
  "burndown": {"axis": [dates], "plan": [n...], "actual": [n...], "forecast": [n...],
               "today_index": int, "end_index": int, "y_max": int},
  "grid": {"days": [dates],                                   # phase_days to max(phase_end, last plan date), capped at phase_end+20 workdays
           "slots": [{"file", "device", "remaining", "remaining_at_start",
                      "cells": {date: {"planned": int, "worked": int, "over_remaining": bool, "pics": [[pic, n]]}}}],
           "planned_by_date": {date: int}, "worked_by_date": {date: int}}
}
```

`PlanningService.board_view(cases, date) -> dict`:

```text
{
  "date", "today", "daily_target",
  "entries": [{pic, file, device, planned}],                  # the stored day, verbatim — the editor rebuilds from it
  "slots": [{"file", "device", "remaining", "remaining_at_start",
             "planned_other_days": int,                       # plans on this slot, date >= today, date != `date`
             "need_through": int,                             # plans on this slot, today <= d' <= date (0 if date < today)
             "over_by": int}],                                # max(0, need_through - remaining_at_start)
  "cells": [{"pic", "file", "device", "planned": int, "worked": int}],   # planned rows + worked-without-plan rows
  "load": {pic: int},                                         # the member's planned total that day
  "members": [pic],                                           # every PIC in the load + every PIC in any plan, sorted, no "N/A"
  "available": [{"file", "device", "remaining_at_start"}]     # slots with work left and not already on this day — the "Add file" list
}
```

Definitions, copied from the design and made exact:

- **worked** on (date, pic, slot) = `sum(row[k] for k in STATUS.worked)` over the `daily_rows` row with that key. Never counted from cases.
- **remaining** per slot = `remaining_rows(cases, keep_finished=True)`.
- **remaining_at_start** (start of *today*) = remaining + worked today on that slot (design `remStartS`).
- **at_start (R0)** = counted in-plan total − worked on undated days or before `phase_start` (design `R0 = all − execBefore`).
- **rate** = mean worked per past phase day over the last `window` past phase days (`"all"` = every past phase day); if there are none, today's worked total.
- **forecast_finish** = today if remaining == 0, else `add_workdays(today, ceil(remaining / rate))` if rate > 0, else None.
- **plan_finish**: consume, per file, `min(today's still-to-run plan, remaining)` then future plans in date order capped per file by remaining (design lines 430–436); the date remaining is covered, else None with `unplanned` = what is left.
- **burndown**: axis = `phase_days(start, axis_end, today)` where `axis_end` = max(phase_end, forecast_finish, plan_finish, last plan date) capped at `add_workdays(phase_end, 20)`; `plan[i]` = max(0, R0 − cumulative planned through axis[i]); `actual[i]` for axis[i] <= today = max(0, R0 − cumulative worked); `forecast` starts at today's actual and falls by `rate` per later day while > 0. Each series has a leading R0 point at index 0 (the design's `X(0)`), so `len(plan) == len(axis) + 1`.
- **over_remaining** in a grid cell: date >= today, planned > 0, and the slot's cumulative plan from today through that date > remaining_at_start.
- Slots in the grid/board = the union of remaining slots with work left, planned slots, and slots worked in range — ordered by the load's file order (first appearance in `remaining_rows(..., keep_finished=True)` sorted by file then device), with unknown files (a plan for a file no longer loaded) last.

- [ ] **Step 1: Write the failing tests** — append to `tests/services/test_planning.py`
  (uses the file's `service`, `entry`, `case` helpers; `today` = 2026-09-22, a Tuesday):

```python
def _load():
    return ([case(row_num=i) for i in range(10)]                                   # 10 NYS
            + [case(row_num=20 + i, result="OK", pic="An", test_date="2026-09-21") for i in range(4)]
            + [case(row_num=30 + i, result="OK", pic="An", test_date="2026-09-22") for i in range(2)])


def test_board_joins_plan_to_worked_and_reports_remaining_at_start():
    svc = service()
    svc.save_settings({"phase_start": "2026-09-21", "phase_end": "2026-09-25"})
    svc.save_day("2026-09-22", [entry(pic="An", planned=5), entry(pic="Bo", planned=4)])
    b = svc.board_view(_load(), "2026-09-22")
    slot = b["slots"][0]
    assert (slot["remaining"], slot["remaining_at_start"]) == (10, 12)
    assert slot["need_through"] == 9 and slot["over_by"] == 0
    cell = {c["pic"]: c for c in b["cells"]}
    assert (cell["An"]["planned"], cell["An"]["worked"]) == (5, 2)
    assert b["load"] == {"An": 5, "Bo": 4}


def test_board_flags_a_plan_bigger_than_what_is_left():
    svc = service()
    svc.save_day("2026-09-22", [entry(pic="An", planned=20)])
    assert svc.board_view(_load(), "2026-09-22")["slots"][0]["over_by"] == 8


def test_board_keeps_a_slot_whose_file_is_no_longer_loaded():
    svc = service()
    svc.save_day("2026-09-22", [entry(file="Gone.xlsx", planned=3)])
    slots = svc.board_view(_load(), "2026-09-22")["slots"]
    gone = [s for s in slots if s["file"] == "Gone.xlsx"][0]
    assert gone["remaining"] == 0 and gone["over_by"] == 3


def test_worked_without_a_pic_counts_but_is_not_a_member():
    svc = service()
    cs = _load() + [case(row_num=99, result="OK", test_date="2026-09-22")]
    b = svc.board_view(cs, "2026-09-22")
    assert "N/A" not in b["members"]
    assert sum(c["worked"] for c in b["cells"]) == 3


def test_phase_view_kpis():
    svc = service()
    svc.save_settings({"phase_start": "2026-09-21", "phase_end": "2026-09-25"})
    svc.save_day("2026-09-22", [entry(planned=5)])
    svc.save_day("2026-09-23", [entry(planned=5)])
    k = svc.phase_view(_load())["kpis"]
    assert (k["remaining"], k["at_start"]) == (10, 16)
    assert (k["planned_today"], k["done_today"]) == (5, 2)
    assert k["needed_pace"] == 3                       # 10 left over Tue..Fri = 4 days
    # Today contributes only what is still to run (5 planned - 2 done = 3), then
    # Wednesday's 5: 8 of 10 covered, so the plan does not finish the phase.
    assert k["plan_finish"] is None and k["unplanned"] == 2
    # Monday is the only past phase day: 4 worked -> 4/day; 10 / 4 -> 3 workdays after Tue.
    assert k["rate"] == 4.0 and k["forecast_finish"] == "2026-09-25"


def test_no_execution_means_no_forecast():
    svc = service()
    svc.save_settings({"phase_start": "2026-09-22", "phase_end": "2026-09-25"})
    k = svc.phase_view([case(row_num=i) for i in range(5)])["kpis"]
    assert k["forecast_finish"] is None and k["plan_finish"] is None and k["unplanned"] == 5


def test_burndown_series_start_at_r0_and_reconcile():
    svc = service()
    svc.save_settings({"phase_start": "2026-09-21", "phase_end": "2026-09-25"})
    b = svc.phase_view(_load())["burndown"]
    assert b["actual"][0] == 16 and b["actual"][-1] == 10
    assert len(b["plan"]) == len(b["axis"]) + 1


def test_empty_workspace_is_zeros_not_an_error():
    v = service().phase_view([])
    assert v["kpis"]["remaining"] == 0 and v["grid"]["slots"] == []
    assert service().board_view([], "2026-09-22")["slots"] == []


def test_settings_default_from_the_load():
    s = service().get_settings(_load())
    assert s["phase_start"] == "2026-09-21" and s["phase_end"] == "2026-09-29" and not s["stored"]
```

- [ ] **Step 2: Run** → FAIL (`AttributeError: phase_view`).

- [ ] **Step 3: Implement** in `tcm/services/planning.py`. Add a private helper that every
  figure reads from, so the two views cannot disagree:

```python
def _worked(row: dict) -> int:
    """Cases of a `daily_rows` row that have left the remaining pile."""
    return sum(row.get(key, 0) for key in STATUS.worked)


class _Facts:
    """Everything both planner views read, computed once per request."""

    def __init__(self, cases, days, today):
        self.today = today
        self.rem = {}           # (file, device) -> remaining
        self.total = 0          # counted, in plan
        order = []
        for r in remaining_rows(cases, keep_finished=True):
            self.rem[(r["file"], r["device"])] = r["remaining"]
            self.total += r["total"]
            order.append(r["file"])
        self.files = sorted(set(order))
        self.worked = defaultdict(int)       # (date, pic, file, device) -> n ; date may be None
        for row in daily_rows(cases):
            n = _worked(row)
            if n:
                self.worked[(row["date"], row["pic"], row["file"], row["device"])] += n
        self.plans = [(d.date, e) for d in days for e in d.entries]

    def worked_on(self, date, slot=None, pic=None):
        return sum(n for (d, p, f, dv), n in self.worked.items()
                   if d == date and (slot is None or (f, dv) == slot) and (pic is None or p == pic))

    def remaining_at_start(self, slot):
        return self.rem.get(slot, 0) + self.worked_on(self.today, slot)

    def slot_order(self, slots):
        known = {f: i for i, f in enumerate(self.files)}
        return sorted(slots, key=lambda s: (s[0] not in known, known.get(s[0], 0), s[0], s[1]))
```

Then write `get_settings`, `save_settings`, `phase_view`, `board_view` following the definitions
above, translating `planVals()` in `design/planning/component.js` (KPIs lines 423–451 and 620–631;
grid lines 463–532; slot figures lines 312–351; editor figures lines 553–617 feed
`planned_other_days`). Keep each public method under ~60 lines by pulling `_burndown`,
`_plan_finish`, `_grid` into private functions. `members` excludes `"N/A"` (what `daily_rows` names
a blank PIC). Use `math.ceil` for needed pace and forecast.

Remove `person_view`, `suggest` and `rebaseline` and their tests in the same file (decision 1);
keep `save_day`'s lazy baseline, `day_view` and `calendar_view` (Daily/Productivity still read the
calendar). Update the module docstring: the "three cuts" paragraph becomes the phase + board pair.

- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add tcm/services/planning.py tests/services/test_planning.py
git commit -m "Compute the phase and day-board figures the planner draws"
```

---

### Task 5: Endpoints

**Files:**
- Modify: `tcm/web/blueprints/plan.py`
- Test: `tests/web/test_api_planning.py`

**Interfaces:**
- Consumes: Task 4 service methods.
- Produces:
  - `GET /api/plan/phase?window=3|5|10|all` → `phase_view` (400 on any other window).
  - `GET /api/plan/board/<date>` → `board_view` (400 on a bad date).
  - `GET /api/plan/settings` → `get_settings(cases)`; `PUT /api/plan/settings` body `{phase_start, phase_end, daily_target}` → the stored settings, 400 with the domain message.
  - Unchanged: `GET /api/plan` (calendar), `GET/PUT /api/plan/<date>`.
  - Removed: `/api/plan/suggest`, `/api/plan/person/<pic>`, `POST /api/plan/<date>/baseline`.

Route order matters: register `/api/plan/phase`, `/api/plan/settings` and `/api/plan/board/<date>`
**before** `/api/plan/<date>`, or Flask matches `phase` as a date and answers 400.

- [ ] **Step 1: Write the failing tests** (the file's `client` fixture pins today to 2026-08-05):

```python
def test_phase_answers_with_nothing_loaded(client):
    r = client.get("/api/plan/phase")
    assert r.status_code == 200 and r.get_json()["kpis"]["remaining"] == 0


def test_phase_refuses_an_unknown_window(client):
    assert client.get("/api/plan/phase?window=7").status_code == 400


def test_board_answers_with_nothing_loaded(client):
    r = client.get("/api/plan/board/2026-08-05")
    assert r.status_code == 200 and r.get_json()["slots"] == []


def test_settings_round_trip_and_refusal(client):
    ok = client.put("/api/plan/settings", json={"phase_start": "2026-08-03",
                                                "phase_end": "2026-08-14", "daily_target": 25})
    assert ok.status_code == 200
    assert client.get("/api/plan/settings").get_json()["daily_target"] == 25
    bad = client.put("/api/plan/settings", json={"phase_start": "2026-08-14", "phase_end": "2026-08-03"})
    assert bad.status_code == 400 and "before it starts" in bad.get_json()["error"]


def test_removed_routes_are_gone(client):
    assert client.get("/api/plan/suggest?date=2026-08-05").status_code in (400, 404)
    assert client.get("/api/plan/person/An").status_code == 404
```

Delete the existing tests for suggest / person / baseline.

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement** the four routes as `jsonify` wrappers, each catching `ValueError` →
  `({"error": str(e)}, 400)`, the file's existing pattern. `window` is validated in the route:
  `if window not in {"3", "5", "10", "all"}: return 400`. Delete the three removed routes. Update
  the blueprint docstring.

- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add tcm/web/blueprints/plan.py tests/web/test_api_planning.py
git commit -m "Serve the phase, the day board and the plan settings"
```

---

### Task 6: `api.js` and the view skeleton

**Files:**
- Modify: `static/js/api.js` (plan section, ~lines 279–360)
- Rewrite: `templates/views/planning.html`
- Create: `static/js/views/planning/{state,cells,render,editor,index}.js` (stubs this task, filled in 7–9)
- Delete: `static/js/views/planning.js`
- Modify: `static/js/main.js` (import at line 30, `VIEWS.planning.sub` at line 58, `initPlanning` call at line 209)

**Interfaces:**
- Produces in `api.js` (each returns `{ok, json}` like its neighbours):
  `getPlanPhase(window)`, `getPlanBoard(date)`, `getPlanSettings()`, `putPlanSettings(settings)`.
  Keep `getPlanCalendar`, `getPlanDay`, `putPlanDay`. Delete `getPlanPerson`, `getPlanSuggest`, `postPlanBaseline`.
- Produces in `views/planning/index.js`: `export function initPlanningView()` (bind once) and
  `export async function initPlanning()` (called after every load; no argument any more — members come from the board).

Template — one section, ids the render module fills:

```html
        <!-- ==================== Planning ====================
             The phase, what each day hands out, and how it is going. The Day
             plan is the only part that edits; the burndown and the phase grid
             report on it. -->
        <section class="view" id="planningView" hidden>
            <div class="plan-phase" id="planPhase"></div>          <!-- start → end, info, target -->
            <div class="stat-grid plan-kpis" id="planKpis"></div>

            <section class="card card--table" id="day-plan">
                <div class="card-head card-head--row" id="planDayHead"></div>
                <p class="empty-note is-error" id="planDayError" hidden></p>
                <p class="card-note" id="planUnplannedNote" hidden></p>
                <div class="scroll-x" id="planMatrix"></div>
                <div class="scroll-x scroll-x--rows" id="planList" hidden></div>
            </section>

            <section class="card" id="planBurn">
                <div class="card-head card-head--row" id="planBurnHead"></div>
                <div class="plan-burn" id="planBurnChart"></div>
                <p class="card-note" id="planBurnNote"></p>
            </section>

            <section class="card card--table" id="planGrid">
                <div class="card-head card-head--row" id="planGridHead"></div>
                <div class="scroll-x" id="planGridTable"></div>
            </section>

            <div class="plan-tip" id="planTip" role="tooltip" hidden></div>

            <dialog class="plan-editor" id="planEditor"></dialog>
        </section>
```

- [ ] **Step 1:** Write the four `api.js` functions after `putPlanDay`, copying `getPlanDay`'s shape.
  `getPlanPhase(window = "5")` → `fetch(\`/api/plan/phase?window=${encodeURIComponent(window)}\`)`.
  `putPlanSettings(s)` → `PUT /api/plan/settings` with JSON body. Delete the three removed functions.
- [ ] **Step 2:** Replace `templates/views/planning.html` with the skeleton above.
- [ ] **Step 3:** `git rm static/js/views/planning.js`; create the five modules. `state.js` holds:

```js
/** Planning state. Declares mutable state and nothing else — see views/detail/state.js. */
let day = null;          // "YYYY-MM-DD" the Day plan is on; null until first init
let layout = "matrix";   // "matrix" | "list"
let fcWindow = "5";      // "3" | "5" | "10" | "all"
let gridOffset = null;   // first visible grid column; null = centred on today
let focus = null;        // {slot: index} highlighted after a grid click, cleared after 3.2s
export const expanded = new Set();          // grid files shown per device (file names; never via the DOM)
export const listSort = { key: "pic", dir: "asc" };
export const listFilter = { pic: "", file: "", status: "" };
export const data = { phase: null, board: null };

export const getDay = () => day;          export const setDay = (v) => { day = v; };
export const getLayout = () => layout;    export const setLayout = (v) => { layout = v; };
export const getWindow = () => fcWindow;  export const setWindow = (v) => { fcWindow = v; };
export const getGridOffset = () => gridOffset; export const setGridOffset = (v) => { gridOffset = v; };
export const getFocus = () => focus;      export const setFocus = (v) => { focus = v; };
```

  `index.js` for now: `initPlanningView()` no-ops, `initPlanning()` fetches phase + board into
  `data` and calls `render()` which writes `JSON.stringify` placeholders — replaced in Task 7.
- [ ] **Step 4:** `main.js`: `import { initPlanning, initPlanningView } from "./views/planning/index.js";`
  (full path — a browser resolves no directory index); `await initPlanning();`; subtitle:
  `"The phase, what each day hands out and how it is going. Click a cell to change a day's plan."`
- [ ] **Step 5: Verify** — `.venv/bin/python -m pytest -q` passes (`test_app.py` renders the
  template). Syntax-check each module: `for f in static/js/views/planning/*.js static/js/api.js static/js/main.js; do cp $f /tmp/x.mjs && node --check /tmp/x.mjs || echo BAD $f; done`.
  Run the app (`.venv/bin/python app.py`), load `samples/generated` (generate with the sample tool if absent), open Planning: the raw JSON placeholders render, no console errors.
- [ ] **Step 6: Commit** — `git commit -m "Swap the Planning view for the new page's skeleton"`.

---

### Task 7: Phase bar, KPIs and the Day plan (matrix + list)

**Files:**
- Modify: `static/js/views/planning/{cells,render,index}.js`
- Modify: `static/css/views.css` (Planning section)

**Interfaces:**
- Consumes: `data.board`, `data.phase` from Task 6; `putPlanSettings`, `putPlanDay`, `getPlanCalendar` + `setPlanCalendar` from `plan.js` (so Daily/Productivity hear a save).
- Produces in `cells.js` (pure, no DOM — `render.js` and `editor.js` both import it):
  - `cellState(planned, worked, { past, today, future }) -> "empty"|"unplanned"|"future"|"nys"|"wip"|"done"|"exceeded"` — design lines 361–362.
  - `behind(planned, onPlan, { date, today }) -> {text, kind: ""|"ok"|"togo"|"missed"}` — design lines 331–336.
  - `slotRows(board) -> [{file, device, fileLabel, first, remaining, remainingAtStart, needThrough, overBy, cells:[{pic, planned, worked, state, pct, over}], planned, worked, onPlan, behind}]`.
  - `memberTotals(board, rows) -> [{pic, planned, worked, onPlan, behind, overTarget: bool}]` (`overTarget` = `board.load[pic] > board.daily_target`).
  - `shortFile(name)` — design line 31.

Behaviour to reproduce (design `planVals` lines 312–421 and markup lines 1–118 of `design/planning/planning-markup.html`):

1. **Phase bar**: two `<input type="date">` (start, end), "N working days · M left incl. today", and a
   "Target / member / day" number input. Any change → `putPlanSettings` → refetch phase and board.
2. **KPIs** — five `stat-card`s: Remaining (`of R0 at phase start`), Planned today (`n done · m members`),
   Needed pace (`n/day`, `to finish by <end>`), Current plan completes (date or "Not covered",
   `within phase` / `after phase end` / `n cases unplanned`), Forecast finish (`at r/day · last n days`).
   Tone: plan/forecast after phase end or None → `--tone-danger`; within → `--tone-success`. Others ink.
3. **Day head**: "Day plan", a badge Today / Past / Upcoming, the behind chip, the headline
   (`Fri 09-25 · 42 planned · 30 done · 4 members · 3 files · 2 iPhone · 1 iPad`), ‹ date › Today,
   **+ Add file** (opens editor in add mode — Task 8), Matrix | List toggle (`.toggle` pair).
4. **Matrix** (`<table class="ledger plan-matrix">`): rows = slots (file label only on the first row
   of each file; a 2px rule between files), columns = `board.members` that have a plan or worked
   that day (all members when none), then Total. Slot header cell shows device, `need / remaining left`
   (past days: `remaining left`) and `over by n` in `--tone-danger`. Each cell is a `<button>` carrying
   `data-r` (row index) and `data-c` (member index): text `worked / planned` (future: `planned`;
   empty: `+`), a state label (Planned / NYS / WIP / Done / Exceeded / Unplanned), and a progress fill
   `linear-gradient(90deg, var(--fill) pct%, var(--base) pct%)`. Fills by state: done →
   `--tone-success-bg`, exceeded → `--tone-success` at reduced mix, wip → `--tone-neutral-bg`, unplanned →
   `--tone-warn-bg`; an over-remaining slot turns the cell `--tone-danger-bg`. Footer row: member
   totals (`worked / planned`, behind text, a member whose load exceeds the target in `--tone-warn`),
   day total. With no slots at all: one "Test case · choose file" column whose cells open add mode.
   A cell or slot-header click → `openEditor(rowIndex, memberIndex)` (Task 8). Unplanned-run note under
   the head when any cell is `unplanned`.
5. **List** (`.scroll-x--rows`): sortable columns Member / File / Device / Planned / Done / Left
   (`sortableTh` + `makeSortable` — generated head, so bind it on each head render), a filter row of
   three selects (member, file, status: All / Planned / Not planned / Exceeds remaining) and Clear.
   Planned rows: number input (change → rewrite that entry in `board.entries`, `putPlanDay`) and
   Remove; unplanned rows: "Add to plan" (→ editor for that slot/member).
6. Every save: `putPlanDay(date, entries)` → on `ok`, refetch board + phase and `getPlanCalendar()` →
   `setPlanCalendar(...)`; on failure show the message in `#planDayError` and keep the edit in the inputs.

- [ ] **Step 1:** Write `cells.js`, translating the design lines named above. No DOM, no `fetch`.
- [ ] **Step 2:** Write `renderPhase`, `renderKpis`, `renderDayHead`, `renderMatrix`, `renderList` in
  `render.js`, all through `esc()` for names; bind their listeners in `index.js`
  (delegated on `#planMatrix` / `#planList` / `#planDayHead`, reading `data-r`/`data-c` indices).
- [ ] **Step 3:** CSS: `.plan-phase`, `.plan-kpis`, `.plan-matrix` (sticky first two columns, `--r-sm`
  cells, `.num` figures), `.plan-cell[data-state=…]` fills, `.plan-cell--over`, `.plan-badge`. Buttons
  use existing `.btn` / `.btn-sm` / `.toggle` — no green primary.
- [ ] **Step 4: Verify in the app** (light and dark theme): switch day with ‹ › and Today; Past/Today/
  Upcoming badges; edit a count in List → Matrix shows it; plan more than remaining → slot shows
  "over by n" in red; change phase dates → KPIs move; set the target below a member's load → that
  member's total turns warn. Reload the page: edits persisted (`~/.test-management/plan.json`).
- [ ] **Step 5: Commit** — `git commit -m "Draw the phase, the KPIs and the day plan"`.

---

### Task 8: The slot editor `<dialog>`

**Files:**
- Modify: `static/js/views/planning/{editor,index}.js`, `static/css/views.css`

**Interfaces:**
- Consumes: `data.board`, `cells.js`, `putPlanDay`.
- Produces: `openEditor({slot: {file, device}|null, focusPic: string|null, isNew: bool})` and
  `closeEditor()` exported from `editor.js`; `index.js` passes a `onSaved` callback that runs the save
  cycle from Task 7 step 6.

Behaviour (design lines 226–264 and 553–617; markup lines 280–448):

- `<dialog id="planEditor">` opened with `showModal()`; Escape and the backdrop close it (listen for
  `click` on the dialog itself where `event.target === dialog`). Framed by a hairline and `--r-lg`,
  `--shadow-2` — the one floating surface in the app (note it in CLAUDE.md, Task 10).
- Title `Login · iPhone` / sub `Fri 09-25 · <full file name>`; add mode: "Add file to plan", with File
  and Device selects built from `board.available` (`<file> · n left`); picking a file with one device
  selects it.
- Stats: Remaining (`remaining_at_start`), Other days (`planned_other_days`), Planned this day (sum of
  inputs). Status line: past day → "Past day · counts are for the record only."; over → "Over remaining
  by n. Trim this day to budget." with **Fit to remaining** (design `edFit`: keep what is already done
  today per member, share the rest of the budget top-down); else "Fits · n remaining cases still unplanned."
- Rows: every member already on that slot that day, plus members who worked it, plus `focusPic`; each:
  name, Done, a number input (changed → `--tone-warn-bg` and "was n"), Day load `load / target`
  (over target → `--tone-warn`), × remove. "+ Add member" select from `board.members` not yet listed.
  "Clear file from this day" sets every input to 0.
- Save: `entries = board.entries` minus rows on this slot, plus one row per member with a count > 0 →
  `putPlanDay`. A row with a count of 0 is dropped (the domain refuses `planned <= 0`). Save disabled
  until a file and device are chosen.

- [ ] **Step 1:** Implement `editor.js` holding its working rows in a module-local array (indices in
  `data-i`, never the PIC).
- [ ] **Step 2:** CSS `.plan-editor`, `.plan-editor::backdrop` (ink at low alpha via `color-mix`), rows grid.
- [ ] **Step 3: Verify in the app:** open from a cell (member pre-focused), from a slot header, and from
  + Add file; Fit to remaining trims to the budget; Save persists and the matrix updates; Cancel/Escape
  leaves the plan unchanged; dark mode legible.
- [ ] **Step 4: Commit** — `git commit -m "Edit one file and device of a day in a dialog"`.

---

### Task 9: Burndown and phase grid

**Files:**
- Modify: `static/js/views/planning/{render,index}.js`, `static/css/views.css`

**Interfaces:**
- Consumes: `data.phase.burndown`, `data.phase.grid`, `data.phase.kpis`, state `fcWindow`, `gridOffset`, `expanded`, `focus`.

Behaviour:

- **Burndown** (design lines 438–461, markup "Burndown · remaining cases"): inline SVG
  `viewBox="0 0 1000 280" preserveAspectRatio="none"` with `vector-effect: non-scaling-stroke`, drawn in
  a CSS-positioned box with y ticks (0, ¼…¹ of `y_max`, `niceMax` from design line 33) and x ticks every
  `ceil(n/9)` days. Plan = dashed `--ink-3`; Actual = solid `--ink`; Forecast = dotted `--ink-2`. Today
  and Phase end are vertical rules with labels. Legend + "Pace from 3d/5d/10d/All" toggles
  (change → `setWindow` → refetch phase only). Note: "At r cases/day (last n days), the remaining N cases
  finish on <day>, k working days after phase end." in `--tone-danger` when late or no forecast, else
  `--tone-success` — the one place status tone colours the chart, because it *is* on-time/late.
  Colours are read from CSS variables, so a theme change needs only a re-render (listen through `onThemeChange` in `theme.js`).
- **Phase grid** (design lines 463–532, markup "Phase plan"): 10-day window starting at
  `gridOffset ?? todayIndex − 3`, ‹ Today › shift by 5. Columns: File, Left, then days (`Fri` / `09-25`;
  today tinted, the Day-plan day inverted ink). File rows (collapsed) sum their device slots; ▸/▾ expands
  (state in `expanded`, "Show devices / Collapse devices" toggles all). Cell: past = worked, future =
  planned; classes `on` / `over` / `under` / `wip` / `unplanned` / `future` mapped to success / success-strong /
  danger / neutral / warn / paper backgrounds; a future cell whose cumulative plan exceeds what is left gets a
  1.5px `--tone-danger` inset ring. Footer rows Planned and Executed (Executed red when below plan).
- **Tooltip** `#planTip`: on `mouseenter` of a non-empty cell, per-device Plan / Actual table, status
  text, "Click to open in Day plan"; positioned from the cell's `getBoundingClientRect`, flipped below
  when near the top.
- **Click** a cell or a day header → `setDay(date)`, layout matrix, fetch board, scroll `#day-plan` into
  view, highlight the matching slot rows for 3.2s (`focus`, `--tone-warn-bg` + an inset left rule).

- [ ] **Step 1:** `renderBurndown` and `renderGrid` in `render.js`; listeners in `index.js`.
- [ ] **Step 2:** CSS `.plan-burn`, `.plan-grid`, `.plan-grid-cell--*`, `.plan-tip`.
- [ ] **Step 3: Verify in the app:** window toggles move the forecast line and the KPI; grid paging stops
  at the ends; expanding a file shows its devices; hover shows the tooltip; clicking a future cell jumps to
  that day with the slot highlighted; toggle theme — chart recolours.
- [ ] **Step 4: Commit** — `git commit -m "Draw the burndown and the phase grid"`.

---

### Task 10: Documentation and final pass

**Files:**
- Modify: `CLAUDE.md` (the Planning section; "Frontend state ownership"; the "no floating surface" sentence in the curvature/framing paragraph; the ports section's `PlanRepository` sentence — now five methods), `README.md` (Planning part, Vietnamese).
- Modify: `static/css/views.css` — delete the now-unused `.plan-split` / `.plan-bar*` rules.

- [ ] **Step 1:** Rewrite CLAUDE.md's Planning section to describe: the `remaining` flag and `worked`
  (and why planning's "done" is wider than "Executed"); plan settings in `plan.json`; the phase and board
  endpoints; that the target returned only as the day-load yardstick; the `<dialog>` as the one floating
  surface; `views/planning/` as a four-module package with `cells.js` as its derivation layer. Remove the
  paragraphs about the suggestion table, the Person cut and "three cuts".
- [ ] **Step 2:** `grep -rn "planning.js\|getPlanSuggest\|getPlanPerson\|postPlanBaseline\|plan-split\|planCut" static templates tcm tests CLAUDE.md` → no hits.
- [ ] **Step 3:** `.venv/bin/python -m pytest -q` → PASS; one last walk through the app on the sample workbooks, both themes, narrow window (tables scroll inside their panes).
- [ ] **Step 4: Commit** — `git commit -m "Record the redesigned planner in CLAUDE.md and the README"`.
