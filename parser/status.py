"""Result -> status classification, driven by a JSON config.

The same taxonomy is used by the API (`/api/summary`, `/api/daily`), by the UI
(via `/api/statuses`) and by the sample generator, so there is one place to edit
when a team's result vocabulary differs.
"""
import json
import logging
import os
from dataclasses import dataclass

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "result_status.json")

DEFAULT_BADGE = "bg-secondary"

#: Text colour used for a status that configures a `badge` but no `text`.
BADGE_TEXT_CLASSES = {
    "bg-success": "text-success",
    "bg-danger": "text-danger",
    "bg-warning": "text-warning-emphasis",
}


def _default_text(badge: str) -> str:
    for token, text_class in BADGE_TEXT_CLASSES.items():
        if token in badge:
            return text_class
    return ""


#: The semantic colour tokens the UI understands. The taxonomy names which tone
#: a status carries; what that tone *looks* like belongs to the CSS theme, so a
#: palette change never touches this file.
TONES = ("success", "danger", "warn", "neutral", "muted")

DEFAULT_TONE = "neutral"

#: Tone inferred for a status that configures a `badge` but no `tone`, so a
#: config written before tones existed still renders sensibly.
BADGE_TONES = {
    "bg-success": "success",
    "bg-danger": "danger",
    "bg-warning": "warn",
    "bg-dark": "muted",
    "bg-secondary": "neutral",
}


def _default_tone(badge: str) -> str:
    for token, tone in BADGE_TONES.items():
        if token in badge:
            return tone
    return DEFAULT_TONE


@dataclass(frozen=True)
class Status:
    key: str
    label: str
    badge: str
    text: str
    tone: str

    def to_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "badge": self.badge,
                "text": self.text, "tone": self.tone}


class StatusSet:
    """An ordered set of statuses plus the result strings that map onto them."""

    def __init__(self, statuses: list[Status], lookup: dict[str, str],
                 empty_key: str, fallback_key: str, needs_reason: list[str],
                 executed: list[str], issue: list[str]):
        self.statuses = statuses
        self.keys = [s.key for s in statuses]
        self.needs_reason = needs_reason
        #: Statuses that count as work actually carried out, in taxonomy order.
        #: `/api/productivity` measures cases per working day against these.
        self.executed = executed
        #: Statuses a reader needs to chase up, in taxonomy order. The report's
        #: Issues sheet lists exactly these, so "which results are problems" is
        #: answered by the config rather than by a hard-coded list of keys.
        self.issue = issue
        self._lookup = lookup
        self._empty_key = empty_key
        self._fallback_key = fallback_key

    @classmethod
    def load(cls, path: str = DEFAULT_CONFIG_PATH) -> "StatusSet":
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return cls.from_dict(raw, source=path)

    @classmethod
    def from_dict(cls, raw: dict, source: str = "<dict>") -> "StatusSet":
        entries = raw.get("statuses")
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"{source}: 'statuses' must be a non-empty list")

        statuses: list[Status] = []
        lookup: dict[str, str] = {}
        empty_keys, fallback_keys, executed_keys, issue_keys = [], [], [], []

        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ValueError(f"{source}: statuses[{i}] must be an object")
            key = entry.get("key")
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"{source}: statuses[{i}] needs a non-empty 'key'")
            key = key.strip()
            if any(s.key == key for s in statuses):
                raise ValueError(f"{source}: duplicate status key '{key}'")

            badge = str(entry.get("badge") or DEFAULT_BADGE)
            # `"text": ""` is meaningful (use the default body colour), so an
            # absent key — not a falsy one — is what falls back to the badge.
            text = entry.get("text")

            tone = entry.get("tone")
            if tone is None:
                tone = _default_tone(badge)
            elif tone not in TONES:
                raise ValueError(
                    f"{source}: status '{key}' has unknown tone '{tone}'; "
                    f"expected one of {', '.join(TONES)}"
                )

            statuses.append(Status(
                key=key,
                label=str(entry.get("label") or key),
                badge=badge,
                text=str(text) if isinstance(text, str) else _default_text(badge),
                tone=tone,
            ))

            for value in entry.get("match") or []:
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{source}: status '{key}' has an empty 'match' value")
                token = value.strip().casefold()
                if token in lookup:
                    raise ValueError(
                        f"{source}: result '{value}' is matched by both "
                        f"'{lookup[token]}' and '{key}'"
                    )
                lookup[token] = key

            if entry.get("empty"):
                empty_keys.append(key)
            if entry.get("fallback"):
                fallback_keys.append(key)
            if entry.get("executed"):
                executed_keys.append(key)
            if entry.get("issue"):
                issue_keys.append(key)

        if len(empty_keys) != 1:
            raise ValueError(
                f"{source}: exactly one status must set \"empty\": true, got {empty_keys}"
            )
        if len(fallback_keys) != 1:
            raise ValueError(
                f"{source}: exactly one status must set \"fallback\": true, got {fallback_keys}"
            )

        needs_reason = raw.get("needs_reason") or []
        if not isinstance(needs_reason, list):
            raise ValueError(f"{source}: 'needs_reason' must be a list of status keys")
        known = {s.key for s in statuses}
        unknown = [k for k in needs_reason if k not in known]
        if unknown:
            raise ValueError(f"{source}: 'needs_reason' names unknown status(es) {unknown}")

        return cls(statuses, lookup, empty_keys[0], fallback_keys[0],
                   list(needs_reason), executed_keys, issue_keys)

    def classify(self, result) -> str:
        """Map a raw result cell onto a status key."""
        if result is None:
            return self._empty_key
        text = str(result).strip()
        if not text:
            return self._empty_key
        return self._lookup.get(text.casefold(), self._fallback_key)

    def zero_counts(self) -> dict[str, int]:
        """A counts dict with every status key present, so totals always reconcile."""
        return {key: 0 for key in self.keys}

    def to_dict(self) -> dict:
        return {
            "statuses": [s.to_dict() for s in self.statuses],
            "needs_reason": list(self.needs_reason),
            "executed": list(self.executed),
            "issue": list(self.issue),
        }


def _load_default() -> StatusSet:
    from config import RESULT_STATUS_CONFIG

    path = RESULT_STATUS_CONFIG
    try:
        return StatusSet.load(path)
    except Exception as e:
        if path == DEFAULT_CONFIG_PATH:
            raise
        log.error("Failed to load result status config '%s': %s — using defaults", path, e)
        return StatusSet.load(DEFAULT_CONFIG_PATH)


STATUS = _load_default()
