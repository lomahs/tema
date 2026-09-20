# Python Layered Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the Python server into one `tcm/` package of four layers — domain, services, infrastructure, web — with `Protocol` ports at the six I/O boundaries, changing no behaviour.

**Architecture:** Phase 1 is a pure move: `git mv` one layer per commit, inward-most first, rewriting imports mechanically and verifying with the full suite after each. Phase 2 then writes `domain/ports.py`, lifts the module-level `_data` / `_auth` / `_login` state out of the blueprint into `Workspace` and `IdentityService` objects, and splits the 506-line `api/routes.py` into five resource blueprints wired by a composition root in `create_app`.

**Tech Stack:** Python 3.14, Flask, pandas + openpyxl, msal + requests, pytest. No build step, no linter, no JS test framework.

**Spec:** `docs/superpowers/specs/2026-09-20-project-restructure-design.md`

## Global Constraints

- Run every command with the project venv: `.venv/bin/python`. Never bare `python`.
- **Invoke git as `/usr/bin/git`, always.** A shell hook rewrites bare `git` to `rtk git`, and this worktree-isolated session refuses that wrapper — every bare `git` command fails with a refusal, not a git error. This applies to every command in this plan: read `/usr/bin/git mv`, `/usr/bin/git add`, `/usr/bin/git commit` wherever the steps below write `git`.
- **Do not put the word `git` inside a heredoc passed to `python`/`bash -c`.** The same guard refuses it. Write such a script to a file first, then run the file.
- The work happens in the worktree `.claude/worktrees/layered-restructure` on branch `refactor/layered-architecture`. `.venv` there is a symlink to the main checkout's; it is excluded via `.git/info/exclude`, so never `git add` it.
- **The suite must read `450 passed` after every task.** It is green at commit `d7fdb32`. A task that leaves it red is not done.
- **Phase 1 contains no logic edits.** Not a docstring fix, not a rename, not an obvious tidy. Only import lines, file paths and module locations change. A module that is wrong stays wrong; it gets its own commit after phase 1.
- **Move files with `git mv`**, never delete-and-create — rename detection is what makes the diff reviewable.
- Status keys, scope keys and device names are never hard-coded in Python. They come from the JSON configs.
- Docstring style is Google; comments say *why*, not *what*. Match the surrounding code.
- No new dependency is added by this plan.
- One task, one commit. Every commit ends with the `Co-Authored-By:` line **your
  own harness specifies for the model you are** — the attribution names who did
  the work, so a task implemented by Haiku signs as Haiku. The example commit
  messages below all show `Claude Opus 5` because that is the model that wrote
  this plan; substitute your own rather than copying that line verbatim.

## The layering rule

This is the invariant the whole plan serves. Task 3 makes it executable.

| Layer | May import |
|---|---|
| `tcm/settings.py` | nothing from `tcm` |
| `tcm/domain/` | `tcm.domain`, `tcm.settings` |
| `tcm/infrastructure/` | `tcm.domain`, `tcm.settings` |
| `tcm/services/` | `tcm.domain`, `tcm.services`, `tcm.infrastructure`, `tcm.settings` |
| `tcm/web/` | anything |

`services → infrastructure` is allowed on purpose: only six boundaries get a port, and where one exists the service takes it as a constructor argument instead of importing the implementation. Everything else (the Excel prepare helpers, the report row builder) is reached concretely.

**`tcm/settings.py` sits outside the four layers deliberately.** The five config-reading modules each do a lazy `from config import X` inside `_load_default()` today; that becomes `from tcm.settings import X` and stays lazy.

## File structure

Phase 1 moves these. Every path on the left exists today; every path on the right is new.

| From | To |
|---|---|
| `config.py` | `tcm/settings.py` |
| `parser/models.py` | `tcm/domain/case.py` |
| `parser/status.py` | `tcm/domain/status.py` |
| `parser/scope.py` | `tcm/domain/scope.py` |
| `parser/device.py` | `tcm/domain/device.py` |
| `parser/sheet_labels.py` | `tcm/domain/sheet_labels.py` |
| `report/layout.py` | `tcm/domain/report_layout.py` |
| `parser/excel_reader.py` | `tcm/infrastructure/excel/reader.py` |
| `parser/tool_data_builder.py` | `tcm/infrastructure/excel/detection.py` |
| `prepare/workbook.py` | `tcm/infrastructure/excel/workbook.py` |
| `prepare/tool_data.py` | `tcm/infrastructure/excel/tool_data.py` |
| `prepare/clear.py` | `tcm/infrastructure/excel/clearing.py` |
| `sharepoint/auth.py` | `tcm/infrastructure/graph/auth.py` |
| `sharepoint/client.py` | `tcm/infrastructure/graph/client.py` |
| `sharepoint/links.py` | `tcm/infrastructure/graph/links.py` |
| `sharepoint/workbook.py` | `tcm/infrastructure/graph/workbook.py` |
| `api/filedialog.py` | `tcm/infrastructure/dialog.py` |
| `aggregate.py` | `tcm/services/aggregation.py` |
| `report/builder.py` | `tcm/services/report_rows.py` |
| `report/publisher.py` | `tcm/services/publishing.py` |
| `prepare/runner.py` | `tcm/services/preparation.py` |
| `config_store.py` | `tcm/services/settings_store.py` |
| `api/routes.py` | `tcm/web/routes.py` (split in phase 2) |
| `app.py` | `tcm/web/app.py` (+ a thin root `app.py` runner) |
| `parser/result_status.json` | `config/result_status.json` |
| `parser/scope_groups.json` | `config/scope_groups.json` |
| `parser/device_groups.json` | `config/device_groups.json` |
| `parser/sheet_labels.json` | `config/sheet_labels.json` |
| `report/report_layout.json` | `config/report_layout.json` |

**Refinement to the spec, applied here:** the spec put `report/layout.py` and `report/builder.py` under `infrastructure/report/`. Neither touches the outside world — `ReportLayout` is a validated-at-import schema exactly like `StatusSet`, and `build_rows` is a pure transform. Leaving them in infrastructure would make `services/publishing.py` depend outward for pure code. They go to `domain/report_layout.py` and `services/report_rows.py`. Task 9 updates the spec to match.

Phase 2 adds:

| New file | Responsibility |
|---|---|
| `tcm/domain/ports.py` | the six `Protocol`s |
| `tcm/infrastructure/store/memory.py` | `InMemoryCaseStore` |
| `tcm/infrastructure/config_repo.py` | `JsonFileConfigRepository` — the atomic JSON write |
| `tcm/services/workspace.py` | `Workspace` — the loaded source and its cases |
| `tcm/services/identity.py` | `IdentityService` — sign-in and the device-code flow |
| `tcm/web/blueprints/{source,analytics,prepare,settings,sharepoint,pages}.py` | five resource blueprints plus `/` |

---

## Task 1: Package metadata and pytest configuration

There is no `pyproject.toml`: no package metadata, no pytest configuration, no declared rootdir. Adding it first means every later task's test run is reproducible.

**Files:**
- Create: `pyproject.toml`
- Modify: `requirements.txt` (unchanged content; referenced from the new file)

**Interfaces:**
- Consumes: nothing.
- Produces: `[tool.pytest.ini_options]` with `pythonpath = ["."]`, so `tests/` can import `tcm.*` once it exists.

- [ ] **Step 1: Confirm the suite is green before touching anything**

Run: `.venv/bin/python -m pytest -q`
Expected: `450 passed`

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "test-management"
version = "0.1.0"
description = "Reads test cases out of Excel workbooks and aggregates progress into Summary, Daily and Detail views."
requires-python = ">=3.12"
dependencies = [
    "Flask>=3.0",
    "pandas>=2.0",
    "openpyxl>=3.1",
    "requests>=2.31",
    "msal>=1.28",
]

[tool.setuptools]
# The app is run from a checkout, not installed. Declaring the package keeps
# `pip install -e .` working for anyone who wants it without turning the
# repository into a src-layout.
packages = ["tcm"]

[tool.pytest.ini_options]
# Pins the rootdir so `tests/` resolves `tcm.*` the same way whether pytest is
# invoked from the repository root or from an editor.
pythonpath = ["."]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 3: Verify pytest still collects the same suite**

Run: `.venv/bin/python -m pytest 2>&1 | tail -3`
Expected: `450 passed`. If pytest reports a different rootdir or a collection error, `pythonpath` is wrong — fix it before continuing.

- [ ] **Step 4: Verify the app still boots**

Run: `.venv/bin/python -c "import app; app.create_app()" && echo OK`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "$(cat <<'MSG'
Declare the project and pin pytest's rootdir

The repository had no package metadata and no pytest configuration, so
where tests resolved imports from depended on where pytest was invoked.
The restructure is about to move every module, which is the wrong time
for that to be ambiguous.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Task 2: The domain layer

Five vocabulary modules plus the two dataclasses, none of which imports anything else in the project except lazily from `config`. They move first because every other layer imports them and nothing imports back.

`report/layout.py` moves with them — see the refinement note above — even though it lives under `report/` today.

**Files:**
- Create: `tcm/__init__.py`, `tcm/domain/__init__.py`
- Move: `config.py` → `tcm/settings.py`
- Move: `parser/models.py` → `tcm/domain/case.py`
- Move: `parser/status.py` → `tcm/domain/status.py`
- Move: `parser/scope.py` → `tcm/domain/scope.py`
- Move: `parser/device.py` → `tcm/domain/device.py`
- Move: `parser/sheet_labels.py` → `tcm/domain/sheet_labels.py`
- Move: `report/layout.py` → `tcm/domain/report_layout.py`
- Move: the five JSON files → `config/`
- Modify: every file importing them (see the rewrite map below)

