"""Start, stop, and pair the in-process Tymeline WebSocket."""

from __future__ import annotations

import logging
import logging.handlers
import os
import signal

from tymeline_rpc.agent.service import CommandService
from tymeline_rpc.agent.transport.pairing import (
    INSECURE_GATEWAY_USER_MESSAGE,
    UNTRUSTED_GATEWAY_USER_MESSAGE,
    PairingToken,
    clear_pairing,
    is_insecure_gateway,
    is_trusted_gateway,
    normalize_gateway_url,
    parse_pairing_token,
    resolve_connect_config,
    save_pairing,
)
from tymeline_rpc.agent.transport.paths import (
    legacy_config_dir,
    log_path,
    migrate_legacy_files,
)
from tymeline_rpc.agent.transport.ws_client import WsClient

_client: WsClient | None = None
_last_status = ""
_log_handler: logging.Handler | None = None
_quit_connected = False


def start_cloud_link() -> str:
    """Open the gateway socket. Call on the GUI thread."""
    global _client
    _connect_about_to_quit()
    if _client is not None:
        snap = _client.snapshot()
        if snap.get("connected"):
            return "Tymeline is already connected."
        if snap.get("connecting"):
            return "Tymeline is already connecting."
        _client.stop(wait=False)
        _client = None

    moved = migrate_legacy_files()
    prefix = ""
    if moved:
        prefix = "Moved your existing Tymeline pairing into FreeCAD's settings folder. "
    _stop_legacy_daemon()
    try:
        cfg = resolve_connect_config()
    except ValueError as exc:
        return f"{prefix}Tymeline pairing is invalid: {exc}. Choose Pair with Tymeline."
    if cfg is None:
        return (
            prefix
            + "Not paired yet. Choose Pair with Tymeline in the Tymeline menu and paste your TYM1 key."
        )
    if not is_trusted_gateway(cfg.url):
        return prefix + UNTRUSTED_GATEWAY_USER_MESSAGE
    _ensure_log_handler()
    import tymeline_rpc.rpc_server as rpc_server

    rpc_server.acquire_dispatch("cloud")
    service = CommandService(connection=rpc_server.FreeCADRPC())
    _client = WsClient(
        cfg.url,
        cfg.secret,
        token_id=cfg.token_id,
        service=service,
        status=_on_status,
        in_process=True,
    )
    _client.start()
    return prefix + f"Connecting to Tymeline ({cfg.url})…"


def stop_cloud_link() -> str:
    """Close the gateway socket. Call on the GUI thread."""
    global _client
    if _client is None:
        return "Tymeline was not connected."
    client = _client
    _client = None
    client.stop(wait=False)
    import tymeline_rpc.rpc_server as rpc_server

    rpc_server.release_dispatch("cloud")
    return "Tymeline disconnected."


def cloud_status() -> dict:
    if _client is None:
        return {"enabled": False, "connected": False, "last_message": _last_status}
    snap = dict(_client.snapshot())
    snap["last_message"] = _last_status
    return snap


def pair(token: str) -> str:
    """Store a TYM1 token and connect. Call on the GUI thread."""
    parsed = parse_pairing_token(token)
    dest = normalize_gateway_url(parsed.url)
    if not is_trusted_gateway(dest):
        raise ValueError(UNTRUSTED_GATEWAY_USER_MESSAGE)
    warning = ""
    if is_insecure_gateway(dest):
        warning = INSECURE_GATEWAY_USER_MESSAGE + " "
    stored = PairingToken(
        url=dest,
        token_id=parsed.token_id,
        secret=parsed.secret,
        display=parsed.display,
    )
    save_pairing(stored)
    if _client is not None:
        stop_cloud_link()
    return "Paired " + stored.to_safe_string() + ". " + warning + start_cloud_link()


def unpair() -> str:
    stop_cloud_link()
    if clear_pairing():
        return "Tymeline pairing removed."
    return "Tymeline was not paired."


def _on_status(message: str) -> None:
    global _last_status
    _last_status = message
    try:
        import FreeCAD

        FreeCAD.Console.PrintMessage(message + "\n")
    except Exception:
        pass
    logging.getLogger("tymeline.agent.ws").info(message)


def _ensure_log_handler() -> None:
    global _log_handler
    if _log_handler is not None:
        return
    handler = logging.handlers.RotatingFileHandler(
        log_path(),
        maxBytes=1_000_000,
        backupCount=2,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger = logging.getLogger("tymeline.agent")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
    _log_handler = handler


def _stop_legacy_daemon() -> None:
    if os.name == "nt":
        return
    path = legacy_config_dir() / "agent.pid"
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
        os.kill(pid, signal.SIGTERM)
    except (OSError, ValueError):
        return
    try:
        import FreeCAD

        FreeCAD.Console.PrintMessage(
            f"[Tymeline] Stopped the old freecad-agent daemon (pid {pid}). "
            "It is no longer needed.\n"
        )
    except Exception:
        pass


def _on_about_to_quit() -> None:
    try:
        stop_cloud_link()
    except Exception:
        pass


def _connect_about_to_quit() -> None:
    global _quit_connected
    if _quit_connected:
        return
    try:
        from PySide import QtWidgets
    except Exception:
        return
    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    app.aboutToQuit.connect(_on_about_to_quit)
    _quit_connected = True


_connect_about_to_quit()
