"""Native folder / file dialogs, run in a child process.

The dialog cannot be opened from the Flask request thread: on macOS Tk must own
the main thread of its process, and Flask serves requests on worker threads.
So each dialog runs as a short-lived `python -c` child that owns its own main
thread, prints the chosen paths as JSON, and exits. That also sidesteps the
"second Tk root in one process" problem when Browse is clicked repeatedly, and
behaves the same on Windows and macOS.

Only the app's own UI reaches this, and only because the server is local — the
same assumption `/api/load` already makes by accepting arbitrary server paths.
"""
import json
import logging
import os
import subprocess
import sys

log = logging.getLogger(__name__)

#: Give up on a dialog nobody ever answers, so a request cannot hang forever.
DIALOG_TIMEOUT_SECONDS = 300

FILE_TYPES = [("Excel workbooks", "*.xlsx"), ("All files", "*.*")]


class DialogError(RuntimeError):
    """The dialog could not be shown — tkinter missing, crashed, or timed out."""


#: Project root, so the child can import this module back.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The child re-imports this module rather than carrying the dialog logic as one
# big string, which keeps that logic readable and unit-testable.
_CHILD_BOOTSTRAP = (
    "import sys; sys.path.insert(0, {root!r}); "
    "from api.filedialog import _child_main; _child_main()"
).format(root=_PROJECT_ROOT)


def _bring_to_front(pid: int) -> None:
    """Make the dialog's own process the frontmost application (macOS).

    `lift()`, `focus_force()` and `-topmost` all act on a window *within* its
    application. macOS grants foreground per application, and a child spawned by
    the server was never activated — so without this the dialog opens behind the
    browser. Activating by pid rather than by name avoids grabbing the wrong
    interpreter when several are running.

    Best-effort: Automation permission may be refused, and a dialog behind the
    browser still beats no dialog at all.
    """
    if sys.platform != "darwin":
        return
    script = (
        'tell application "System Events" to set frontmost of '
        f"(first process whose unix id is {pid}) to true"
    )
    try:
        subprocess.run(["/usr/bin/osascript", "-e", script],
                       capture_output=True, timeout=5)
    except Exception as e:  # noqa: BLE001 - never let this sink the dialog
        log.debug("Could not bring the dialog to the front: %s", e)


def _child_main() -> None:
    """Entry point for the dialog child process. Prints picked paths as JSON."""
    import json as _json

    try:
        import tkinter
        from tkinter import filedialog as tk_filedialog
    except Exception as e:
        sys.stderr.write(f"tkinter unavailable: {e}")
        raise SystemExit(2)

    mode, initial_arg, file_types_arg = sys.argv[1], sys.argv[2], sys.argv[3]
    initial = initial_arg or None
    file_types = [tuple(t) for t in _json.loads(file_types_arg)]

    root = tkinter.Tk()
    root.withdraw()
    # Register as a GUI process before asking to be activated.
    root.update()
    _bring_to_front(os.getpid())
    root.attributes("-topmost", True)
    root.lift()
    root.focus_force()

    if mode == "folder":
        picked = tk_filedialog.askdirectory(initialdir=initial, mustexist=True)
        paths = [picked] if picked else []
    else:
        picked = tk_filedialog.askopenfilenames(initialdir=initial, filetypes=file_types)
        # askopenfilenames may hand back a Tcl list *string* rather than a tuple,
        # notably on Windows. Letting Tcl split it keeps paths with spaces whole.
        paths = list(root.tk.splitlist(picked))

    root.destroy()
    sys.stdout.write(_json.dumps(paths))


def _run_dialog(mode: str, initial: str | None) -> list[str]:
    """Open one dialog and return the chosen paths, `[]` if it was cancelled."""
    cmd = [
        sys.executable, "-c", _CHILD_BOOTSTRAP,
        mode, initial or "", json.dumps(FILE_TYPES),
    ]
    kwargs = {}
    if os.name == "nt":
        # Without this every Browse click flashes a console window.
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=DIALOG_TIMEOUT_SECONDS, **kwargs,
        )
    except subprocess.TimeoutExpired:
        raise DialogError("The file dialog timed out waiting for a selection.")
    except OSError as e:
        raise DialogError(f"Could not start the file dialog: {e}")

    if proc.returncode != 0:
        detail = (proc.stderr or "").strip() or f"exit code {proc.returncode}"
        raise DialogError(detail)

    try:
        paths = json.loads(proc.stdout)
    except ValueError:
        raise DialogError("The file dialog returned unreadable output.")

    # Tk returns forward slashes even on Windows; normalise so the path matches
    # what the user would type or paste.
    return [os.path.normpath(p) for p in paths]


def pick_folder(initial: str | None = None) -> list[str]:
    """Ask for one folder. Returns `[path]`, or `[]` if cancelled."""
    return _run_dialog("folder", initial)


def pick_files(initial: str | None = None) -> list[str]:
    """Ask for one or more .xlsx files. Returns the paths, `[]` if cancelled."""
    return _run_dialog("files", initial)