**Interfaces:**
- Consumes: nothing.
- Produces: `tcm.domain.case` (`TestCase`, `SheetConfig`, `CASE_COLUMNS`), `tcm.domain.status` (`STATUS`, `StatusSet`, `TONES`, `DERIVE_CONDITIONS`), `tcm.domain.scope` (`SCOPES`, `ScopeSet`), `tcm.domain.device` (`DEVICES`, `DeviceSet`), `tcm.domain.sheet_labels` (`LABELS`, `SheetLabels`, `HEADER_FIELDS`, `RESULT_FIELDS`), `tcm.domain.report_layout` (`LAYOUT`, `ReportLayout`, `SheetLayout`, `RUN_DATE`), `tcm.settings` (every constant `config.py` exported).

- [ ] **Step 1: Create the package skeleton**

```bash
mkdir -p tcm/domain config
printf '"""The test-management application package."""\n' > tcm/__init__.py
printf '"""Domain models and the vocabularies that classify them.\n\nNothing here touches Flask, pandas, requests or msal. The four vocabulary\nsingletons read their JSON at import through `tcm.settings`, which is the one\nplace outside the layers.\n"""\n' > tcm/domain/__init__.py
```

- [ ] **Step 2: Move the modules and the JSON**

```bash
git mv config.py tcm/settings.py
git mv parser/models.py tcm/domain/case.py
git mv parser/status.py tcm/domain/status.py
git mv parser/scope.py tcm/domain/scope.py
git mv parser/device.py tcm/domain/device.py
git mv parser/sheet_labels.py tcm/domain/sheet_labels.py
git mv report/layout.py tcm/domain/report_layout.py
git mv parser/result_status.json config/result_status.json
git mv parser/scope_groups.json config/scope_groups.json
git mv parser/device_groups.json config/device_groups.json
git mv parser/sheet_labels.json config/sheet_labels.json
git mv report/report_layout.json config/report_layout.json
```

- [ ] **Step 3: Point `tcm/settings.py` at `config/`**

`config.py` computed its JSON paths from its own directory with `_HERE`. It now sits one level deeper *and* the JSONs moved, so every default path is wrong in two ways. Replace the `_HERE` definition and the five defaults:

```python
# The repository root: this file lives at <root>/tcm/settings.py.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_DIR = os.path.join(_ROOT, "config")
```

Then every default becomes `os.path.join(_CONFIG_DIR, "<name>.json")`. There are five: `RESULT_STATUS_CONFIG`, `SCOPE_GROUPS_CONFIG`, `DEVICE_GROUPS_CONFIG`, `REPORT_LAYOUT_CONFIG`, `SHEET_LABELS_CONFIG`. Delete the now-unused `_HERE`. Note `RESULT_STATUS_CONFIG` used `os.path.dirname(os.path.abspath(__file__))` inline rather than `_HERE` — it changes too.

- [ ] **Step 4: Rewrite every import in one pass**

```bash
.venv/bin/python - <<'PY'
import pathlib, re

MAP = [
    (r"\bfrom parser\.models import\b",        "from tcm.domain.case import"),
    (r"\bfrom parser\.status import\b",        "from tcm.domain.status import"),
    (r"\bfrom parser\.scope import\b",         "from tcm.domain.scope import"),
    (r"\bfrom parser\.device import\b",        "from tcm.domain.device import"),
    (r"\bfrom parser\.sheet_labels import\b",  "from tcm.domain.sheet_labels import"),
    (r"\bfrom report\.layout import\b",        "from tcm.domain.report_layout import"),
    (r"\bfrom parser import models\b",         "from tcm.domain import case as models"),
    (r"\bfrom config import\b",                "from tcm.settings import"),
    (r"^import config$",                       "import tcm.settings as config"),
    (r"\bimport config as app_config\b",       "import tcm.settings as app_config"),
]

for path in pathlib.Path(".").rglob("*.py"):
    if ".venv" in path.parts or path.parts[0] in {"build", "dist"}:
        continue
    text = original = path.read_text()
    for pattern, replacement in MAP:
        text = re.sub(pattern, replacement, text, flags=re.M)
    if text != original:
        path.write_text(text)
        print("rewrote", path)
PY
```

- [ ] **Step 5: Fix the two callers the regex cannot reach**

`api/routes.py` has `import config` on its own line *and* uses `config.GRAPH_CLIENT_ID`; the map above turns it into `import tcm.settings as config`, which keeps every `config.X` usage working. Confirm that is what happened:

Run: `grep -n "^import tcm.settings as config" api/routes.py`
Expected: one hit.

`tests/test_status.py:221` used `from parser import models` and then `models.CASE_COLUMNS`; the map aliases it so the body still reads `models.`. Confirm:

Run: `grep -n "from tcm.domain import case as models" tests/test_status.py`
Expected: one hit.

- [ ] **Step 6: Delete the emptied packages**

`parser/` now holds only `__init__.py`, `excel_reader.py` and `tool_data_builder.py` — those move in Task 4, so `parser/` stays for now. `report/` still holds `__init__.py`, `builder.py` and `publisher.py` — it stays too. Nothing to delete yet; this step is a check that you have not deleted anything prematurely.

Run: `ls parser report`
Expected: `parser` has `__init__.py excel_reader.py tool_data_builder.py`; `report` has `__init__.py builder.py publisher.py`.

- [ ] **Step 7: Run the suite**

Run: `.venv/bin/python -m pytest 2>&1 | tail -5`
Expected: `450 passed`

If a test fails with `ModuleNotFoundError: No module named 'parser.status'`, the rewrite missed a lazy import inside a function body — the regex is multiline and handles indentation, but check with:
`grep -rn "parser\.\(status\|scope\|device\|sheet_labels\|models\)\|report\.layout\|from config import" --include='*.py' . | grep -v '/.venv/'`
Expected: no hits.

- [ ] **Step 8: Verify the app still boots and reads its config from the new place**

```bash
.venv/bin/python -c "
from tcm.domain.status import STATUS
from tcm.domain.scope import SCOPES
from tcm.domain.report_layout import LAYOUT
import tcm.settings as s
assert STATUS.keys, 'taxonomy did not load'
assert SCOPES.keys, 'scope groups did not load'
assert 'config/result_status.json' in s.RESULT_STATUS_CONFIG, s.RESULT_STATUS_CONFIG
print('OK', STATUS.keys)
"
```
Expected: `OK ['OK', 'NG', 'NG-OK', 'Pending', 'Cancel', 'NYS', 'OOS', 'Other']`

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "$(cat <<'MSG'
Move the domain vocabularies out of parser/

parser/ was four unrelated things: the Excel reader, four vocabularies
that parse nothing, and the JSON those vocabularies read. The
vocabularies were only there because the reader happened to be their
first caller, and the package shadowed the stdlib `parser` name.

The JSON moves to config/ at the root, because the Config view writes
those files at runtime and a package directory is the wrong place to
write user data.

report/layout.py comes too: it is a validated-at-import schema exactly
like StatusSet, so leaving it outside the domain would make the
publisher depend outward for pure code.

No logic changed. 450 passed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Task 3: Make the layering rule executable

The rule is worth nothing if only this document states it. This test is what stops layer four of the move quietly importing backwards.

**Files:**
- Create: `tests/test_layering.py`

**Interfaces:**
- Consumes: the `tcm.domain` package from Task 2.
- Produces: nothing other modules use.

- [ ] **Step 1: Write the test**

```python
"""The layering rule, made executable.

The spec's dependency table is only worth something if something checks it.
This walks the AST of every module in the package and asserts what each layer
is allowed to import — which is what stops a later move quietly importing
backwards and leaving the tree layered in name only.
"""
import ast
import pathlib

import pytest

PACKAGE = pathlib.Path(__file__).resolve().parents[1] / "tcm"

#: Nothing in the domain may reach a framework. The vocabularies still read
#: their JSON at import, so this names frameworks rather than forbidding I/O;
#: the ConfigRepository port is where that gets cut properly.
FRAMEWORKS = {"flask", "pandas", "openpyxl", "requests", "msal"}

#: Which `tcm.<layer>` each layer may import. `tcm.settings` sits outside the
#: layers on purpose and is allowed everywhere.
ALLOWED = {
    "domain": {"domain"},
    "infrastructure": {"domain", "infrastructure"},
    "services": {"domain", "infrastructure", "services"},
    "web": {"domain", "infrastructure", "services", "web"},
}


def _modules(layer):
    """Every .py file in one layer, as (layer, path) pairs for parametrising."""
    root = PACKAGE / layer
    return [p for p in sorted(root.rglob("*.py"))] if root.is_dir() else []


def _imported_names(path):
    """Every module name `path` imports, absolute names only."""
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


def _cases(layer):
    return pytest.mark.parametrize(
        "path", _modules(layer), ids=lambda p: str(p.relative_to(PACKAGE)))


@_cases("domain")
def test_the_domain_reaches_no_framework(path):
    for name in _imported_names(path):
        assert name.split(".")[0] not in FRAMEWORKS, (
            f"{path.name} imports {name}; the domain classifies cases and must "
            f"not know how they were read or where they are served")


@pytest.mark.parametrize("layer", sorted(ALLOWED))
def test_each_layer_imports_only_inward(layer):
    for path in _modules(layer):
        for name in _imported_names(path):
            parts = name.split(".")
            if parts[0] != "tcm" or len(parts) < 2 or parts[1] == "settings":
                continue
            assert parts[1] in ALLOWED[layer], (
                f"tcm/{layer}/{path.name} imports {name}, which points outward; "
                f"{layer} may only reach {sorted(ALLOWED[layer])}")


def test_only_the_web_layer_knows_about_flask():
    for layer in ("domain", "infrastructure", "services"):
        for path in _modules(layer):
            for name in _imported_names(path):
                assert name.split(".")[0] != "flask", (
                    f"tcm/{layer}/{path.name} imports flask; HTTP is the web "
                    f"layer's business and nothing below it should have one")
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python -m pytest tests/test_layering.py -v 2>&1 | tail -20`
Expected: all pass. Only `domain/` exists so far, so `_modules("services")` returns `[]` and those parametrisations are empty — that is correct, and the test starts biting as each layer arrives.

