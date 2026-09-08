"""Scope -> scope-group classification, driven by a JSON config.

The Summary view reports FPT work and JP work as separate tables, because they
are separate commitments and adding them together answers no question anyone
asks. Which Scope strings belong to which table is data, not code — the same
reasoning as `parser/status.py`: a team that renames a scope, or wants a third
table, edits `parser/scope_groups.json` and nothing else.

Every scope reaches exactly one group. Anything the config does not name — a
typo, a scope nobody has configured yet, or the blank Scope of a spreadsheet
section heading — lands in the fallback group, so the three tables always add
up to everything that was loaded.
"""
import json
import logging
import os
from dataclasses import dataclass

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "scope_groups.json")


@dataclass(frozen=True)
class ScopeGroup:
    key: str
    label: str

    def to_dict(self) -> dict:
        return {"key": self.key, "label": self.label}


class ScopeSet:
    """An ordered set of scope groups plus the Scope strings that map onto them."""

    def __init__(self, groups: list[ScopeGroup], lookup: dict[str, str], fallback_key: str):
        self.groups = groups
        self.keys = [g.key for g in groups]
        self._lookup = lookup
        self._fallback_key = fallback_key

    @classmethod
    def load(cls, path: str = DEFAULT_CONFIG_PATH) -> "ScopeSet":
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return cls.from_dict(raw, source=path)

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

            groups.append(ScopeGroup(key=key, label=str(entry.get("label") or key)))

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

        groups.append(ScopeGroup(key=fb_key, label=str(fallback.get("label") or fb_key)))
        return cls(groups, lookup, fb_key)

    def classify(self, scope) -> str:
        """Map a raw Scope cell onto a scope-group key."""
        if scope is None:
            return self._fallback_key
        text = str(scope).strip()
        if not text:
            return self._fallback_key
        return self._lookup.get(text.casefold(), self._fallback_key)

    def to_dict(self) -> dict:
        return {"groups": [g.to_dict() for g in self.groups]}


def _load_default() -> ScopeSet:
    from config import SCOPE_GROUPS_CONFIG

    path = SCOPE_GROUPS_CONFIG
    try:
        return ScopeSet.load(path)
    except Exception as e:
        if path == DEFAULT_CONFIG_PATH:
            raise
        log.error("Failed to load scope groups config '%s': %s — using defaults", path, e)
        return ScopeSet.load(DEFAULT_CONFIG_PATH)


SCOPES = _load_default()
