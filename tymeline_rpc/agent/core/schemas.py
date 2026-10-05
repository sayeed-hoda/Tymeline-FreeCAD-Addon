"""Envelope `{id, type, event, payload}`. None is omitted on write; False is kept."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tymeline_rpc.agent.core.json import dumps, fold_properties, loads, omit_none

_ENVELOPE = ("id", "type", "event", "payload")


def _opt_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _as_str(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


class _Wire:
    def to_json(self) -> str:
        return dumps(self)

    @classmethod
    def from_json(cls, text: str) -> Any:
        return cls.from_dict(loads(text))  # type: ignore[attr-defined]


@dataclass
class Envelope(_Wire):
    id: str | None = None
    type: str = ""
    event: str | None = None
    payload: Any = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Envelope:
        raw = fold_properties(data, _ENVELOPE)
        return cls(
            id=_opt_str(raw.get("id")),
            type=_as_str(raw.get("type", "")),
            event=_opt_str(raw.get("event")),
            payload=raw.get("payload"),
        )

    def to_dict(self) -> dict[str, Any]:
        return omit_none(
            {
                "id": self.id,
                "type": self.type,
                "event": self.event,
                "payload": self.payload,
            }
        )