- [ ] **Step 3: Prove it can fail**

Temporarily add `import flask` to the top of `tcm/domain/status.py`, run the test, confirm `test_the_domain_reaches_no_framework` fails naming `status.py`, then remove the line.

Run: `.venv/bin/python -m pytest tests/test_layering.py -q 2>&1 | tail -5`
Expected with the line present: at least 1 failed. Expected after removing it: all pass.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest 2>&1 | tail -3`
Expected: `4xx passed` — the count grows by however many parametrised cases exist; record the new number and use it as the gate from here on.

- [ ] **Step 5: Commit**

```bash
git add tests/test_layering.py
git commit -m "$(cat <<'MSG'
Check the layering rule instead of only documenting it

A dependency rule that lives in a document is one nothing enforces. This
walks each module's AST and asserts what its layer may import, so a
later move that points outward fails here rather than being discovered
when somebody tries to reuse the domain.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Task 4: The Excel infrastructure

Five modules that read and write `.xlsx`. They import the domain and each other, and nothing above them.

**Files:**
- Create: `tcm/infrastructure/__init__.py`, `tcm/infrastructure/excel/__init__.py`
- Move: `parser/excel_reader.py` → `tcm/infrastructure/excel/reader.py`
- Move: `parser/tool_data_builder.py` → `tcm/infrastructure/excel/detection.py`
- Move: `prepare/workbook.py` → `tcm/infrastructure/excel/workbook.py`
- Move: `prepare/tool_data.py` → `tcm/infrastructure/excel/tool_data.py`
- Move: `prepare/clear.py` → `tcm/infrastructure/excel/clearing.py`
- Modify: `prepare/runner.py`, `api/routes.py`, `tools/generate_samples.py`, `tests/conftest.py` and the test modules importing them

**Interfaces:**
- Consumes: `tcm.domain.case`, `tcm.domain.status`, `tcm.domain.scope`, `tcm.domain.sheet_labels`.
- Produces: `tcm.infrastructure.excel.reader` (`load_file`, `load_files`, `load_from_folder`, `load_from_files`, `find_workbooks`, `parse_tool_data`, `read_test_cases`, `TOOL_DATA_SHEET`, `TOOL_DATA_COLUMNS`), `tcm.infrastructure.excel.clearing` (`plan_sheet`, `apply_plan`, `DEFAULT_KEEP`), `tcm.infrastructure.excel.tool_data` (`write_tool_data_sheet`, `diff_configs`), `tcm.infrastructure.excel.detection`, `tcm.infrastructure.excel.workbook`.

- [ ] **Step 1: Create the packages and move**

```bash
mkdir -p tcm/infrastructure/excel
printf '"""Everything that touches the outside world: Excel, Graph, disk, the OS.\n\nImports the domain and nothing above it.\n"""\n' > tcm/infrastructure/__init__.py
printf '"""Reading and writing the test case workbooks."""\n' > tcm/infrastructure/excel/__init__.py
git mv parser/excel_reader.py tcm/infrastructure/excel/reader.py
git mv parser/tool_data_builder.py tcm/infrastructure/excel/detection.py
git mv prepare/workbook.py tcm/infrastructure/excel/workbook.py
git mv prepare/tool_data.py tcm/infrastructure/excel/tool_data.py
git mv prepare/clear.py tcm/infrastructure/excel/clearing.py
git rm -q parser/__init__.py
rmdir parser 2>/dev/null || true
```

- [ ] **Step 2: Rewrite the imports**

```bash
.venv/bin/python - <<'PY'
import pathlib, re

MAP = [
    (r"\bfrom parser\.excel_reader import\b",       "from tcm.infrastructure.excel.reader import"),
    (r"\bimport parser\.excel_reader\b",            "import tcm.infrastructure.excel.reader"),
    (r"\bfrom parser\.tool_data_builder import\b",  "from tcm.infrastructure.excel.detection import"),
    (r"\bfrom prepare\.workbook import\b",          "from tcm.infrastructure.excel.workbook import"),
    (r"\bfrom prepare\.tool_data import\b",         "from tcm.infrastructure.excel.tool_data import"),
    (r"\bfrom prepare\.clear import\b",             "from tcm.infrastructure.excel.clearing import"),
    (r"\bfrom prepare import clear\b",              "from tcm.infrastructure.excel import clearing as clear"),
    (r"\bfrom prepare import tool_data\b",          "from tcm.infrastructure.excel import tool_data"),
    (r"\bfrom prepare import workbook\b",           "from tcm.infrastructure.excel import workbook"),
]

for path in pathlib.Path(".").rglob("*.py"):
    if ".venv" in path.parts:
        continue
    text = original = path.read_text()
    for pattern, replacement in MAP:
        text = re.sub(pattern, replacement, text, flags=re.M)
    if text != original:
        path.write_text(text)
        print("rewrote", path)
PY
```

- [ ] **Step 3: Check nothing still names the old modules**

Run:
```bash
grep -rn "parser\.excel_reader\|parser\.tool_data_builder\|prepare\.workbook\|prepare\.tool_data\|prepare\.clear" --include='*.py' . | grep -v '/.venv/'
```
Expected: no hits.

- [ ] **Step 4: Run the suite**

Run: `.venv/bin/python -m pytest 2>&1 | tail -5`
Expected: the Task 3 gate count, all passing.

Note the log prefix in captured warnings changes from `parser.excel_reader` to `tcm.infrastructure.excel.reader`, because loggers are named `__name__`. If a test asserts on a logger name, that is a real assertion to update — grep for it:
`grep -rn "parser.excel_reader" tests/`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "$(cat <<'MSG'
Gather the Excel code into one infrastructure package

Reading a workbook and writing one back were split across parser/ and
prepare/ for no reason other than when each was written. They are one
concern -- the only code that knows what an .xlsx looks like -- and they
now sit together under infrastructure, which is the layer allowed to
know that.

No logic changed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Task 5: The Graph and OS infrastructure

**Files:**
- Create: `tcm/infrastructure/graph/__init__.py`
- Move: `sharepoint/{auth,client,links,workbook}.py` → `tcm/infrastructure/graph/`
- Move: `api/filedialog.py` → `tcm/infrastructure/dialog.py`
- Modify: `report/publisher.py`, `api/routes.py`, the SharePoint and filedialog tests

**Interfaces:**
- Consumes: nothing from `tcm`.
- Produces: `tcm.infrastructure.graph.auth` (`GraphAuth`, `NotConfigured`, `NotSignedIn`), `tcm.infrastructure.graph.client` (`GraphClient`, `GraphError`), `tcm.infrastructure.graph.links` (`DriveItemRef` and the URL parser), `tcm.infrastructure.graph.workbook` (`Workbook`, `UsedRange`), `tcm.infrastructure.dialog` (`pick_files`, `pick_folder`, `DialogError`).

- [ ] **Step 1: Move**

```bash
mkdir -p tcm/infrastructure/graph
printf '"""Microsoft Graph: auth, the HTTP client, link parsing, the workbook API.\n\nReading stays local; Graph is only ever used to write the report.\n"""\n' > tcm/infrastructure/graph/__init__.py
git mv sharepoint/auth.py tcm/infrastructure/graph/auth.py
git mv sharepoint/client.py tcm/infrastructure/graph/client.py
git mv sharepoint/links.py tcm/infrastructure/graph/links.py
git mv sharepoint/workbook.py tcm/infrastructure/graph/workbook.py
git mv api/filedialog.py tcm/infrastructure/dialog.py
git rm -q sharepoint/__init__.py
rmdir sharepoint 2>/dev/null || true
```

- [ ] **Step 2: Rewrite the imports**

```bash
.venv/bin/python - <<'PY'
import pathlib, re

MAP = [
    (r"\bfrom sharepoint\.auth import\b",     "from tcm.infrastructure.graph.auth import"),
    (r"\bfrom sharepoint\.client import\b",   "from tcm.infrastructure.graph.client import"),
    (r"\bfrom sharepoint\.links import\b",    "from tcm.infrastructure.graph.links import"),
    (r"\bfrom sharepoint\.workbook import\b", "from tcm.infrastructure.graph.workbook import"),
    (r"\bfrom sharepoint import\b",           "from tcm.infrastructure.graph import"),
    (r"\bimport sharepoint\.(\w+)\b",         r"import tcm.infrastructure.graph.\1"),
    (r"\bfrom api\.filedialog import\b",      "from tcm.infrastructure.dialog import"),
    (r"\bimport api\.filedialog\b",           "import tcm.infrastructure.dialog"),
    (r"\bfrom api import filedialog\b",       "from tcm.infrastructure import dialog as filedialog"),
]

for path in pathlib.Path(".").rglob("*.py"):
    if ".venv" in path.parts:
        continue
    text = original = path.read_text()
    for pattern, replacement in MAP:
        text = re.sub(pattern, replacement, text, flags=re.M)
    if text != original:
        path.write_text(text)
        print("rewrote", path)
PY
```

- [ ] **Step 3: Check for stragglers, including monkeypatch targets**

Tests patch by string path. Those are *not* import lines and the rewrite above misses them.

Run:
```bash
grep -rn "sharepoint\|api\.filedialog\|api\.routes\._auth" --include='*.py' . | grep -v '/.venv/'
```
Expected: only hits inside string literals used by `monkeypatch.setattr(...)`. Update each to the new dotted path by hand. `tests/test_filedialog.py` and `tests/test_api_sharepoint.py` are the likely ones.

- [ ] **Step 4: Run the suite**

Run: `.venv/bin/python -m pytest 2>&1 | tail -5`
Expected: the gate count, all passing.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "$(cat <<'MSG'
Move Graph and the native file dialog into infrastructure

