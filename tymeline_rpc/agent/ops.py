"""Turn a ``freecad_ops_v1`` plan into addon calls. No network and no FreeCAD."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tymeline_rpc.agent.core.errors import AgentError

# Geometric properties the agent may set. Anything else is refused.
_PROPERTY_ALLOW = frozenset(
    {
        "Length",
        "Width",
        "Height",
        "Radius",
        "Radius1",
        "Radius2",
        "Angle",
        "Label",
        "FirstAngle",
        "SecondAngle",
    }
)
_REF_KEYS = frozenset({"Base", "Tool", "Profile"})


@dataclass(frozen=True)
class Step:
    kind: str
    op: str
    op_index: int
    name: str
    data: dict[str, Any] = field(default_factory=dict)


def compile_plan(payload: dict[str, Any], document: str) -> list[Step]:
    """Validate the plan and return steps. Raises before any document edit."""
    if not isinstance(payload, dict):
        raise AgentError.bad_request("apply_plan payload must be a JSON object.")
    schema = payload.get("schema")
    if schema != "freecad_ops_v1":
        raise AgentError.bad_request("schema must be freecad_ops_v1.")
    ops = payload.get("ops")
    if ops is None:
        ops = []
    if not isinstance(ops, list):
        raise AgentError.bad_request("ops must be a list.")

    steps: list[Step] = []
    current = document
    for index, raw in enumerate(ops):
        if not isinstance(raw, dict):
            raise AgentError.bad_request(f"ops[{index}] must be a JSON object.")
        op_name = raw.get("op")
        if not isinstance(op_name, str) or not op_name:
            raise AgentError.bad_request(f"ops[{index}] is missing op.")
        if op_name == "new_document":
            name = _text(raw, "name", op_name)
            steps.append(Step("create_document", op_name, index, name))
            current = name
            continue
        if not current:
            raise AgentError.no_document(
                "No active document. Send doc_name, or start the plan with new_document."
            )
        steps.append(_compile_op(raw, op_name, index))
    return steps


def resolve_refs(data: dict[str, Any], aliases: dict[str, str]) -> dict[str, Any]:
    """Replace object ids created earlier in this plan with FreeCAD's real Name."""
    resolved: dict[str, Any] = {}
    for key, value in data.items():
        if key in _REF_KEYS and isinstance(value, str):
            resolved[key] = aliases.get(value, value)
        else:
            resolved[key] = value
    return resolved


def _compile_op(raw: dict[str, Any], op_name: str, index: int) -> Step:
    if op_name == "add_box":
        return _primitive(
            raw, index, op_name, "Part::Box",
            (("length", "Length"), ("width", "Width"), ("height", "Height")),
        )
    if op_name == "add_cylinder":
        return _primitive(
            raw, index, op_name, "Part::Cylinder",
            (("radius", "Radius"), ("height", "Height")),
        )
    if op_name == "add_sphere":
        return _primitive(raw, index, op_name, "Part::Sphere", (("radius", "Radius"),))
    if op_name == "add_cone":
        return _primitive(
            raw, index, op_name, "Part::Cone",
            (("radius1", "Radius1"), ("radius2", "Radius2"), ("height", "Height")),
        )
    if op_name == "add_sketch":
        return Step("create_object", op_name, index, _text(raw, "name", op_name), {"type": "Sketcher::SketchObject"})
    if op_name == "add_rectangle":
        return _rectangle(raw, index)
    if op_name == "add_circle":
        return _primitive(raw, index, op_name, "Draft::Circle", (("radius", "Radius"),))
    if op_name == "add_wire":
        return _wire(raw, index)
    if op_name == "extrude":
        return _extrude(raw, index)
    if op_name in {"cut", "fuse", "common"}:
        return _boolean(raw, index, op_name)
    if op_name == "set_placement":
        return _placement(raw, index)
    if op_name == "set_property":
        return _set_property(raw, index)
    if op_name == "remove_object":
        return Step("delete_object", op_name, index, _text(raw, "id", op_name))
    raise AgentError.bad_request(f"Unknown op '{op_name}'.")


def _primitive(
    raw: dict[str, Any],
    index: int,
    op_name: str,
    type_id: str,
    fields: tuple[tuple[str, str], ...],
) -> Step:
    props = {dest: _number(raw, source, op_name) for source, dest in fields}
    return Step(
        "create_object",
        op_name,
        index,
        _text(raw, "name", op_name),
        {"type": type_id, "properties": props},
    )


