"""Wire JSON: snake_case property names, omit nulls, reject bare null / malformed."""

from __future__ import annotations

import json as _json
from typing import Any

from tymeline_rpc.agent.core.errors import AgentError


def loads(text: str) -> dict[str, Any]:
    """Parse a JSON object. Bare `null` and non-objects are `bad_request`."""
    try:
        value = _json.loads(text)
    except _json.JSONDecodeError as exc:
        raise AgentError.bad_request(f"malformed JSON: {exc.msg}") from exc
    if value is None:
        raise AgentError.bad_request("JSON deserialized to null")
    if not isinstance(value, dict):
        raise AgentError.bad_request("expected a JSON object")
    return value


def dumps(obj: Any) -> str:
    """Serialize a wire model or dict. Compact, insertion-order keys, UTF-8."""
    if hasattr(obj, "to_dict"):
        obj = obj.to_dict()
    return _json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def omit_none(data: dict[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is None. Keep False, 0, and empty strings."""
    return {key: value for key, value in data.items() if value is not None}


def fold_properties(data: Any, names: tuple[str, ...]) -> dict[str, Any]:
    """Case-insensitive read of known snake_case names. Unknown keys are dropped.

    Matching is against the snake_case name. `OutPath` does not fold onto
    `out_path`. JSON null is treated as absent.
    """
    if not isinstance(data, dict):
        raise AgentError.bad_request("expected a JSON object")
    lookup = {name.lower(): name for name in names}
    out: dict[str, Any] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            continue
        dest = lookup.get(key.lower())
        if dest is None or value is None:
            continue
        out[dest] = value
    return out
