import sys as _sys
import os as _os
try:
    _addon_dir = _os.path.dirname(_os.path.abspath(__file__))
except NameError:
    import inspect as _inspect
    _addon_dir = _os.path.dirname(_os.path.abspath(_inspect.getfile(_inspect.currentframe())))
if _addon_dir not in _sys.path:
    _sys.path.insert(0, _addon_dir)


class TymelineWorkbench(Workbench):
    MenuText = "Tymeline"
    ToolTip = "Tymeline agent for FreeCAD"

    def Initialize(self):
        from tymeline_rpc import rpc_server

        commands = [
            "Tymeline_Start",
            "Tymeline_Stop",
            "Tymeline_Auto_Start",
            "Tymeline_Pair",
            "Tymeline_Status",
            "Tymeline_Unpair",
        ]
        self.appendToolbar("Tymeline", commands)
        self.appendMenu("Tymeline", commands)

    def Activated(self):
        pass

    def Deactivated(self):
        pass

    def ContextMenu(self, recipient):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


# FreeCAD execs InitGui.py inside a function. Names assigned in this file are
# not visible inside the class body, so the icon path has to be set after it.
# package.xml points the Addon Manager at the same file.
TymelineWorkbench.Icon = _os.path.join(_addon_dir, "Resources", "icons", "tymeline.png")

Gui.addWorkbench(TymelineWorkbench())


def _auto_start_mcp():
    try:
        from tymeline_rpc import cloud_link, rpc_server

        settings = rpc_server.load_settings()
        if not settings.get("auto_start_rpc", False):
            return

        msg = cloud_link.start_cloud_link()
        if settings.get("local_listener"):
            msg = f"{msg} {rpc_server.start_rpc_server()}"
        FreeCAD.Console.PrintMessage(f"[Tymeline] Auto-start: {msg}\n")
    except Exception as e:
        FreeCAD.Console.PrintWarning(f"[Tymeline] Auto-start failed: {e}\n")


from PySide import QtCore

QtCore.QTimer.singleShot(0, _auto_start_mcp)
