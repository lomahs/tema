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