Both are the outside world: one is somebody else's HTTP API, the other
is the OS. The file dialog in particular had no business living under
api/ -- it answers to a route, but so does everything.

No logic changed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Task 6: The service layer

The five modules that orchestrate. `aggregate.py` is the one the routes and the publisher share, which is what keeps the screen and the published report from drifting; moving it into a named layer is most of this task's point.

**Files:**
- Create: `tcm/services/__init__.py`
- Move: `aggregate.py` → `tcm/services/aggregation.py`
- Move: `report/builder.py` → `tcm/services/report_rows.py`
- Move: `report/publisher.py` → `tcm/services/publishing.py`
- Move: `prepare/runner.py` → `tcm/services/preparation.py`
- Move: `config_store.py` → `tcm/services/settings_store.py`
- Modify: `api/routes.py`, `tests/conftest.py`, the aggregate/publisher/prepare/config tests

**Interfaces:**
- Consumes: the domain from Task 2, the Excel and Graph infrastructure from Tasks 4–5.
- Produces: `tcm.services.aggregation` (`summary_rows`, `file_rows`, `status_cases`, `daily_rows`, `productivity_rows`, `issue_rows`, `in_plan`), `tcm.services.report_rows` (`build_rows`), `tcm.services.publishing` (`publish_to_url`, `SheetMissing`), `tcm.services.preparation` (`describe`, `detect`, `clear`, `source_workbooks`), `tcm.services.settings_store` (`read_all`, `save`, `path_of`, `CONFIGS`).

- [ ] **Step 1: Move**

```bash
mkdir -p tcm/services
printf '"""Orchestration over domain objects.\n\nPlain functions and small objects: no Flask, no HTTP, no request context. The\nroutes are jsonify wrappers around what lives here, and the report publisher\ncalls the same functions the screen does -- which is what stops the numbers on\nscreen and the numbers in the report drifting apart.\n"""\n' > tcm/services/__init__.py
git mv aggregate.py tcm/services/aggregation.py
git mv report/builder.py tcm/services/report_rows.py
git mv report/publisher.py tcm/services/publishing.py
git mv prepare/runner.py tcm/services/preparation.py
git mv config_store.py tcm/services/settings_store.py
git rm -q report/__init__.py prepare/__init__.py
rmdir report prepare 2>/dev/null || true
```

- [ ] **Step 2: Rewrite the imports**

```bash
.venv/bin/python - <<'PY'
import pathlib, re

MAP = [
    (r"^import aggregate$",                   "from tcm.services import aggregation as aggregate"),
    (r"\bfrom aggregate import\b",            "from tcm.services.aggregation import"),
    (r"\bimport aggregate\b",                 "from tcm.services import aggregation as aggregate"),
    (r"\bfrom report\.builder import\b",      "from tcm.services.report_rows import"),
    (r"\bfrom report\.publisher import\b",    "from tcm.services.publishing import"),
    (r"\bfrom report import publisher\b",     "from tcm.services import publishing as publisher"),
    (r"\bfrom prepare\.runner import\b",      "from tcm.services.preparation import"),
    (r"\bfrom prepare import runner\b",       "from tcm.services import preparation as runner"),
    (r"^import config_store$",                "from tcm.services import settings_store as config_store"),
    (r"\bimport config_store\b",              "from tcm.services import settings_store as config_store"),
    (r"\bfrom config_store import\b",         "from tcm.services.settings_store import"),
]

for path in pathlib.Path(".").rglob("*.py"):
    if ".venv" in path.parts:
        continue
    text = original = path.read_text()
    for pattern, replacement in MAP:
        text = re.sub(pattern, replacement, text, flags=re.M)
    if text != original:
        path.write_text(text)
        print("rewrote", path)
PY
```

The aliases matter: `api/routes.py` calls `aggregate.summary_rows(...)` and `runner.detect(...)` throughout, and `tests/test_publisher.py:344` does `from report import publisher` then `publisher.X`. Aliasing keeps the bodies untouched, which is the no-logic-edits rule.

- [ ] **Step 3: Check for stragglers and duplicate import lines**

The `^import aggregate$` and `\bimport aggregate\b` rules can both fire on the same line. Check:

Run: `grep -rn "aggregation as aggregate as aggregate\|settings_store as config_store as config_store" --include='*.py' . | grep -v '/.venv/'`
Expected: no hits. If any appear, fix by hand.

Run: `grep -rn "^import aggregate\|^import config_store\|from report import\|from prepare import\|from config_store import" --include='*.py' . | grep -v '/.venv/'`
Expected: no hits.

- [ ] **Step 4: Run the suite and the layering test**

Run: `.venv/bin/python -m pytest 2>&1 | tail -5`
Expected: the gate count, all passing. `test_each_layer_imports_only_inward` now has real `services/` modules to check.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "$(cat <<'MSG'
Give the service layer a name and a home

aggregate.py, config_store.py, prepare/runner.py and report/publisher.py
were already the services: plain functions over domain objects that the
routes and the publisher both call. They were spread across three levels
of the tree, so nothing in the file listing said they were a layer.

No logic changed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Task 7: The web layer

Phase 1 moves the blueprint as one file. Splitting it is Task 11, after the state it holds has somewhere to go.

The root `app.py` stays, reduced to a runner, so `.venv/bin/python app.py` keeps working — it is the documented command in CLAUDE.md and README.

**Files:**
- Create: `tcm/web/__init__.py`, `tcm/web/app.py`
- Move: `api/routes.py` → `tcm/web/routes.py`
- Modify: `app.py` (becomes a runner), `templates/` reference in the factory
- Delete: `api/__init__.py`

**Interfaces:**
- Consumes: every layer below.
- Produces: `tcm.web.app.create_app()`, `tcm.web.routes.api` (the blueprint).

- [ ] **Step 1: Move the blueprint**

```bash
mkdir -p tcm/web
printf '"""HTTP: the Flask app, its blueprints, and nothing else.\n\nThe only layer that imports Flask.\n"""\n' > tcm/web/__init__.py
git mv api/routes.py tcm/web/routes.py
git rm -q api/__init__.py
rmdir api 2>/dev/null || true
```

- [ ] **Step 2: Write `tcm/web/app.py`**

Flask must be told where the templates and static files are, because the package is no longer beside them.

```python
"""The Flask application factory."""
import logging
import os

from flask import Flask, render_template

from tcm.settings import DEBUG, PORT
from tcm.web.routes import api

#: templates/ and static/ stayed at the repository root: they are the app's
#: front end, not the package's data, and the run command documented in
#: README.md is still `.venv/bin/python app.py` from there.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(_ROOT, "templates"),
        static_folder=os.path.join(_ROOT, "static"),
    )
    app.register_blueprint(api)

    @app.route("/")
    def index():
        return render_template("index.html")

    return app


def configure_logging():
    logging.basicConfig(
        level=logging.DEBUG if DEBUG else logging.INFO,
        format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
```

- [ ] **Step 3: Reduce the root `app.py` to a runner**

```python
"""Run the app: `.venv/bin/python app.py`.

The factory lives in `tcm.web.app`; this is the entry point that keeps the
documented command working from the repository root.
"""
from tcm.settings import DEBUG, PORT
from tcm.web.app import configure_logging, create_app

configure_logging()
app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=DEBUG)
```

- [ ] **Step 4: Rewrite the imports**

```bash
.venv/bin/python - <<'PY'
import pathlib, re

MAP = [
    (r"\bfrom api\.routes import\b",  "from tcm.web.routes import"),
    (r"\bimport api\.routes\b",       "import tcm.web.routes"),
    (r"\bfrom api import routes\b",   "from tcm.web import routes"),
    (r'"api\.routes\.',               '"tcm.web.routes.'),
    (r"'api\.routes\.",               "'tcm.web.routes.",),
]

for path in pathlib.Path(".").rglob("*.py"):
    if ".venv" in path.parts:
        continue
    text = original = path.read_text()
    for pattern, replacement in MAP:
        text = re.sub(pattern, replacement, text, flags=re.M)
    if text != original:
        path.write_text(text)
        print("rewrote", path)
PY
```

`tests/test_api.py` imports `routes` to reset `routes._data` between tests and to replace `_spawn`; those become `from tcm.web import routes`.

- [ ] **Step 5: Run the suite**

Run: `.venv/bin/python -m pytest 2>&1 | tail -5`
Expected: the gate count, all passing.

- [ ] **Step 6: Verify the app boots and serves the page**

```bash
.venv/bin/python -c "
from tcm.web.app import create_app
c = create_app().test_client()
r = c.get('/')
assert r.status_code == 200, r.status_code
assert b'summaryView' in r.data, 'index.html did not render'
s = c.get('/static/js/main.js')
assert s.status_code == 200, f'static not served: {s.status_code}'
print('OK')
"
```
Expected: `OK`. This is the step that catches a wrong `template_folder` or `static_folder`, which no unit test covers.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "$(cat <<'MSG'
Move the blueprint into a web layer behind an app factory

The factory now names where templates/ and static/ are, because the
package no longer sits beside them; the root app.py stays as the runner
so the documented command still works.

Splitting the blueprint comes next -- it holds application state, and
that needs somewhere to go first.

No logic changed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Task 8: Mirror the tests onto the layout

23 flat test modules that no longer say which layer they cover.

**Files:**
- Create: `tests/{domain,services,infrastructure,web}/__init__.py`
- Move: each test module into the layer it tests
- Modify: `tests/conftest.py` stays at `tests/` — it is shared

**Interfaces:**
- Consumes: everything.
- Produces: nothing.

- [ ] **Step 1: Create the directories and move**

