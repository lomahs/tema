"""Scope -> scope-group classification, driven by a JSON config.

The Summary view reports FPT work and JP work as separate tables, because they
are separate commitments and adding them together answers no question anyone
asks. Which Scope strings belong to which table is data, not code — the same
reasoning as `parser/status.py`: a team that renames a scope, or wants a third
table, edits `parser/scope_groups.json` and nothing else.

Every scope reaches exactly one group. Anything the config does not name — a
typo, or a scope nobody has configured yet — lands in the fallback group, so
the tables always add up to every case that was loaded.

A blank Scope is a different thing again, and `is_unscoped` is where that is
decided: a row with no Scope names no commitment, so it is not a case and the
reader never builds one. The fallback group therefore holds only scopes that
were written down and not recognised.
"""
import json
import logging
import os
from dataclasses import dataclass

from tcm.settings import CONFIG_DIR

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join(CONFIG_DIR, "scope_groups.json")


@dataclass(frozen=True)
class ScopeGroup:
    key: str
    label: str
    #: Whether this group's cases are part of the plan the figures are read
    #: against. False keeps the group's own Summary table -- the count has to
    #: stay visible -- and leaves it out of everything that adds groups
    #: together. Absent from a config means True, so nothing changes for a
    #: config written before the field existed.
    counted: bool = True
    #: Whether this is the catch-all group. Exactly one group carries it, it is
    #: always last, and it is never `counted`. Summary reports the three roles
    #: -- counted, excluded, catch-all -- as three tables, and this is what
    #: tells the three apart without the browser naming a scope of its own.
    fallback: bool = False

    def to_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "counted": self.counted,
                "fallback": self.fallback}


class ScopeSet:
    """An ordered set of scope groups plus the Scope strings that map onto them."""

    def __init__(self, groups: list[ScopeGroup], lookup: dict[str, str], fallback_key: str):
        self.groups = groups
        self.keys = [g.key for g in groups]
        #: The groups whose cases the cross-cutting figures add up, and its
        #: complement -- the same pair, and the same reasoning, as
        #: `StatusSet.counted` / `StatusSet.excluded`. `keys` says what exists;
        #: this says what the denominator is made of.
        self.counted = [g.key for g in groups if g.counted]
        self.excluded = [g.key for g in groups if not g.counted]
        self._lookup = lookup
        self._fallback_key = fallback_key

    @classmethod
    def load(cls, path: str = DEFAULT_CONFIG_PATH) -> "ScopeSet":
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return cls.from_dict(raw, source=path)

    def adopt(self, other: "ScopeSet") -> None:
        """Become `other`, in place — see `StatusSet.adopt` for why."""
        self.__dict__.update(other.__dict__)

    @classmethod
    def from_dict(cls, raw: dict, source: str = "<dict>") -> "ScopeSet":
        entries = raw.get("groups")
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"{source}: 'groups' must be a non-empty list")

        groups: list[ScopeGroup] = []
        lookup: dict[str, str] = {}

        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ValueError(f"{source}: groups[{i}] must be an object")
            key = entry.get("key")
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"{source}: groups[{i}] needs a non-empty 'key'")
            key = key.strip()
            if any(g.key == key for g in groups):
                raise ValueError(f"{source}: duplicate scope group key '{key}'")

            groups.append(ScopeGroup(key=key, label=str(entry.get("label") or key),
                                     counted=not entry.get("excluded")))

            values = entry.get("match")
            if not isinstance(values, list) or not values:
                raise ValueError(f"{source}: scope group '{key}' needs a non-empty 'match' list")
            for value in values:
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{source}: scope group '{key}' has an empty 'match' value")
                token = value.strip().casefold()
                if token in lookup:
                    raise ValueError(
                        f"{source}: scope '{value}' is matched by both "
                        f"'{lookup[token]}' and '{key}'"
                    )
                lookup[token] = key

        # The fallback is a group in its own right and always last: it is what a
        # blank or unrecognised Scope becomes, so the tables account for every
        # case rather than quietly dropping the ones nobody configured.
        fallback = raw.get("fallback")
        if not isinstance(fallback, dict):
            raise ValueError(f"{source}: 'fallback' must be an object naming the catch-all group")
        fb_key = fallback.get("key")
        if not isinstance(fb_key, str) or not fb_key.strip():
            raise ValueError(f"{source}: 'fallback' needs a non-empty 'key'")
        fb_key = fb_key.strip()
        if any(g.key == fb_key for g in groups):
            raise ValueError(f"{source}: fallback key '{fb_key}' duplicates a configured group")
        if fb_key.casefold() in lookup:
            raise ValueError(f"{source}: fallback '{fb_key}' is also a 'match' value")
        # The fallback never counts, and the config does not get a say.
        #
        # It is the group an unrecognised scope lands in, and an unrecognised
        # scope is not a commitment anybody made -- so it cannot sit in the
        # denominator progress is read against. Summary gives it a table of its
        # own, drawn whenever it holds anything, which is where these cases stay
        # visible; `"excluded"` on the fallback is therefore not refused any
        # more, it is simply redundant and ignored.
        #
        # What this costs is worth stating: a misspelt Scope now reaches no
        # figure in the app except that table. The guarantee the old rule was
        # really making -- that *something* counts -- is the one below, which is
        # what stops a config leaving every figure in the app reading zero.
        counted_groups = [g.key for g in groups if g.counted]
        if not counted_groups:
            raise ValueError(
                f"{source}: at least one group other than the fallback must count "
                f"toward the total; every group here is 'excluded', which would "
                f"leave every figure in the app reading zero"
            )

        groups.append(ScopeGroup(key=fb_key, label=str(fallback.get("label") or fb_key),
                                 counted=False, fallback=True))
        return cls(groups, lookup, fb_key)

    @staticmethod
    def is_unscoped(scope) -> bool:
        """True for a Scope cell nobody filled in.

        A blank Scope is not an unrecognised scope: it is a row that names no
        commitment at all -- a section heading, a spacer, the tail of a device
        block that was sized generously. Such a row is not a test case, so the
        reader drops it rather than handing the aggregates something to count.
        That is why the fallback group holds only *unrecognised* scopes.
        """
        return scope is None or not str(scope).strip()

    def classify(self, scope) -> str:
        """Map a raw Scope cell onto a scope-group key.

        Total by construction, blanks included, so no caller can produce a case
        that belongs to no table. In practice the blank never arrives: a row
        with no scope never becomes a `TestCase` -- see `is_unscoped`.
        """
        if self.is_unscoped(scope):
            return self._fallback_key
        return self._lookup.get(str(scope).strip().casefold(), self._fallback_key)

    def is_counted(self, scope) -> bool:
        """True when a raw Scope cell belongs to a group that is in the plan.

        Takes the cell rather than the group key, so callers filtering cases
        classify in one step and cannot classify one way here and another way
        in the tables.
        """
        return self.classify(scope) in set(self.counted)

    def to_dict(self) -> dict:
        return {"groups": [g.to_dict() for g in self.groups]}


def _load_default() -> ScopeSet:
    from tcm.settings import SCOPE_GROUPS_CONFIG

    path = SCOPE_GROUPS_CONFIG
    try:
        return ScopeSet.load(path)
    except Exception as e:
        if path == DEFAULT_CONFIG_PATH:
            raise
        log.error("Failed to load scope groups config '%s': %s — using defaults", path, e)
        return ScopeSet.load(DEFAULT_CONFIG_PATH)


SCOPES = _load_default()
