"""Qt Command classes for the Tymeline workbench menu.

Toolbar and menu: Start Tymeline Connection, Stop Tymeline Connection,
Auto-Start, Pair with Tymeline.

``register_commands()`` and ``schedule_toggle_sync()`` are invoked from
``rpc_server.py`` at import time to preserve current side-effect behavior.
"""

import FreeCAD
import FreeCADGui
from PySide import QtWidgets

from tymeline_rpc.settings import load_settings, save_settings


def _report_server_command(message: str, error: bool = False) -> None:
    """Show command feedback even when the Report View is closed."""
    printer = FreeCAD.Console.PrintError if error else FreeCAD.Console.PrintMessage
    printer(message + "\n")
    try:
        FreeCADGui.getMainWindow().statusBar().showMessage(message, 15000)
    except Exception:
        # Console feedback remains available if the main window is closing.
        pass


class StartRPCServerCommand:
    def GetResources(self):
        return {
            "MenuText": "Start Tymeline Connection",
            "ToolTip": "Connect this FreeCAD to Tymeline. Pair first if you have not.",
            "StatusTip": "Connect this FreeCAD to Tymeline. Pair first if you have not.",
        }

    def Activated(self, checked: int = 0) -> None:
        try:
            from tymeline_rpc import cloud_link, rpc_server

            msg = cloud_link.start_cloud_link()
            if load_settings().get("local_listener"):
                msg = f"{msg} {rpc_server.start_rpc_server()}"
        except Exception as exc:
            _report_server_command(
                f"Tymeline connection failed to start: {type(exc).__name__}: {exc}",
                error=True,
            )
            return
        _report_server_command(msg)

    def IsActive(self):
        return True


class StopRPCServerCommand:
    def GetResources(self):
        return {
            "MenuText": "Stop Tymeline Connection",
            "ToolTip": "Disconnect this FreeCAD from Tymeline.",
            "StatusTip": "Disconnect this FreeCAD from Tymeline.",
        }

    def Activated(self, checked: int = 0) -> None:
        try:
            from tymeline_rpc import cloud_link, rpc_server

            msg = cloud_link.stop_cloud_link()
            if rpc_server.rpc_server_instance:
                msg = f"{msg} {rpc_server.stop_rpc_server()}"
        except Exception as exc:
            _report_server_command(
                f"Tymeline connection failed to stop: {type(exc).__name__}: {exc}",
                error=True,
            )
            return
        _report_server_command(msg)

    def IsActive(self):
        return True


class ToggleRemoteConnectionsCommand:
    def GetResources(self):
        settings = load_settings()
        return {
            "MenuText": "Remote Connections",
            "ToolTip": "Enable or disable remote connections for the RPC server.",
            "Checkable": bool(settings.get("remote_enabled", False)),
        }

    def Activated(self, checked=0):
        from . import rpc_server
        settings = load_settings()
        settings["remote_enabled"] = bool(checked)
        save_settings(settings)

        if settings["remote_enabled"]:
            allowed_ips = settings.get("allowed_ips", "127.0.0.1")
            FreeCAD.Console.PrintMessage(
                f"Remote connections enabled. Allowed IPs: {allowed_ips}\n"
            )
            if not settings.get("auth_token", ""):
                FreeCAD.Console.PrintWarning(
                    "Remote connections have no auth token configured — anyone on "
                    "an allowed IP can execute code in FreeCAD. Set one via "
                    "'Add API Key' in the Tymeline menu.\n"
                )
        else:
            FreeCAD.Console.PrintMessage("Remote connections disabled.\n")

        if rpc_server.rpc_server_instance:
            FreeCAD.Console.PrintMessage(
                "Restart the RPC server for changes to take effect.\n"
            )

    def IsActive(self):
        return True


class AddApiKeyCommand:
    def GetResources(self):
        return {
            "MenuText": "Add API Key",
            "ToolTip": "Set the API key clients must present. Blank clears it.",
        }

    def Activated(self):
        from . import rpc_server
        settings = load_settings()
        current = settings.get("auth_token", "")
        text, ok = QtWidgets.QInputDialog.getText(
            None,
            "Add API Key",
            "Enter the API key clients must present (leave blank to clear it).\n"
            "The key is for the local listener only.",
            QtWidgets.QLineEdit.Normal,
            current,
        )
        if not ok:
            FreeCAD.Console.PrintMessage("API key not changed.\n")
            return
        settings["auth_token"] = text.strip()
        save_settings(settings)
        if settings["auth_token"]:
            FreeCAD.Console.PrintMessage("API key set — clients must present it.\n")
        else:
            FreeCAD.Console.PrintMessage("API key cleared.\n")
        if rpc_server.rpc_server_instance:
            FreeCAD.Console.PrintMessage(
                "Restart the Tymeline connection for the API key to take effect.\n"
            )

    def IsActive(self):
        return True


