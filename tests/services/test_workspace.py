"""Workspace holds the load; the routes only report it."""
import os

import pytest

from tcm.domain import case as models
from tcm.infrastructure.excel.reader import LOCK_FILE_PREFIX
from tcm.infrastructure.store.memory import InMemoryCaseStore
from tcm.services.workspace import Workspace


class FakeLoader:
    """A CaseLoader that answers from a dict instead of reading .xlsx.

    `workbooks_by_folder` answers `find_workbooks`, separately from
    `by_folder` (which answers a load): `source_workbooks()` re-globs a folder
    rather than remembering what a load once found, and a fake that answered
    both from the same dict could not tell the two apart.
    """

    def __init__(self, by_folder=None, by_file=None, workbooks_by_folder=None):
        self.by_folder = by_folder or {}
        self.by_file = by_file or {}
        self.workbooks_by_folder = workbooks_by_folder or {}
        self.calls = []

    def load_from_folder(self, folder_path):
        self.calls.append(("folder", folder_path))
        return self.by_folder.get(folder_path, ([], []))

    def load_from_files(self, file_paths):
        self.calls.append(("files", tuple(file_paths)))
        return self.by_file.get(tuple(file_paths), ([], []))

    def find_workbooks(self, folder_path):
        self.calls.append(("find_workbooks", folder_path))
        return list(self.workbooks_by_folder.get(folder_path, []))

    def exclude_lock_files(self, paths):
        self.calls.append(("exclude_lock_files", tuple(paths)))
        return [p for p in paths if not os.path.basename(p).startswith(LOCK_FILE_PREFIX)]


def case(**kw):
    """`models.TestCase` is reached through the module rather than imported by
    name: pytest tries to collect any module-level class called `Test*` and
    warns when it cannot. See `tests/services/test_aggregate.py`.
    """
    return models.TestCase(file_name=kw.pop("file_name", "TC.xlsx"),
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


# --- source_workbooks() ------------------------------------------------
#
# What `_requested_files()` and `prepare_files()` check a write against, so a
# lock file slipping through here is a loosened write guard, not a cosmetic
# miscount.

def test_source_workbooks_excludes_excel_lock_files_from_a_file_list(tmp_path):
    """A workbook open in Excel leaves a `~$name.xlsx` lock file beside it.

    Regression test: `source_workbooks()`'s files branch once returned
    `list(source["value"])` verbatim, so a lock file picked up by a multi-select
    was treated as part of the loaded source -- and these endpoints write to
    the files they are handed.
    """
    good = tmp_path / "TC.xlsx"
    good.touch()
    lock = tmp_path / f"{LOCK_FILE_PREFIX}TC.xlsx"
    lock.touch()
    ws, _ = workspace(by_file={(str(good), str(lock)): ([], [])})

    ws.load_files([str(good), str(lock)])

    assert ws.source_workbooks() == [str(good)]


def test_source_workbooks_for_a_folder_is_re_globbed_not_remembered(tmp_path):
    """A workbook dropped into the folder after the load still appears.

    `source_workbooks()` calls the loader's `find_workbooks` fresh each time
    rather than replaying what a `load_folder` once found -- otherwise a file
    added since the load would be invisible to the Tools panel and to the
    write guard that checks a prepare request's paths against it.
    """
    folder = str(tmp_path)
    ws, loader = workspace(by_folder={folder: ([case(case_no="TC-1")], [])})
    ws.load_folder(folder)
    loader.workbooks_by_folder[folder] = [str(tmp_path / "TC.xlsx")]

    assert ws.source_workbooks() == [str(tmp_path / "TC.xlsx")]

    loader.workbooks_by_folder[folder] = [
        str(tmp_path / "TC.xlsx"), str(tmp_path / "New.xlsx")]

    assert ws.source_workbooks() == [
        str(tmp_path / "TC.xlsx"), str(tmp_path / "New.xlsx")]
