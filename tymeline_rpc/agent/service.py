"""The five gateway commands. Each one calls the FreeCAD addon over XML-RPC."""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from tymeline_rpc.agent.core.errors import AgentError
from tymeline_rpc.agent.core.json import omit_none
from tymeline_rpc.agent.ops import Step, compile_plan, resolve_refs
from tymeline_rpc.agent.version import PLUGIN_VERSION

_LOG = logging.getLogger("tymeline.agent.command")
_VIEWS = frozenset(
    {
        "Isometric",
        "Front",
        "Top",
        "Right",
        "Back",
        "Left",
        "Bottom",
        "Dimetric",
        "Trimetric",
    }
)
_PARTIAL = (
    " Objects already created in this plan: {names}. "
    "This build applies each op on its own, so those objects stay in the document."
)


class CommandService:
    """One place the WebSocket (and, later, the loopback HTTP server) calls."""

    def __init__(self, connection: Any = None) -> None:
        self._connection = connection

    def get_status(self) -> dict[str, Any]:
        rpc = self._rpc_status()
        if rpc is None:
            payload = self._status_payload(connected=False)
            self._log("get_status", None, [], "freecad_disconnected")
            return payload
        session = self._session()
        payload = self._status_payload(
            connected=True,
            freecad_version=_opt_str(session.get("freecad_version")),
            document=_opt_str(session.get("document")),
            path=_opt_str(session.get("path")),
        )
        self._log("get_status", payload.get("document"), [], "ok")
        return payload

    def extract(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = payload if isinstance(payload, dict) else {}
        self._require_listener()
        document = self._document_name(body)
        if not document:
            raise AgentError.no_document()
        object_name = _opt_str(body.get("id")) or _opt_str(body.get("object")) or _opt_str(body.get("name"))
        if object_name:
            found = self._fc().get_object(document, object_name)
            if not isinstance(found, dict) or not found.get("Name"):
                self._log("extract", document, [object_name], "stale_plan")
                raise AgentError.stale_plan(f"Object '{object_name}' was not found in '{document}'.")
            self._log("extract", document, [object_name], "ok")
            return omit_none(
                {"schema": "freecad_extract_v1", "document": document, "object": found}
            )
        objects = self._fc().get_objects(document)
        if not isinstance(objects, list):
            objects = []
        names = [item.get("Name") for item in objects if isinstance(item, dict) and isinstance(item.get("Name"), str)]
        self._log("extract", document, names, "ok")
        return {"schema": "freecad_extract_v1", "document": document, "objects": objects}

    def apply_plan(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = payload if isinstance(payload, dict) else {}
        self._require_listener()
        document = self._document_name(body)
        try:
            steps = compile_plan(body, document)
        except AgentError as exc:
            self._log("apply_plan", document or None, [], exc.code)
            raise
        names = [step.name for step in steps]
        plan_id = _opt_str(body.get("plan_id"))
        current = document
        aliases: dict[str, str] = {}
        created: list[str] = []
        results: list[dict[str, Any]] = []
        for step in steps:
            if step.kind == "create_document":
                outcome = self._apply_create_document(step)
            else:
                if not current:
                    raise AgentError.no_document()
                outcome = self._apply_step(step, current, aliases)
            results.append(outcome["result"])
            if outcome.get("document"):
                current = outcome["document"]
            if outcome.get("created"):
                created.append(outcome["created"])
                aliases[step.name] = outcome["created"]
            if not outcome["ok"]:
                code = _error_code(outcome["error"])
                message = outcome["error"]
                if created:
                    message += _PARTIAL.format(names=", ".join(created))
                self._log("apply_plan", current, names, code)
                # Nothing was left behind: the gateway gets a command error.
                # Something was created: answer with success false so the agent
                # still receives the names FreeCAD assigned.
                if not created:
                    raise AgentError(code, message)
                return omit_none(
                    {
                        "schema": "freecad_apply_v1",
                        "plan_id": plan_id,
                        "success": False,
                        "error": code,
                        "message": message,
                        "created_names": created,
                        "results": results,
                    }
                )
        self._log("apply_plan", current, created or names, "ok")
        return omit_none(
            {
                "schema": "freecad_apply_v1",
                "plan_id": plan_id,
                "success": True,
                "created_names": created,
                "results": results,
            }
        )

    def run_checks(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = payload if isinstance(payload, dict) else {}
        self._require_listener()
        document = self._document_name(body)
        try:
            report = self._fc().run_checks(document)
        except Exception as exc:
            if _missing_method(exc):
                raise AgentError.not_supported(
                    "This FreeCAD addon has no run_checks method. Update the addon."
                ) from exc
            raise AgentError.freecad_disconnected(str(exc)) from exc
        if not isinstance(report, dict):
            raise AgentError.internal_error("run_checks returned an unexpected result.")
        if report.get("success") is False:
            code = report.get("error") if isinstance(report.get("error"), str) else "internal_error"
            message = report.get("message") if isinstance(report.get("message"), str) else "run_checks failed."
            self._log("run_checks", document or None, [], code)
            if code == "no_document":
                raise AgentError.no_document(message)
            raise AgentError(code if code in {"no_document", "internal_error"} else "internal_error", message)
        errors = report.get("errors") if isinstance(report.get("errors"), list) else []
        names = [item.get("name") for item in errors if isinstance(item, dict)]
        ok = bool(report.get("ok"))
        self._log("run_checks", _opt_str(report.get("document")) or document, [n for n in names if isinstance(n, str)], "ok" if ok else "invalid")
        return {
            "schema": "freecad_checks_v1",
            "ok": ok,
            "document": report.get("document") or document,
            "errors": errors,
        }

    def export(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = payload if isinstance(payload, dict) else {}
        self._require_listener()
        kind = _opt_str(body.get("kind")) or "screenshot"
        if kind.lower() in {"step", "stp", "stl"}:
            self._log("export", None, [], "not_supported")
            raise AgentError.not_supported(
                "STEP and STL export are not in this build yet. Screenshot export is available."
            )
        if kind.lower() not in {"screenshot", "png", "image"}:
            self._log("export", None, [], "not_supported")
            raise AgentError.not_supported(f"Unknown export kind '{kind}'.")
        view = _opt_str(body.get("view_name")) or "Isometric"
        if view not in _VIEWS:
            self._log("export", None, [], "bad_request")
            raise AgentError.bad_request(
                f"view_name must be one of: {', '.join(sorted(_VIEWS))}."
            )
        width = body.get("width") if isinstance(body.get("width"), int) and not isinstance(body.get("width"), bool) else None
        height = body.get("height") if isinstance(body.get("height"), int) and not isinstance(body.get("height"), bool) else None
        focus = _opt_str(body.get("focus_object"))
        encoded = self._fc().get_active_screenshot(view, width, height, focus)
        if not isinstance(encoded, str) or not encoded:
            self._log("export", self._document_name(body) or None, [], "internal_error")
            raise AgentError.internal_error("FreeCAD did not return a screenshot.")
        include_base64 = body.get("include_base64")
        if include_base64 is None:
            include_base64 = True
        if not isinstance(include_base64, bool):
            raise AgentError.bad_request("include_base64 must be true or false.")
        out_path = _opt_str(body.get("out_path"))
        written: str | None = None
        if out_path:
            written = str(_write_png(out_path, encoded))
        elif not include_base64:
            raise AgentError.bad_request("export needs out_path or include_base64.")
        document = self._document_name(body)
        self._log("export", document or None, [focus] if focus else [], "ok")
        return omit_none(
            {
                "kind": "screenshot",
                "path": written,
                "base64": encoded if include_base64 else None,
            }
        )

    def _apply_create_document(self, step: Step) -> dict[str, Any]:
        res = self._fc().create_document(step.name)
        ok, error, actual = _outcome(res)
        name = actual or step.name
        return {
            "ok": ok,
            "error": error or "",
            "document": name if ok else None,
            "created": None,
            "result": _result(step, "ok" if ok else "error", error, created=name if ok else None),
        }

    def _apply_step(self, step: Step, document: str, aliases: dict[str, str]) -> dict[str, Any]:
        fc = self._fc()
        target = aliases.get(step.name, step.name)
        if step.kind == "create_object":
            properties = resolve_refs(step.data.get("properties") or {}, aliases)
            res = fc.create_object(
                document,
                {"Name": step.name, "Type": step.data["type"], "Properties": properties},
            )
            ok, error, actual = _outcome(res)
            created = actual or (step.name if ok else None)
            return {
                "ok": ok,
                "error": error or "",
                "document": None,
                "created": created if ok or actual else None,
                "result": _result(step, "ok" if ok else "error", error, created=created if ok else actual),
            }
        if step.kind == "edit_object":
            properties = resolve_refs(step.data.get("properties") or {}, aliases)
            res = fc.edit_object(document, target, {"Properties": properties})
            ok, error, _actual = _outcome(res)
            return {
                "ok": ok,
                "error": error or "",
                "document": None,
                "created": None,
                "result": _result(step, "ok" if ok else "error", error, created=None),
            }
        if step.kind == "delete_object":
            res = fc.delete_object(document, target)
            ok, error, _actual = _outcome(res)
            return {
                "ok": ok,
                "error": error or "",
                "document": None,
                "created": None,
                "result": _result(step, "ok" if ok else "error", error, created=None),
            }
        raise AgentError.internal_error(f"Unknown plan step '{step.kind}'.")

    def _require_listener(self) -> None:
        if self._rpc_status() is None:
            raise AgentError.freecad_disconnected()

    def _rpc_status(self) -> dict[str, Any] | None:
        try:
            status = self._fc().get_rpc_status()
        except Exception:
            return None
        return status if isinstance(status, dict) else None

    def _session(self) -> dict[str, Any]:
        fc = self._fc()
        method = getattr(fc, "get_session_info", None)
        if not callable(method):
            return self._session_from_documents()
        try:
            info = method()
        except Exception as exc:
            if _missing_method(exc):
                return self._session_from_documents()
            return {}
        return info if isinstance(info, dict) else {}

    def _session_from_documents(self) -> dict[str, Any]:
        try:
            documents = self._fc().list_documents()
        except Exception:
            return {}
        if not isinstance(documents, list):
            return {}
        names = [item for item in documents if isinstance(item, str)]
        document = names[0] if len(names) == 1 else None
        return {"documents": names, "document": document}

    def _document_name(self, payload: dict[str, Any]) -> str:
        for key in ("doc_name", "document"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
        session = self._session()
        document = session.get("document")
        if isinstance(document, str) and document:
            return document
        documents = session.get("documents")
        if isinstance(documents, list) and len(documents) == 1 and isinstance(documents[0], str):
            return documents[0]
        return ""

    def _fc(self) -> Any:
        if self._connection is None:
            raise AgentError.freecad_disconnected(
                "No FreeCAD connection was given to CommandService."
            )
        return self._connection

    def _status_payload(
        self,
        *,
        connected: bool,
        freecad_version: str | None = None,
        document: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        return omit_none(
            {
                "schema": "freecad_status_v1",
                "cad_kind": "freecad",
                "freecad_version": freecad_version,
                "plugin_version": PLUGIN_VERSION,
                "document": document,
                "path": path,
                "connected": connected,
                "supported_schemas": ["freecad_ops_v1"],
            }
        )

    def _log(self, kind: str, document: str | None, names: list[str], code: str) -> None:
        _LOG.info(
            "command type=%s document=%s objects=%s result=%s",
            kind,
            document or "",
            ",".join(names),
            code,
        )


def _opt_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _missing_method(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "is not supported" in text or "method not found" in text


def _outcome(res: Any) -> tuple[bool, str | None, str | None]:
    if not isinstance(res, dict):
        return False, "FreeCAD returned an unexpected result.", None
    actual = res.get("object_name") if isinstance(res.get("object_name"), str) else None
    if actual is None and isinstance(res.get("document_name"), str):
        actual = res["document_name"]
    if res.get("success") is True:
        return True, None, actual
    error = res.get("error") or res.get("message") or "FreeCAD rejected the change."
    return False, str(error), actual


def _error_code(message: str) -> str:
    lower = message.lower()
    if "object" in lower and "not found" in lower:
        return "stale_plan"
    if "not found" in lower and "document" in lower:
        return "no_document"
    if "not found" in lower:
        return "stale_plan"
    return "internal_error"


def _result(step: Step, status: str, error: str | None, created: str | None) -> dict[str, Any]:
    return omit_none(
        {
            "op_index": step.op_index,
            "op": step.op,
            "status": status,
            "error": error,
            "created_name": created,
        }
    )


def _write_png(out_path: str, encoded: str) -> Path:
    path = Path(out_path).expanduser()
    if not path.is_absolute():
        raise AgentError.bad_request("out_path must be an absolute path.")
    try:
        data = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise AgentError.internal_error("Screenshot data was not valid base64.") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path