```bash
mkdir -p tests/domain tests/services tests/infrastructure tests/web
for d in domain services infrastructure web; do : > tests/$d/__init__.py; done

git mv tests/test_status.py tests/domain/test_status.py
git mv tests/test_scope.py tests/domain/test_scope.py
git mv tests/test_device_groups.py tests/domain/test_device_groups.py
git mv tests/test_report_layout.py tests/domain/test_report_layout.py

git mv tests/test_excel_reader.py tests/infrastructure/test_excel_reader.py
git mv tests/test_prepare_clear.py tests/infrastructure/test_prepare_clear.py
git mv tests/test_prepare_tool_data.py tests/infrastructure/test_prepare_tool_data.py
git mv tests/test_sharepoint_auth.py tests/infrastructure/test_sharepoint_auth.py
git mv tests/test_sharepoint_client.py tests/infrastructure/test_sharepoint_client.py
git mv tests/test_sharepoint_workbook.py tests/infrastructure/test_sharepoint_workbook.py
git mv tests/test_filedialog.py tests/infrastructure/test_filedialog.py

git mv tests/test_aggregate.py tests/services/test_aggregate.py
git mv tests/test_publisher.py tests/services/test_publisher.py
git mv tests/test_publish_integration.py tests/services/test_publish_integration.py
git mv tests/test_report_builder.py tests/services/test_report_builder.py
git mv tests/test_config_store.py tests/services/test_config_store.py

git mv tests/test_api.py tests/web/test_api.py
git mv tests/test_api_config.py tests/web/test_api_config.py
git mv tests/test_api_prepare.py tests/web/test_api_prepare.py
git mv tests/test_api_sharepoint.py tests/web/test_api_sharepoint.py
```

`tests/test_generate_samples.py` and `tests/test_layering.py` stay at `tests/` — the first covers `tools/`, which is not a layer, and the second covers the package as a whole.

- [ ] **Step 2: Run the suite**

Run: `.venv/bin/python -m pytest 2>&1 | tail -5`
Expected: the gate count, all passing. `conftest.py` at `tests/` still applies to every subdirectory, so the fixtures resolve unchanged.

If collection errors appear about duplicate module names, it is the missing `__init__.py` in one of the four directories — check all four exist.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "$(cat <<'MSG'
Mirror the tests onto the layers they cover

23 flat modules gave no clue which layer a failure was in. conftest.py
stays at tests/ because its workbook fixtures are shared by three of the
four layers.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Task 9: Rewrite the architecture documents

`CLAUDE.md` names roughly 60 file paths and is the architecture document for this repository. Every one of them is now wrong. This is a deliverable, not bookkeeping.

**Files:**
- Modify: `CLAUDE.md`, `README.md`, `docs/superpowers/specs/2026-09-20-project-restructure-design.md`

**Interfaces:**
- Consumes: the finished phase 1 tree.
- Produces: nothing code depends on.

- [ ] **Step 1: List every stale path**

```bash
grep -oE '\[[^]]+\]\(([a-z_]+/)*[a-z_]+\.(py|json)\)|`[a-z_/]+\.(py|json)`' CLAUDE.md | sort -u
```
Work through the list; each maps through the table at the top of this plan.

- [ ] **Step 2: Rewrite `CLAUDE.md`'s paths and the Commands section**

Update every path. The Commands block gains nothing new — `.venv/bin/python app.py` and `.venv/bin/python -m pytest -q` both still work — but `RESULT_STATUS_CONFIG=/path/my_status.json` now points at `config/`, and the sample generator's module path is unchanged (`tools.generate_samples`).

Add a short section stating the layering rule and pointing at `tests/test_layering.py`, since that is now the thing enforcing it.

- [ ] **Step 3: Rewrite `README.md`'s structure tree**

The "Cấu trúc" block at the top lists the old tree. Replace it with the new one. Keep it in Vietnamese, matching the surrounding prose.

- [ ] **Step 4: Correct the spec's `report/layout.py` placement**

The spec puts `report/layout.py` and `report/builder.py` under `infrastructure/report/`. Change those two lines to `domain/report_layout.py` and `services/report_rows.py`, and add one sentence giving the reason: neither touches the outside world, so leaving them in infrastructure would make `services/publishing.py` depend outward for pure code.

- [ ] **Step 5: Verify no stale path survives**

```bash
grep -nE '\b(parser|sharepoint|api)/[a-z_]+\.py|\baggregate\.py|\bconfig_store\.py|\bprepare/(runner|clear|tool_data|workbook)\.py|\breport/(layout|builder|publisher)\.py' CLAUDE.md README.md
```
Expected: no hits.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md README.md docs/superpowers/specs/2026-09-20-project-restructure-design.md
git commit -m "$(cat <<'MSG'
Describe the tree that now exists

CLAUDE.md names around sixty file paths and is the architecture document
for this repository; every one of them moved. Records the layering rule
and points at the test that enforces it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

**Phase 1 ends here.** The tree is layered, the suite is green, and no behaviour has changed.

---

## Task 10: The ports

Six `Protocol`s. Each has exactly one implementation today; the rule bounding the set is in the spec — a port exists where a test already needs a stand-in, or where a swap is genuinely planned.

**Files:**
- Create: `tcm/domain/ports.py`
- Create: `tests/domain/test_ports.py`

**Interfaces:**
- Consumes: `tcm.domain.case.TestCase`.
- Produces: `CaseLoader`, `CaseStore`, `ReportWorkbook`, `ConfigRepository`, `TokenProvider`, `FilePicker`, and `Snapshot`.

- [ ] **Step 1: Write the ports**

```python
"""The interfaces this application talks to the outside world through.

Each has one implementation today. The rule is that a port exists where a test
already needs a stand-in, or where a swap is genuinely planned -- not wherever
a boundary could be drawn. `ReportWorkbook` is the clearest case: the publisher
has been driven through a hand-written fake since it was first tested, so the
interface already existed and simply was not written down.
"""
from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

from tcm.domain.case import TestCase


@dataclass
class Snapshot:
    """One load: the cases read, and what each workbook contributed.

    Attributes:
        cases: Every case read, across every workbook.
        file_results: One `{"file", "path", "status", ...}` dict per workbook,
            including the ones that failed -- a malformed TOOL_DATA row must
            not sink the batch.
        source: What was loaded, as `{"type": "folder"|"files", "value": ...}`.
    """

    cases: list[TestCase] = field(default_factory=list)
    file_results: list[dict] = field(default_factory=list)
    source: Optional[dict] = None


@runtime_checkable
class CaseLoader(Protocol):
    """Reads test cases from somewhere. Excel today."""

    def load_from_folder(self, folder_path: str) -> tuple[list[TestCase], list[dict]]:
        ...

    def load_from_files(self, file_paths: list[str]) -> tuple[list[TestCase], list[dict]]:
        ...

    def find_workbooks(self, folder_path: str) -> list[str]:
        ...


@runtime_checkable
class CaseStore(Protocol):
    """Holds the current load. In memory today; the database seam."""

    def put(self, snapshot: Snapshot) -> None:
        ...

    def get(self) -> Snapshot:
        ...


@runtime_checkable
class ReportWorkbook(Protocol):
    """The report workbook, edited in place.

    Exactly the eight methods `tests/services/test_publisher.py`'s FakeWorkbook
    implements. (CLAUDE.md has long said "seven methods wide" -- it is wrong,
    and Task 15 corrects it.) Widening this means widening the fake, which is the point:
    downloading the file, rewriting it and putting it back would destroy the
    charts and pivots in a hand-built report.
    """

    def worksheet_names(self) -> list[str]:
        ...

    def used_range(self, sheet: str):
        ...

    def write_values(self, sheet: str, first_row: int, first_column: int,
                     rows: list[list]) -> None:
        ...

    def delete_rows(self, sheet: str, first_row: int, count: int,
                    first_column: int, width: int) -> None:
        ...

    def table_at(self, sheet: str, header_row: int):
        ...

    def table_rows(self, table: str) -> list[tuple[int, list]]:
        ...

    def table_add_rows(self, table: str, rows: list[list]) -> None:
        ...

    def table_delete_row(self, table: str, index: int) -> None:
        ...


@runtime_checkable
class ConfigRepository(Protocol):
    """Reads and writes the editable config files.

    A write must be atomic: a half-written result_status.json does not make the
    taxonomy wrong, it stops the app booting.
    """

    def read_text(self, path: str) -> str:
        ...

    def write_text(self, path: str, text: str) -> None:
        ...


@runtime_checkable
class TokenProvider(Protocol):
    """A Microsoft Graph identity. One per process today; per user later."""

    def status(self) -> dict:
        ...

    def token(self) -> str:
        ...

    def begin_device_login(self) -> dict:
        ...

    def complete_device_login(self, flow: dict) -> dict:
        ...

    def sign_out(self) -> None:
        ...


@runtime_checkable
class FilePicker(Protocol):
    """A native folder / file dialog on the machine running the server."""

    def pick_folder(self, initial: Optional[str] = None) -> list[str]:
        ...

    def pick_files(self, initial: Optional[str] = None) -> list[str]:
        ...
```

- [ ] **Step 2: Write the test that the shipped implementations satisfy them**

```python
"""Each port's one implementation actually implements it.

A Protocol nothing is checked against is a comment. These are the checks that
make the six interfaces load-bearing rather than decorative.
"""
from tcm.domain import ports
from tcm.infrastructure.graph.auth import GraphAuth
from tcm.infrastructure.graph.workbook import Workbook


def test_the_graph_workbook_is_a_report_workbook():
    assert issubclass(Workbook, ports.ReportWorkbook)


def test_graph_auth_is_a_token_provider():
    assert issubclass(GraphAuth, ports.TokenProvider)


def test_the_publisher_fake_is_a_report_workbook():
    """The fake and the real client answer to one interface, or they drift."""
    from tests.services.test_publisher import FakeWorkbook
    assert issubclass(FakeWorkbook, ports.ReportWorkbook)
```

