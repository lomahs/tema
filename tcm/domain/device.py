"""Device -> device-family classification, driven by a JSON config.

One test plan usually covers a phone at two screen sizes — "iPhone Min size"
and "iPhone Max size" are two device blocks in the workbook and two rows in
Summary, but one commitment to anyone reading the totals. This is what lets
Summary's third Rows mode add them together.

Which names belong to which family is data, not code — the same reasoning as
`parser/scope.py` and `parser/status.py`: a team that tests a new handset edits
`parser/device_groups.json` and nothing else.

Two things differ from `ScopeSet`, and both follow from what a device name is.

**Matching is by substring, not by the whole cell.** A scope cell holds one of
a handful of agreed words; a device name is written freehand and carries the
model, the size and sometimes the OS version. Nobody is going to list every
spelling of "iPhone" that a workbook might contain, so a family names a token
and claims every device whose name contains it, case-insensitively. Order
therefore decides: the first family whose token appears wins, which is what
makes "iPad mini" before "iPad" a meaningful thing to configure.

**There is no fallback family.** A device that no family claims is its own
family, keyed and labelled by its own name, so the merged table names every
device it did not merge and still adds up to exactly what the split table does.
A catch-all would put an Android and a Windows box on one row together and call
the result a device.
"""
import json
import logging
import os
from dataclasses import dataclass

from tcm.settings import CONFIG_DIR

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join(CONFIG_DIR, "device_groups.json")


@dataclass(frozen=True)
class DeviceFamily:
    key: str
    label: str

    def to_dict(self) -> dict:
        return {"key": self.key, "label": self.label}


class DeviceSet:
    """An ordered list of device families and the tokens that claim a device."""

    def __init__(self, families: list[DeviceFamily], rules: list[tuple[str, str]]):
        self.families = families
        self.keys = [f.key for f in families]
        #: (token, family key), in config order — the order `classify` tries.
        self._rules = rules

    @classmethod
    def load(cls, path: str = DEFAULT_CONFIG_PATH) -> "DeviceSet":
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return cls.from_dict(raw, source=path)

    def adopt(self, other: "DeviceSet") -> None:
        """Become `other`, in place — see `StatusSet.adopt` for why."""
        self.__dict__.update(other.__dict__)

    @classmethod
    def from_dict(cls, raw: dict, source: str = "<dict>") -> "DeviceSet":
        entries = raw.get("families")
        if entries is None:
            entries = []
        if not isinstance(entries, list):
            raise ValueError(f"{source}: 'families' must be a list")

        families: list[DeviceFamily] = []
        rules: list[tuple[str, str]] = []

        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ValueError(f"{source}: families[{i}] must be an object")
            key = entry.get("key")
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"{source}: families[{i}] needs a non-empty 'key'")
            key = key.strip()
            if any(f.key == key for f in families):
                raise ValueError(f"{source}: duplicate device family key '{key}'")

            families.append(DeviceFamily(key=key, label=str(entry.get("label") or key)))

            values = entry.get("match")
            if not isinstance(values, list) or not values:
                raise ValueError(f"{source}: device family '{key}' needs a non-empty 'match' list")
            for value in values:
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{source}: device family '{key}' has an empty 'match' value")
                token = value.strip().casefold()
                # A token *containing* an earlier one can never win: everything
                # that matches it matched the earlier rule first, so the family
                # would silently claim nothing. Refused rather than shipped.
                #
                # The reverse is not a clash but the point of ordering: "iPad
                # mini" ahead of "iPad" still leaves "iPad Pro" for "iPad".
                clash = next(((t, k) for t, k in rules if t in token), None)
                if clash is not None:
                    owner = clash[1]
                    raise ValueError(
                        f"{source}: device family '{key}' matches '{value}', which is "
                        f"already matched by '{owner}' — one of the two can never apply"
                    )
                rules.append((token, key))

        return cls(families, rules)

    def classify(self, device) -> str:
        """Map a raw device name onto a family key.

        Total by construction: a device no family claims is its own family, so
        every row reaches exactly one and nothing is merged out of sight.
        """
        name = "" if device is None else str(device).strip()
        folded = name.casefold()
        for token, key in self._rules:
            if token in folded:
                return key
        return name

    def label_of(self, key: str) -> str:
        """What to print for a family key — its own name if nothing configured it."""
        return next((f.label for f in self.families if f.key == key), key)

    def to_dict(self) -> dict:
        return {"families": [f.to_dict() for f in self.families]}


def _load_default() -> DeviceSet:
    from tcm.settings import DEVICE_GROUPS_CONFIG

    path = DEVICE_GROUPS_CONFIG
    try:
        return DeviceSet.load(path)
    except Exception as e:
        if path == DEFAULT_CONFIG_PATH:
            raise
        log.error("Failed to load device groups config '%s': %s — using defaults", path, e)
        return DeviceSet.load(DEFAULT_CONFIG_PATH)


DEVICES = _load_default()
