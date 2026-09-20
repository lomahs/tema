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