- [ ] **Step 3: Run it**

Run: `.venv/bin/python -m pytest tests/domain/test_ports.py -v 2>&1 | tail -15`
Expected: all pass.

`runtime_checkable` Protocols support `issubclass` for method-only Protocols — all six are method-only, which is why none declares an attribute. If a check fails, the implementation is genuinely missing a method or has a differently-named one; fix the port to match reality rather than changing the implementation, since phase 2 changes no behaviour either.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest 2>&1 | tail -3`
Expected: gate count + 3.

- [ ] **Step 5: Commit**

```bash
git add tcm/domain/ports.py tests/domain/test_ports.py
git commit -m "$(cat <<'MSG'
Write down the six interfaces the outside world is reached through

ReportWorkbook is the clearest: the publisher has been driven through a
hand-written fake since it was first tested, so the interface already
existed -- it just was not written down anywhere that could be checked.
The other five are the seams a database, per-user tokens and a headless
run will be cut at.

Every port is checked against its implementation. A Protocol nothing is
checked against is a comment.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Task 11: `Workspace` — the loaded source and its cases

Lifts `_data` and `_load` out of the blueprint. This is the change `tests/web/test_api.py` currently pays for by resetting a module global between tests.

**Files:**
- Create: `tcm/services/workspace.py`, `tcm/infrastructure/store/__init__.py`, `tcm/infrastructure/store/memory.py`, `tcm/infrastructure/excel/loader.py`
- Create: `tests/services/test_workspace.py`
- Modify: `tcm/web/routes.py`

**Interfaces:**
- Consumes: `tcm.domain.ports` (`CaseLoader`, `CaseStore`, `Snapshot`), `tcm.infrastructure.excel.reader`.
- Produces: `Workspace(loader, store)` with `load_folder(path)`, `load_files(paths)`, `reload()`, `cases`, `source`, `file_results`, `source_workbooks()`. Each of the three load methods returns `(body: dict, status: int)`, exactly what `_load` returns today, so the routes are unchanged in shape.

- [ ] **Step 1: Write the failing test**

```python
"""Workspace holds the load; the routes only report it."""
import pytest

from tcm.domain.case import TestCase
from tcm.domain.ports import Snapshot
from tcm.infrastructure.store.memory import InMemoryCaseStore
from tcm.services.workspace import Workspace


class FakeLoader:
    """A CaseLoader that answers from a dict instead of reading .xlsx."""

    def __init__(self, by_folder=None, by_file=None):
        self.by_folder = by_folder or {}
        self.by_file = by_file or {}
        self.calls = []

    def load_from_folder(self, folder_path):
        self.calls.append(("folder", folder_path))
        return self.by_folder.get(folder_path, ([], []))

    def load_from_files(self, file_paths):
        self.calls.append(("files", tuple(file_paths)))
        return self.by_file.get(tuple(file_paths), ([], []))

    def find_workbooks(self, folder_path):
        return list(self.by_folder.get(folder_path, ([], []))[1])


def case(**kw):
    return TestCase(file_name=kw.pop("file_name", "TC.xlsx"),
                    sheet=kw.pop("sheet", "Login"),
                    device=kw.pop("device", "iPhone"), **kw)


def workspace(**kw):
    loader = FakeLoader(**kw)
    return Workspace(loader, InMemoryCaseStore()), loader


def test_a_folder_load_is_remembered_so_reload_can_repeat_it(tmp_path):
    folder = str(tmp_path)
    ws, loader = workspace(by_folder={folder: ([case(case_no="TC-1")], [{"file": "TC.xlsx"}])})

    body, status = ws.load_folder(folder)

    assert status == 200
    assert body["loaded"] == 1
    assert ws.source == {"type": "folder", "value": folder}

    ws.reload()
    assert loader.calls == [("folder", folder), ("folder", folder)]


def test_a_failed_load_leaves_the_previous_one_in_place(tmp_path):
    folder = str(tmp_path)
    ws, _ = workspace(by_folder={folder: ([case(case_no="TC-1")], [])})
    ws.load_folder(folder)

    body, status = ws.load_folder(str(tmp_path / "nope"))

    assert status == 400
    assert "not found" in body["error"].lower()
    assert len(ws.cases) == 1, "a failed load must not empty the store"
    assert ws.source == {"type": "folder", "value": folder}


def test_reloading_before_anything_loaded_is_refused():
    ws, _ = workspace()
    body, status = ws.reload()
    assert status == 400
    assert "No data loaded" in body["error"]


def test_a_file_load_refuses_paths_that_are_not_there(tmp_path):
    ws, _ = workspace()
    body, status = ws.load_files([str(tmp_path / "missing.xlsx")])
    assert status == 400
    assert "not found" in body["error"].lower()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/services/test_workspace.py -q 2>&1 | tail -5`
Expected: collection error — `No module named 'tcm.services.workspace'`.

- [ ] **Step 3: Write `tcm/infrastructure/store/memory.py`**

```python
"""The current load, held in memory.

One process, one load. The database seam: a SqlCaseStore implementing the same
two methods is what a multi-user version swaps in, and nothing in the service
layer changes.
"""
from tcm.domain.ports import Snapshot


class InMemoryCaseStore:
    """Holds one `Snapshot`."""

    def __init__(self):
        self._snapshot = Snapshot()

    def put(self, snapshot: Snapshot) -> None:
        self._snapshot = snapshot

    def get(self) -> Snapshot:
        return self._snapshot
```

With `tcm/infrastructure/store/__init__.py` containing `"""Where a load is kept between requests."""`.

- [ ] **Step 4: Write `tcm/infrastructure/excel/loader.py`**

The reader is a module of functions; the port is an object. This is the adapter, and it adds no logic.

```python
"""The CaseLoader port, answered by the Excel reader."""
from tcm.infrastructure.excel import reader


class ExcelCaseLoader:
    """Reads test cases out of .xlsx workbooks."""

    def load_from_folder(self, folder_path):
        return reader.load_from_folder(folder_path)

    def load_from_files(self, file_paths):
        return reader.load_from_files(file_paths)

    def find_workbooks(self, folder_path):
        return reader.find_workbooks(folder_path)
```

- [ ] **Step 5: Write `tcm/services/workspace.py`**

Move the body of `_load` from `tcm/web/routes.py` verbatim, with `_data[...]` becoming the store.

```python
"""The loaded source, and the cases read from it.

This was a module-level dict in the blueprint. It is an object now for one
reason: a module global cannot be tested without reaching into the module that
owns it, which is what `tests/web/test_api.py` did between every test.

The store is only updated once a load succeeds, so a failed call leaves the
previously loaded data -- and the source `reload` repeats -- untouched.
"""
import os

from tcm.domain.ports import CaseLoader, CaseStore, Snapshot


class Workspace:
    """One loaded source and its cases."""

    def __init__(self, loader: CaseLoader, store: CaseStore):
        self._loader = loader
        self._store = store

    # --- what is loaded now ------------------------------------------------

    @property
    def cases(self):
        return self._store.get().cases

    @property
    def file_results(self):
        return self._store.get().file_results

    @property
    def source(self):
        return self._store.get().source

    # --- loading -----------------------------------------------------------

    def load_folder(self, value):
        path = os.path.abspath(value)
        if not os.path.isdir(path):
            return {"error": f"Folder not found: {value}"}, 400
        cases, file_results = self._loader.load_from_folder(path)
        return self._remember({"type": "folder", "value": path}, cases, file_results)

    def load_files(self, value):
        paths = [os.path.abspath(f) for f in value]
        missing = [f for f in paths if not os.path.isfile(f)]
        if missing:
            return {"error": f"Files not found: {missing}"}, 400
        cases, file_results = self._loader.load_from_files(paths)
        return self._remember({"type": "files", "value": paths}, cases, file_results)

    def reload(self):
        """Re-read whatever source was last accepted."""
        src = self.source
        if not src:
            return {"error": "No data loaded yet. Use /api/load first."}, 400
        if src["type"] == "folder":
            return self.load_folder(src["value"])
        return self.load_files(src["value"])

    def source_workbooks(self):
        """Every workbook the loaded source names, re-globbed rather than remembered.

        A file dropped into the folder since the last load still appears, which
        is what the prepare endpoints check a request's paths against.
        """
        src = self.source
        if not src:
            return []
        if src["type"] == "folder":
            return self._loader.find_workbooks(src["value"])
        return list(src["value"])

    def _remember(self, source, cases, file_results):
        self._store.put(Snapshot(cases=cases, file_results=file_results, source=source))
        return {
            "loaded": len(cases),
            "file_count": len(file_results),
            "file_results": file_results,
        }, 200
```

- [ ] **Step 6: Run the new test**

Run: `.venv/bin/python -m pytest tests/services/test_workspace.py -v 2>&1 | tail -10`
Expected: 4 passed.

- [ ] **Step 7: Point the blueprint at it**

In `tcm/web/routes.py`: delete `_data` and `_load`, and add near the top, beside the other module-level objects that Task 13 will move into the factory:

```python
from tcm.infrastructure.excel.loader import ExcelCaseLoader
from tcm.infrastructure.store.memory import InMemoryCaseStore
from tcm.services.workspace import Workspace

#: Moved into the app factory in the next task; module-level here so this
#: task changes one thing at a time.
_workspace = Workspace(ExcelCaseLoader(), InMemoryCaseStore())
```

Then replace, mechanically:
- `_data["cases"]` → `_workspace.cases`
- `_data["source"]` → `_workspace.source`
- `_load("folder", body["folder"])` → `_workspace.load_folder(body["folder"])`
- `_load("files", body["files"])` → `_workspace.load_files(body["files"])`
- the whole body of `reload_data` → `result, status = _workspace.reload()`
- `runner.source_workbooks(_data["source"])` → `_workspace.source_workbooks()`

