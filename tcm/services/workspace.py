"""The loaded source, and the cases read from it.

This was a module-level dict in the blueprint. It is an object now for one
reason: a module global cannot be tested without reaching into the module that
owns it, which is what `tests/web/test_api.py` did between every test.

The store is only updated once a load succeeds, so a failed call leaves the
previously loaded data -- and the source `reload` repeats -- untouched.

A snapshot opened from the database goes into the same store a load does, with
`origin` set; a load or reload clears it, which is what makes Reload the way
back to live data.
"""
import os

from tcm.domain.ports import CaseLoader, CaseStore, Snapshot, SnapshotRepository
from tcm.services.aggregation import compare_cases, compared_cases

_NO_STORE = {"error": "Snapshots are not available: no database is configured."}


class Workspace:
    """One loaded source and its cases, and the snapshots kept of them."""

    def __init__(self, loader: CaseLoader, store: CaseStore,
                 snapshots: SnapshotRepository = None):
        self._loader = loader
        self._store = store
        self._snapshots = snapshots

    # --- what is loaded now ------------------------------------------------

    @property
    def origin(self):
        """None for a live load; the snapshot's `{id, taken_at, label}` otherwise."""
        return self._store.get().origin

    def state(self) -> dict:
        """What is loaded now, in the shape a load answers with, plus where it came from."""
        snap = self._store.get()
        return {"loaded": len(snap.cases), "file_count": len(snap.file_results),
                "file_results": snap.file_results, "source": snap.source,
                "origin": snap.origin}

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
        is what the prepare endpoints check a request's paths against. An
        explicit file list is filtered through the loader too: a workbook open
        in another program leaves a lock file beside it, and a multi-select
        that swept one up must not hand a write guard something to treat as
        part of the source.
        """
        src = self.source
        if not src:
            return []
        if src["type"] == "folder":
            return self._loader.find_workbooks(src["value"])
        return self._loader.exclude_lock_files(src["value"])

    # --- snapshots -----------------------------------------------------------

    def save_snapshot(self, label: str = ""):
        if self._snapshots is None:
            return _NO_STORE, 400
        snap = self._store.get()
        if snap.source is None and not snap.file_results:
            return {"error": "Nothing is loaded — load test cases before saving a snapshot."}, 400
        if snap.origin is not None:
            # A copy would be stamped now while holding old data, and would
            # become the newest -- the one the next start restores.
            return {"error": "A snapshot is on screen, not live data. "
                             "Reload the source before saving a snapshot."}, 400
        return self._snapshots.save(snap, label), 201

    def snapshots(self) -> list:
        return self._snapshots.list() if self._snapshots else []

    def open_snapshot(self, snapshot_id: int):
        if self._snapshots is None:
            return _NO_STORE, 400
        snap = self._snapshots.load(snapshot_id)
        if snap is None:
            return {"error": f"No snapshot with id {snapshot_id}"}, 404
        self._store.put(snap)
        return self.state(), 200

    def delete_snapshot(self, snapshot_id: int):
        if self._snapshots is None:
            return _NO_STORE, 400
        if not self._snapshots.delete(snapshot_id):
            return {"error": f"No snapshot with id {snapshot_id}"}, 404
        return {"deleted": snapshot_id}, 200

    def restore_latest(self) -> bool:
        """Put the newest snapshot in the store. False when there is none."""
        if self._snapshots is None:
            return False
        sid = self._snapshots.latest_id()
        if sid is None:
            return False
        self._store.put(self._snapshots.load(sid))
        return True

    def compare(self, base_id: int, head_id: int):
        if self._snapshots is None:
            return _NO_STORE, 400
        base, head = self._snapshots.load(base_id), self._snapshots.load(head_id)
        missing = [i for i, s in ((base_id, base), (head_id, head)) if s is None]
        if missing:
            return {"error": f"No snapshot with id {missing[0]}"}, 404
        return {"base": base.origin, "head": head.origin,
                **compare_cases(base.cases, head.cases)}, 200

    def compared_cases(self, base_id: int, head_id: int, was, now):
        """The cases behind one move of `compare` — see `compared_cases`."""
        if self._snapshots is None:
            return _NO_STORE, 400
        base, head = self._snapshots.load(base_id), self._snapshots.load(head_id)
        missing = [i for i, s in ((base_id, base), (head_id, head)) if s is None]
        if missing:
            return {"error": f"No snapshot with id {missing[0]}"}, 404
        return {"cases": compared_cases(base.cases, head.cases, was, now)}, 200

    def _remember(self, source, cases, file_results):
        self._store.put(Snapshot(cases=cases, file_results=file_results, source=source))
        return {
            "loaded": len(cases),
            "file_count": len(file_results),
            "file_results": file_results,
        }, 200