def _rectangle(raw: dict[str, Any], index: int) -> Step:
    length = _number(raw, "length", "add_rectangle")
    if "width" in raw:
        second = _number(raw, "width", "add_rectangle")
    elif "height" in raw:
        second = _number(raw, "height", "add_rectangle")
    else:
        raise AgentError.bad_request("add_rectangle requires length and width.")
    # Draft.make_rectangle takes (length, height). The plan's width is that second side.
    return Step(
        "create_object",
        "add_rectangle",
        index,
        _text(raw, "name", "add_rectangle"),
        {"type": "Draft::Rectangle", "properties": {"Length": length, "Height": second}},
    )


def _wire(raw: dict[str, Any], index: int) -> Step:
    points = raw.get("points")
    if not isinstance(points, list) or not points:
        raise AgentError.bad_request("add_wire requires a non-empty points list.")
    props: dict[str, Any] = {"Points": points}
    if "closed" in raw:
        if not isinstance(raw["closed"], bool):
            raise AgentError.bad_request("add_wire closed must be true or false.")
        props["Closed"] = raw["closed"]
    return Step(
        "create_object",
        "add_wire",
        index,
        _text(raw, "name", "add_wire"),
        {"type": "Draft::Wire", "properties": props},
    )


def _extrude(raw: dict[str, Any], index: int) -> Step:
    props: dict[str, Any] = {
        "Base": _text(raw, "base", "extrude"),
        "Length": _number(raw, "length", "extrude"),
    }
    if "reversed" in raw:
        if not isinstance(raw["reversed"], bool):
            raise AgentError.bad_request("extrude reversed must be true or false.")
        props["Reversed"] = raw["reversed"]
    return Step(
        "create_object",
        "extrude",
        index,
        _text(raw, "name", "extrude"),
        {"type": "Part::Extrusion", "properties": props},
    )


def _boolean(raw: dict[str, Any], index: int, op_name: str) -> Step:
    type_id = {"cut": "Part::Cut", "fuse": "Part::Fuse", "common": "Part::Common"}[op_name]
    props = {
        "Base": _text(raw, "base", op_name),
        "Tool": _text(raw, "tool", op_name),
    }
    return Step(
        "create_object",
        op_name,
        index,
        _text(raw, "name", op_name),
        {"type": type_id, "properties": props},
    )


def _placement(raw: dict[str, Any], index: int) -> Step:
    rotation = _number(raw, "rotation_deg", "set_placement") if "rotation_deg" in raw else 0
    props = {
        "Placement": {
            "Position": {
                "x": _coord(raw, "x"),
                "y": _coord(raw, "y"),
                "z": _coord(raw, "z"),
            },
            "Rotation": {
                "Axis": {"x": 0, "y": 0, "z": 1},
                "Angle": rotation,
            },
        }
    }
    return Step("edit_object", "set_placement", index, _text(raw, "id", "set_placement"), {"properties": props})


def _set_property(raw: dict[str, Any], index: int) -> Step:
    name = _text(raw, "id", "set_property")
    incoming = raw.get("properties")
    if isinstance(incoming, dict):
        props = _allowed_properties(incoming)
    else:
        prop = _text(raw, "property", "set_property")
        if "value" not in raw:
            raise AgentError.bad_request("set_property requires value.")
        props = _allowed_properties({prop: raw["value"]})
    return Step("edit_object", "set_property", index, name, {"properties": props})


def _allowed_properties(props: dict[str, Any]) -> dict[str, Any]:
    if not props:
        raise AgentError.bad_request("set_property requires at least one property.")
    cleaned: dict[str, Any] = {}
    for key, value in props.items():
        if not isinstance(key, str) or key not in _PROPERTY_ALLOW:
            raise AgentError.not_supported(f"set_property cannot set '{key}'.")
        if isinstance(value, bool) or isinstance(value, (int, float, str)):
            cleaned[key] = value
            continue
        raise AgentError.bad_request(
            f"set_property value for '{key}' must be a number, string, or boolean."
        )
    return cleaned


def _text(raw: dict[str, Any], key: str, op_name: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AgentError.bad_request(f"{op_name} requires {key}.")
    return value


def _number(raw: dict[str, Any], key: str, op_name: str) -> int | float:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AgentError.bad_request(f"{op_name} requires a number for {key}.")
    return value


def _coord(raw: dict[str, Any], key: str) -> int | float:
    if key not in raw:
        return 0
    return _number(raw, key, "set_placement")
