"""AgentError. `code` is the wire `payload.error` string."""

from __future__ import annotations

from typing import Any

HTTP_STATUS: dict[str, int] = {
    "bad_request": 400,
    "not_supported": 400,
    "no_document": 409,
    "stale_plan": 409,
    "freecad_busy": 503,
    "freecad_disconnected": 503,
    "internal_error": 500,
}


class AgentError(Exception):
    """Typed plugin error. `code` is the wire `payload.error` string."""

    def __init__(self, code: str, message: str, http_status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = HTTP_STATUS[code] if http_status is None else http_status

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.code, "message": self.message}

    @classmethod
    def bad_request(cls, message: str) -> AgentError:
        return cls("bad_request", message)

    @classmethod
    def not_supported(cls, message: str) -> AgentError:
        return cls("not_supported", message)

    @classmethod
    def no_document(cls, message: str = "No active document.") -> AgentError:
        return cls("no_document", message)

    @classmethod
    def stale_plan(cls, message: str) -> AgentError:
        return cls("stale_plan", message)

    @classmethod
    def freecad_busy(cls, message: str) -> AgentError:
        return cls("freecad_busy", message)

    @classmethod
    def freecad_disconnected(
        cls, message: str = "FreeCAD is not running, or the listener on port 9875 is down."
    ) -> AgentError:
        return cls("freecad_disconnected", message)

    @classmethod
    def internal_error(cls, message: str) -> AgentError:
        return cls("internal_error", message)