Check `tcm/services/preparation.py` still needs its own `source_workbooks`; if nothing calls it any more, leave it — removing it is a logic change and belongs in its own commit.

- [ ] **Step 8: Update the test that reset the global**

In `tests/web/test_api.py`, the reset between tests becomes a reset of the workspace's store. Replace the `routes._data` reset with:

```python
routes._workspace = Workspace(ExcelCaseLoader(), InMemoryCaseStore())
```

- [ ] **Step 9: Run the full suite**

Run: `.venv/bin/python -m pytest 2>&1 | tail -5`
Expected: gate count + 7, all passing.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "$(cat <<'MSG'
Give the loaded source an object instead of a module global

_data and _load were application state and application logic living in a
blueprint. They are a Workspace now, over a CaseLoader and a CaseStore,
which is what lets it be tested without a fixture that reaches into the
module to empty a dict between every test.

The store is still in memory and still one per process: the seam is
placed, the behaviour is unchanged.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Task 12: `IdentityService` — sign-in and the device-code flow

**Files:**
- Create: `tcm/services/identity.py`, `tests/services/test_identity.py`
- Modify: `tcm/web/routes.py`

**Interfaces:**
- Consumes: `tcm.domain.ports.TokenProvider`.
- Produces: `IdentityService(auth, spawn=...)` with `status()`, `begin_login()`, `sign_out()`, `token()`. `begin_login()` returns `(body, status)`; `status()` returns the dict the endpoint serves, login-in-progress folded in.

- [ ] **Step 1: Write the failing test**

```python
"""The device-code flow, without Microsoft."""
import pytest

from tcm.services.identity import IdentityService


class FakeAuth:
    """A TokenProvider that plays back scripted answers."""

    def __init__(self, flow=None, begin_error=None, complete_error=None):
        self.flow = flow or {"user_code": "ABC-123",
                             "verification_uri": "https://microsoft.com/devicelogin",
                             "expires_in": 900}
        self.begin_error = begin_error
        self.complete_error = complete_error
        self.signed_out = False
        self.state = "signed_out"

    def status(self):
        return {"state": self.state}

    def token(self):
        return "token"

    def begin_device_login(self):
        if self.begin_error:
            raise self.begin_error
        return self.flow

    def complete_device_login(self, flow):
        if self.complete_error:
            raise self.complete_error
        self.state = "signed_in"
        return {"ok": True}

    def sign_out(self):
        self.signed_out = True
        self.state = "signed_out"


def inline(fn, *args):
    """Stand-in for the background thread: run it now."""
    fn(*args)


def test_a_login_in_progress_shows_the_code_to_type():
    auth = FakeAuth()
    # Never complete, so the flow stays pending and status can be inspected.
    service = IdentityService(auth, spawn=lambda fn, *a: None)

    body, status = service.begin_login()

    assert status == 200
    assert body["user_code"] == "ABC-123"
    assert service.status()["state"] == "pending"
    assert service.status()["user_code"] == "ABC-123"


def test_a_completed_login_stops_being_pending():
    auth = FakeAuth()
    service = IdentityService(auth, spawn=inline)

    service.begin_login()

    assert auth.state == "signed_in"
    assert service.status()["state"] == "signed_in"


def test_a_failed_login_is_reported_on_the_next_status():
    auth = FakeAuth(complete_error=RuntimeError("expired"))
    service = IdentityService(auth, spawn=inline)

    service.begin_login()

    assert service.status()["error"] == "expired"


def test_signing_out_clears_a_failed_login():
    auth = FakeAuth(complete_error=RuntimeError("expired"))
    service = IdentityService(auth, spawn=inline)
    service.begin_login()

    service.sign_out()

    assert auth.signed_out
    assert "error" not in service.status()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/services/test_identity.py -q 2>&1 | tail -5`
Expected: `No module named 'tcm.services.identity'`.

- [ ] **Step 3: Write `tcm/services/identity.py`**

Move `_login`, `_login_lock`, `_reset_login`, `_spawn` and `_await_login` out of the blueprint verbatim, as methods.

```python
"""Who is signed in to Microsoft Graph, and how far a sign-in has got.

The device flow takes as long as the user takes to type a code into a browser,
which is minutes -- far too long to hold a request open on a single-threaded
dev server. So `begin_login` answers as soon as Microsoft hands back a code and
waits for the rest on a background thread, leaving the outcome where `status`
can report it.

`spawn` is injected so tests run the wait inline.
"""
import logging
import threading

from tcm.domain.ports import TokenProvider

log = logging.getLogger(__name__)


def _thread(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


class IdentityService:
    """One Graph identity, and at most one sign-in in progress."""

    def __init__(self, auth: TokenProvider, spawn=_thread):
        self._auth = auth
        self._spawn = spawn
        self._lock = threading.Lock()
        self._login = {}
        self._reset()

    def _reset(self):
        with self._lock:
            self._login.clear()
            self._login.update({"state": "idle", "user_code": None,
                                "verification_uri": None, "error": None})

    def token(self) -> str:
        return self._auth.token()

    def status(self) -> dict:
        """Who is signed in, or how far a sign-in has got."""
        status = self._auth.status()
        with self._lock:
            pending = self._login["state"] == "pending"
            snapshot = dict(self._login)

        if status["state"] == "signed_in":
            return status
        if pending:
            return {**status, "state": "pending",
                    "user_code": snapshot["user_code"],
                    "verification_uri": snapshot["verification_uri"]}
        if snapshot["error"]:
            return {**status, "error": snapshot["error"]}
        return status

    def begin_login(self):
        """Start a device-code sign-in. Returns `(body, http_status)`."""
        flow = self._auth.begin_device_login()

        with self._lock:
            self._login.update({"state": "pending", "error": None,
                                "user_code": flow.get("user_code"),
                                "verification_uri": flow.get("verification_uri")})

        self._spawn(self._await_login, flow)

        return {
            "user_code": flow.get("user_code"),
            "verification_uri": flow.get("verification_uri"),
            "expires_in": flow.get("expires_in"),
        }, 200

    def sign_out(self) -> dict:
        self._auth.sign_out()
        self._reset()
        return self._auth.status()

    def _await_login(self, flow):
        """Wait out the flow, leaving the outcome where `status` can see it."""
        try:
            self._auth.complete_device_login(flow)
        except Exception as e:
            log.warning("Device login did not complete: %s", e)
            with self._lock:
                self._login.update({"state": "failed", "error": str(e)})
            return
        self._reset()
```

`NotConfigured` stays the route's to catch: it is a 400, and mapping an exception to a status code is the web layer's job.

- [ ] **Step 4: Run the new test**

Run: `.venv/bin/python -m pytest tests/services/test_identity.py -v 2>&1 | tail -10`
Expected: 4 passed.

- [ ] **Step 5: Point the blueprint at it**

In `tcm/web/routes.py`, delete `_login`, `_login_lock`, `_reset_login`, `_spawn`, `_await_login` and the bodies of the three sharepoint routes' state handling. `_auth` stays for now (Task 13 moves it into the factory):

```python
_identity = IdentityService(_auth)
```

- `sharepoint_status` → `return jsonify(_identity.status())`
- `sharepoint_login` → keep the `try/except NotConfigured → 400`, `except Exception → 502` around `_identity.begin_login()`
- `sharepoint_logout` → `return jsonify(_identity.sign_out())`
- `publish_report`'s `_auth.token()` → `_identity.token()`

- [ ] **Step 6: Update the test that replaced `_spawn`**

`tests/web/test_api_sharepoint.py` replaces `routes._spawn` to run inline. It now replaces the service's:

```python
routes._identity = IdentityService(fake_auth, spawn=lambda fn, *a: fn(*a))
```

- [ ] **Step 7: Run the full suite**

Run: `.venv/bin/python -m pytest 2>&1 | tail -5`
Expected: gate count + 11, all passing.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "$(cat <<'MSG'
Give the sign-in flow an object instead of a module dict and a lock

_login, _login_lock, _spawn and _await_login were a state machine living
in a blueprint, reachable only by monkeypatching the module. The thread
strategy is injected now, so the test that used to replace _spawn
constructs a service instead.

Behaviour is unchanged, including which exception becomes which status
code -- that stays the route's job.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Task 13: Split the blueprint and wire a composition root

The last structural task. `tcm/web/routes.py` becomes five blueprints of 60–110 lines, and `create_app` builds the concrete implementations.

**Files:**
- Create: `tcm/web/blueprints/__init__.py`, `tcm/web/blueprints/{source,analytics,prepare,settings,sharepoint,pages}.py`
- Modify: `tcm/web/app.py`
- Delete: `tcm/web/routes.py`

**Interfaces:**
- Consumes: `Workspace`, `IdentityService`, the services, the ports.
- Produces: each module exports one `Blueprint`; `create_app()` registers all six. Services are reached through `current_app.extensions["workspace"]` and `["identity"]`.

- [ ] **Step 1: Add the accessors**

In `tcm/web/blueprints/__init__.py`:

```python
"""One blueprint per resource.

A blueprint reads the request, calls a service and jsonifies the answer. It
holds no state: the services live on the app, which is what lets one be built
differently for a test without reaching into a module.
"""
from flask import current_app


def workspace():
    """The Workspace this app was built with."""
    return current_app.extensions["workspace"]


def identity():
    """The IdentityService this app was built with."""
    return current_app.extensions["identity"]
```

- [ ] **Step 2: Split the routes**

Move each route into its blueprint **verbatim**, changing only `_workspace` → `workspace()` and `_identity` → `identity()`. Each file begins:

```python
from flask import Blueprint, jsonify, request

from tcm.web.blueprints import workspace

bp = Blueprint("source", __name__)
```

The split, by route:

