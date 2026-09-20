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

    def _remember(self, source, cases, file_results):
        self._store.put(Snapshot(cases=cases, file_results=file_results, source=source))
        return {
            "loaded": len(cases),
            "file_count": len(file_results),
            "file_results": file_results,
        }, 200