class PairTymelineCommand:
    def GetResources(self):
        return {
            "MenuText": "Pair with Tymeline",
            "ToolTip": "Paste your Tymeline API key (it starts with TYM1.). This is the key that opens the WebSocket to Tymeline.",
            "StatusTip": "Paste your Tymeline API key (it starts with TYM1.). This is the key that opens the WebSocket to Tymeline.",
        }

    def Activated(self, checked: int = 0) -> None:
        parent = None
        try:
            parent = FreeCADGui.getMainWindow()
        except Exception:
            parent = None
        text, ok = QtWidgets.QInputDialog.getText(
            parent,
            "Pair with Tymeline",
            "Paste the TYM1 pairing key:",
        )
        if not ok or not str(text).strip():
            return
        try:
            from tymeline_rpc import cloud_link

            message = cloud_link.pair(str(text).strip())
        except Exception as exc:
            _report_server_command(f"Pairing failed: {exc}", error=True)
            return
        _report_server_command(message)

    def IsActive(self):
        return True


class ToggleAutoStartCommand:
    def GetResources(self):
        settings = load_settings()
        return {
            "MenuText": "Auto-Start",
            "ToolTip": "Start the Tymeline connection automatically every time FreeCAD opens.",
            "StatusTip": "Start the Tymeline connection automatically every time FreeCAD opens.",
            "Checkable": bool(settings.get("auto_start_rpc", False)),
        }

    def Activated(self, checked=0):
        settings = load_settings()
        settings["auto_start_rpc"] = bool(checked)
        save_settings(settings)

        if settings["auto_start_rpc"]:
            FreeCAD.Console.PrintMessage(
                "Tymeline will start automatically on next FreeCAD launch.\n"
            )
        else:
            FreeCAD.Console.PrintMessage(
                "Tymeline auto-start disabled.\n"
            )

    def IsActive(self):
        return True


class TymelineStatusCommand:
    def GetResources(self):
        return {
            "MenuText": "Tymeline Status",
            "ToolTip": "Show whether this FreeCAD is connected to Tymeline.",
        }

    def Activated(self, checked: int = 0) -> None:
        from tymeline_rpc import cloud_link
        from tymeline_rpc.agent.transport.paths import log_path

        status = cloud_link.cloud_status()
        connected = "yes" if status.get("connected") else "no"
        text = (
            f"Connected: {connected}\n"
            f"Gateway: {status.get('gateway') or ''}\n"
            f"Last message: {status.get('last_message') or ''}\n"
            f"Log file: {log_path()}"
        )
        parent = None
        try:
            parent = FreeCADGui.getMainWindow()
        except Exception:
            parent = None
        QtWidgets.QMessageBox.information(parent, "Tymeline Status", text)

    def IsActive(self):
        return True


class TymelineUnpairCommand:
    def GetResources(self):
        return {
            "MenuText": "Unpair Tymeline",
            "ToolTip": "Forget the Tymeline pairing key and disconnect.",
        }

    def Activated(self, checked: int = 0) -> None:
        parent = None
        try:
            parent = FreeCADGui.getMainWindow()
        except Exception:
            parent = None
        answer = QtWidgets.QMessageBox.question(
            parent,
            "Unpair Tymeline",
            "Remove the Tymeline pairing from this FreeCAD?",
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        try:
            from tymeline_rpc import cloud_link

            message = cloud_link.unpair()
        except Exception as exc:
            _report_server_command(f"Unpair failed: {exc}", error=True)
            return
        _report_server_command(message)

    def IsActive(self):
        return True


def register_commands() -> None:
    FreeCADGui.addCommand("Tymeline_Start", StartRPCServerCommand())
    FreeCADGui.addCommand("Tymeline_Stop", StopRPCServerCommand())
    FreeCADGui.addCommand("Tymeline_Auto_Start", ToggleAutoStartCommand())
    FreeCADGui.addCommand("Tymeline_Pair", PairTymelineCommand())
    FreeCADGui.addCommand("Tymeline_Status", TymelineStatusCommand())
    FreeCADGui.addCommand("Tymeline_Unpair", TymelineUnpairCommand())


def schedule_toggle_sync() -> None:
    """Compatibility no-op; toggle state is initialized by ``GetResources``.

    FreeCAD treats the presence of the ``Checkable`` resource as making an
    action checkable and uses its boolean value as the action's initial checked
    state. Loading the saved setting in ``GetResources`` therefore avoids any
    delayed QAction lookup or workbench activation at startup.
    """