| Module | Blueprint name | Routes |
|---|---|---|
| `source.py` | `source` | `/api/load`, `/api/reload`, `/api/browse`, `/api/prepare/files` |
| `analytics.py` | `analytics` | `/api/statuses`, `/api/cases`, `/api/summary`, `/api/file`, `/api/daily`, `/api/productivity` |
| `prepare.py` | `prepare` | `/api/prepare/tool-data`, `/api/prepare/clear` |
| `settings.py` | `settings` | `/api/config`, `PUT /api/config/<name>` |
| `sharepoint.py` | `sharepoint` | `/api/sharepoint/status`, `/login`, `/logout`, `/api/report/publish` |
| `pages.py` | `pages` | `/` |

`/api/prepare/files` goes to `source.py`, not `prepare.py`: it reports what the loaded source contains and writes nothing, so it belongs with loading rather than with the two endpoints that overwrite workbooks.

**Watch the name collision.** `tcm/web/blueprints/settings.py` and `tcm/settings.py` are both importable as `settings`. In `app.py`, import the blueprint module aliased — `from tcm.web.blueprints import settings as settings_bp` — and keep `from tcm import settings`. Inside the blueprint itself, import the config module as `from tcm import settings as app_settings` if it needs one at all.

`_requested_files` moves to `prepare.py` as a module-level helper — it is a request guard, which is genuinely the web layer's job — and calls `workspace().source_workbooks()`.

- [ ] **Step 3: Rewrite `create_app` as the composition root**

```python
def create_app(workspace=None, identity=None):
    """Build the app.

    Args:
        workspace: A `Workspace`, or None to build the shipped one over the
            Excel reader and an in-memory store.
        identity: An `IdentityService`, or None to build one over Graph.

    Both are arguments so a test can build an app over fakes without patching
    a module; nothing in the app changes them after construction.
    """
    app = Flask(__name__, template_folder=..., static_folder=...)

    app.extensions["workspace"] = workspace or Workspace(
        ExcelCaseLoader(), InMemoryCaseStore())
    app.extensions["identity"] = identity or IdentityService(GraphAuth(
        client_id=settings.GRAPH_CLIENT_ID,
        tenant_id=settings.GRAPH_TENANT_ID,
        scopes=settings.GRAPH_SCOPES,
        cache_path=settings.GRAPH_TOKEN_CACHE,
    ))

    for module in (source, analytics, prepare, settings_bp, sharepoint, pages):
        app.register_blueprint(module.bp)

    return app
```

- [ ] **Step 4: Update the test fixtures**

`tests/web/conftest.py` (or the `client` fixture wherever it lives) builds the app per test instead of resetting globals:

```python
@pytest.fixture
def client():
    app = create_app(workspace=Workspace(ExcelCaseLoader(), InMemoryCaseStore()))
    app.config["TESTING"] = True
    return app.test_client()
```

Delete the between-test reset entirely — a fresh app per test is what replaces it.

- [ ] **Step 5: Delete the old module**

```bash
git rm tcm/web/routes.py
```

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest 2>&1 | tail -5`
Expected: the gate count, all passing.

- [ ] **Step 7: Check every route still exists**

```bash
.venv/bin/python -c "
from tcm.web.app import create_app
rules = sorted(str(r) for r in create_app().url_map.iter_rules())
for r in rules: print(r)
print(len(rules), 'rules')
"
```
Expected: **20 rules** — 18 `/api/*`, `/`, and `/static/<path:filename>`. This was verified against the pre-split app, so a different count means the split dropped a route; diff the two lists rather than guessing which.

- [ ] **Step 8: Exercise the app by hand**

Start it, load the sample workbooks, and click through all seven views. This is the step no test covers.

```bash
.venv/bin/python -m tools.generate_samples --out samples/generated --seed 1
.venv/bin/python app.py
```
Expected: Summary's three buckets render, a status figure opens Detail on that status, a file name opens the File view, Tools lists the workbooks, Config saves and the figures change.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "$(cat <<'MSG'
Split the blueprint by resource and build the app from a root

506 lines and five unrelated resources in one module, holding the
application's state as well. The routes are jsonify wrappers now -- the
rule CLAUDE.md always stated -- and the services are built in the
factory, so a test builds an app over fakes instead of reaching into a
module to empty a dict.

/api/prepare/files goes with loading rather than with the two endpoints
that overwrite workbooks: it reports and writes nothing.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Task 14: The remaining two ports

`ConfigRepository` and `FilePicker` have implementations but nothing takes them as arguments yet.

**Files:**
- Create: `tcm/infrastructure/config_repo.py`
- Modify: `tcm/services/settings_store.py`, `tcm/infrastructure/dialog.py`, `tcm/web/blueprints/source.py`, `tests/services/test_config_store.py`

**Interfaces:**
- Consumes: `tcm.domain.ports` (`ConfigRepository`, `FilePicker`).
- Produces: `JsonFileConfigRepository` with `read_text(path)` / `write_text(path, text)`; `NativeDialog` with `pick_folder` / `pick_files`.

- [ ] **Step 1: Write `tcm/infrastructure/config_repo.py`**

Move `_write_atomically` out of `settings_store.py` verbatim.

```python
"""Reading and writing the editable config files on disk.

The write is atomic because a half-written result_status.json does not make the
taxonomy wrong -- it stops the app booting, since the vocabularies load at
import. So the text goes to a temp file beside the target and os.replace swaps
it in, which is one filesystem operation.
"""
import os
import tempfile


class JsonFileConfigRepository:
    """Config files as JSON on the local filesystem."""

    def read_text(self, path: str) -> str:
        with open(path, encoding="utf-8") as f:
            return f.read()

    def write_text(self, path: str, text: str) -> None:
        directory = os.path.dirname(os.path.abspath(path))
        fd, temp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(temp, path)
        except BaseException:
            if os.path.exists(temp):
                os.unlink(temp)
            raise
```

- [ ] **Step 2: Have `settings_store` take one**

`read_all()` and `save()` become methods on a small `SettingsStore` class taking a `ConfigRepository`, or keep the module functions and add a module-level `_repo = JsonFileConfigRepository()` that both use. **Take the second option** — the module-level functions are what `/api/config` wraps, and converting them to a class is a logic change this plan does not need.

- [ ] **Step 3: Wrap the dialog**

```python
class NativeDialog:
    """The FilePicker port, answered by the OS dialog."""

    def pick_folder(self, initial=None):
        return pick_folder(initial)

    def pick_files(self, initial=None):
        return pick_files(initial)
```

appended to `tcm/infrastructure/dialog.py`.

- [ ] **Step 4: Run the ports test and the full suite**

Add to `tests/domain/test_ports.py`:

```python
def test_the_json_repository_is_a_config_repository():
    from tcm.infrastructure.config_repo import JsonFileConfigRepository
    assert issubclass(JsonFileConfigRepository, ports.ConfigRepository)


def test_the_native_dialog_is_a_file_picker():
    from tcm.infrastructure.dialog import NativeDialog
    assert issubclass(NativeDialog, ports.FilePicker)
```

Run: `.venv/bin/python -m pytest 2>&1 | tail -5`
Expected: gate count + 2, all passing.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "$(cat <<'MSG'
Answer the last two ports

The atomic write moves to the repository that owns it, and the native
dialog gains the object form the port describes. Both had exactly one
caller and neither changes behaviour; what changes is that the seam a
database-backed settings store would be cut at is now visible.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Task 15: Final documentation pass

**Files:**
- Modify: `CLAUDE.md`, `README.md`

- [ ] **Step 1: Document the six ports and the composition root in `CLAUDE.md`**

Add a section stating: where a port exists, a service takes it as a constructor argument; the rule bounding the set; and that `create_app` is the only place implementations are chosen.

- [ ] **Step 2: Correct "seven methods wide"**

`CLAUDE.md` says the Graph workbook interface is "deliberately seven methods wide". It is eight: `worksheet_names`, `used_range`, `write_values`, `delete_rows`, `table_at`, `table_rows`, `table_add_rows`, `table_delete_row`. The spec inherited the error from it. Fix both files.

- [ ] **Step 3: Replace the "Out of scope by decision" paragraph**

It currently says the `_data` dict, `_auth` and the `_login` dict are deliberate module-level state. They are objects now. Replace it with what is *still* true and now matters more: the four vocabulary singletons are process-global and `settings_store.save()` mutates them in place via `adopt()`, which a multi-user version will have to face.

- [ ] **Step 4: Verify**

Run: `grep -n "_data\|_login\|_auth\b" CLAUDE.md`
Expected: only the new paragraph about the vocabulary singletons.

Run: `grep -n "seven methods" CLAUDE.md docs/superpowers/specs/2026-09-20-project-restructure-design.md`
Expected: no hits.

Run: `.venv/bin/python -m pytest 2>&1 | tail -3`
Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "$(cat <<'MSG'
Record the ports, the composition root, and what is still global

The paragraph calling the in-memory store a deliberate single-user
choice describes code that no longer exists. What is still process-wide
is the four vocabulary singletons and the adopt() that mutates them,
which is the thing a multi-user version will actually have to face.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Verification checklist

Before calling this plan done:

- [ ] `.venv/bin/python -m pytest` passes, with a count ≥ 450 + the new tests
- [ ] `tests/test_layering.py` passes with all four layers populated
- [ ] `.venv/bin/python app.py` serves `/` and all seven views work in both themes
- [ ] `grep -rn "^\(from\|import\) \(parser\|aggregate\|config_store\|prepare\|report\|sharepoint\|api\)\b" --include='*.py' .` returns nothing outside `.venv`
- [ ] `git status` is clean
- [ ] `CLAUDE.md` names no path that no longer exists

## Not in this plan

Phase 3 (the two oversized JS view modules) and phase 4 (`app.css` and
`index.html`) are separate subsystems with their own verification story — no
test framework, exercised by hand — and get their own plans once this one
lands. Multi-user, sessions, a database, per-user Graph tokens and the
`adopt()` race are out of scope per the spec.
