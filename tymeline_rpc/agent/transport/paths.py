"""Pairing and device-id files. The gateway secret stays in this directory."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

CONFIG_DIRNAME = "tymeline-freecad"
# Default Tymeline WebSocket port. 8001 collides with common local servers.
# A pairing URL that already includes a port is left as written.
WS_PORT = 53117


def config_dir() -> Path:
    override = os.environ.get("TYMELINE_CONFIG_DIR")
    if override:
        path = Path(override)
    else:
        path = _freecad_user_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _freecad_user_dir() -> Path:
    """FreeCAD's versioned user folder, or the old home path when FreeCAD is absent.

    Pytest stubs a ``FreeCAD`` module that imports but has no ``getUserAppDataDir``.
    That is the same case as plain pytest: keep pairing out of a fake app dir.
    """
    try:
        import FreeCAD

        getter = getattr(FreeCAD, "getUserAppDataDir", None)
        if not callable(getter):
            raise AttributeError("getUserAppDataDir")
        return Path(getter()) / "Tymeline"
    except (ImportError, AttributeError, OSError, TypeError):
        return Path.home() / ".config" / CONFIG_DIRNAME


def legacy_config_dir() -> Path:
    return Path.home() / ".config" / CONFIG_DIRNAME


def pairing_path() -> Path:
    return config_dir() / "pairing.json"


def device_id_path() -> Path:
    return config_dir() / "device_id"


def log_path() -> Path:
    return config_dir() / "agent.log"


def migrate_legacy_files() -> list[str]:
    """Copy pairing and device id from the old daemon directory. Never deletes them."""
    legacy = legacy_config_dir()
    current = config_dir()
    copied: list[str] = []
    for name in ("pairing.json", "device_id"):
        src = legacy / name
        dest = current / name
        if not src.is_file() or dest.exists():
            continue
        shutil.copy2(src, dest)
        if name == "pairing.json":
            try:
                os.chmod(dest, 0o600)
            except OSError:
                pass
        copied.append(name)
    return copied
