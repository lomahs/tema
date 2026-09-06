"""The native picker, with the OS dialog stubbed out.

pytest cannot drive a real Tk dialog, so every test here replaces
`subprocess.run` and asserts on what the parent process does with the child's
output — the parsing, normalising and error handling that actually hold the
Windows/macOS differences.
"""
import json
import os
import subprocess

import pytest

from api import filedialog
from api.filedialog import DialogError, pick_files, pick_folder


def stub_dialog(monkeypatch, *, paths=None, returncode=0, stderr="", record=None):
    """Replace the dialog subprocess with one returning `paths`.

    `record`, when given, is a dict that receives the call's kwargs so a test
    can assert on how the child was launched.
    """
    stdout = json.dumps(paths if paths is not None else [])

    def fake_run(cmd, **kwargs):
        if record is not None:
            record.update(kwargs)
            record["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(filedialog.subprocess, "run", fake_run)


def test_picking_one_file_returns_that_path(monkeypatch):
    stub_dialog(monkeypatch, paths=["/data/TC.xlsx"])
    assert pick_files() == ["/data/TC.xlsx"]


def test_picking_several_files_returns_every_path(monkeypatch):
    stub_dialog(monkeypatch, paths=["/data/TC one.xlsx", "/data/TC two.xlsx"])
    assert pick_files() == ["/data/TC one.xlsx", "/data/TC two.xlsx"]


def test_a_path_containing_spaces_survives_intact(monkeypatch):
    """The Tcl-list-as-string gotcha: a naive split would break this apart."""
    stub_dialog(monkeypatch, paths=["/My Test Cases/sprint 12.xlsx"])
    assert pick_files() == ["/My Test Cases/sprint 12.xlsx"]


def test_cancelling_the_file_dialog_returns_no_paths(monkeypatch):
    stub_dialog(monkeypatch, paths=[])
    assert pick_files() == []


def test_picking_a_folder_returns_that_directory(monkeypatch):
    stub_dialog(monkeypatch, paths=["/data/project1"])
    assert pick_folder() == ["/data/project1"]


def test_cancelling_the_folder_dialog_returns_no_paths(monkeypatch):
    stub_dialog(monkeypatch, paths=[])
    assert pick_folder() == []


def test_returned_paths_are_normalised(monkeypatch):
    """Tk hands back unnormalised paths; the parent tidies them before use."""
    stub_dialog(monkeypatch, paths=["/data/./project1/"])
    assert pick_folder() == [os.path.normpath("/data/./project1/")]


def test_the_initial_directory_is_passed_to_the_dialog(monkeypatch):
    record = {}
    stub_dialog(monkeypatch, paths=[], record=record)
    pick_folder("/data/last-used")
    assert "/data/last-used" in record["cmd"]


def test_windows_launches_the_dialog_without_a_console_window(monkeypatch):
    """Otherwise every Browse click flashes a cmd window on Windows."""
    record = {}
    monkeypatch.setattr(filedialog.os, "name", "nt")
    monkeypatch.setattr(filedialog.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    stub_dialog(monkeypatch, paths=[], record=record)

    pick_folder()

    assert record.get("creationflags") == 0x08000000


def test_posix_does_not_pass_windows_creation_flags(monkeypatch):
    record = {}
    monkeypatch.setattr(filedialog.os, "name", "posix")
    stub_dialog(monkeypatch, paths=[], record=record)

    pick_folder()

    assert "creationflags" not in record


# --- bringing the dialog to the front ---------------------------------------
# macOS hands foreground to an *application*, and a child spawned by the server
# has never been activated — so `lift()` and `-topmost` alone leave the dialog
# behind the browser. See `_bring_to_front`.

def record_run(monkeypatch, *, raises=None):
    """Capture the commands `_bring_to_front` shells out to."""
    calls = []

    def fake_run(cmd, **kwargs):
        if raises is not None:
            raise raises
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(filedialog.subprocess, "run", fake_run)
    return calls


def test_macos_activates_the_dialog_process_by_its_pid(monkeypatch):
    monkeypatch.setattr(filedialog.sys, "platform", "darwin")
    calls = record_run(monkeypatch)

    filedialog._bring_to_front(4242)

    assert len(calls) == 1, "expected exactly one activation call"
    command = " ".join(calls[0])
    assert "osascript" in command
    assert "4242" in command, "must activate this process, not whatever is frontmost"


def test_other_platforms_do_not_shell_out_to_osascript(monkeypatch):
    monkeypatch.setattr(filedialog.sys, "platform", "win32")
    calls = record_run(monkeypatch)

    filedialog._bring_to_front(4242)

    assert calls == []


def test_a_blocked_activation_still_lets_the_dialog_open(monkeypatch):
    """Automation permission can be denied; a dialog behind beats no dialog."""
    monkeypatch.setattr(filedialog.sys, "platform", "darwin")
    record_run(monkeypatch, raises=OSError("osascript not found"))

    filedialog._bring_to_front(4242)  # must not raise


def test_a_child_that_fails_raises_dialog_error(monkeypatch):
    stub_dialog(monkeypatch, returncode=2, stderr="tkinter unavailable: No module named '_tkinter'")
    with pytest.raises(DialogError, match="tkinter unavailable"):
        pick_folder()


def test_unreadable_child_output_raises_dialog_error(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="not json", stderr="")

    monkeypatch.setattr(filedialog.subprocess, "run", fake_run)
    with pytest.raises(DialogError):
        pick_folder()


def test_a_hanging_dialog_raises_dialog_error(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 300)

    monkeypatch.setattr(filedialog.subprocess, "run", fake_run)
    with pytest.raises(DialogError):
        pick_folder()
