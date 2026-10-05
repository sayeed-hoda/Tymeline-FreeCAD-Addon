"""Start the Tymeline daemon from inside FreeCAD.

FreeCAD's Python does not have the WebSocket package. The addon only starts
the localhost listener. This module spawns the separate ``freecad-agent``
program, the same moment the listener starts, and leaves that program running
if FreeCAD later closes.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
from pathlib import Path


def project_root(start: Path | None = None) -> Path | None:
    """Directory that contains this repo's ``src/freecad_agent`` package."""
    env = os.environ.get("FREECAD_AGENT_PROJECT", "").strip()
    if env and _is_project(Path(env)):
        return Path(env)
    recorded = Path.home() / ".config" / "tymeline-freecad" / "project_dir"
    try:
        if recorded.is_file():
            raw = recorded.read_text(encoding="utf-8").strip()
            if raw and _is_project(Path(raw)):
                return Path(raw)
    except OSError:
        pass
    here = start if start is not None else Path(__file__).resolve()
    for parent in (here, *here.parents):
        if _is_project(parent):
            return parent
    return None


def agent_command(start: Path | None = None) -> list[str] | None:
    """Argv up to, but not including, the ``serve`` / ``pair`` subcommand."""
    env_bin = os.environ.get("FREECAD_AGENT_BIN", "").strip()
    if env_bin and os.access(env_bin, os.X_OK):
        return [env_bin]
    found = shutil.which("freecad-agent")
    if found:
        return [found]
    root = project_root(start)
    if root is None:
        return None
    venv_bin = root / ".venv" / "bin" / "freecad-agent"
    if os.access(venv_bin, os.X_OK):
        return [str(venv_bin)]
    uv = shutil.which("uv")
    if uv is not None and (root / "pyproject.toml").is_file():
        return [uv, "run", "--project", str(root), "freecad-agent"]
    return None


def pairing_is_stored(path: Path | None = None) -> bool:
    dest = path if path is not None else Path.home() / ".config" / "tymeline-freecad" / "pairing.json"
    try:
        data = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    return all(isinstance(data.get(key), str) and data[key] for key in ("url", "token_id", "secret"))


def read_pid(path: Path | None = None) -> int | None:
    dest = path if path is not None else Path.home() / ".config" / "tymeline-freecad" / "agent.pid"
    try:
        return int(dest.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


# FreeCAD's AppImage exports these for its own interpreter. The agent is this
# repo's virtualenv, and it cannot start while they point at the AppImage.
_PYTHON_ENV_KEYS = (
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "PYTHONEXECUTABLE",
    "PYTHONNOUSERSITE",
    "PYTHONSAFEPATH",
    "PYTHONUSERBASE",
)


def subprocess_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for ``freecad-agent``, without FreeCAD's Python home."""
    env = dict(os.environ if base is None else base)
    home = env.get("PYTHONHOME", "")
    for key in _PYTHON_ENV_KEYS:
        env.pop(key, None)
    prefixes = [home.rstrip("/")] if home else []
    library_path = env.get("LD_LIBRARY_PATH", "")
    if library_path:
        kept = []
        for part in library_path.split(":"):
            if not part or "/.mount_" in part:
                continue
            if any(part == prefix or part.startswith(prefix + "/") for prefix in prefixes):
                continue
            kept.append(part)
        if kept:
            env["LD_LIBRARY_PATH"] = ":".join(kept)
        else:
            env.pop("LD_LIBRARY_PATH", None)
    return env


def pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def start_daemon(
    *,
    start: Path | None = None,
    pairing_file: Path | None = None,
    pid_file: Path | None = None,
    log_file: Path | None = None,
    popen: object | None = None,
) -> str:
    """Spawn ``freecad-agent serve`` when a pairing key is stored and none is running."""
    if not pairing_is_stored(pairing_file):
        return (
            "Tymeline listener is up. Choose Pair with Tymeline in the Tymeline menu "
            "and paste your TYM1 key."
        )
    existing = read_pid(pid_file)
    if existing is not None and pid_is_alive(existing):
        return f"Tymeline agent is already running (pid {existing})."
    command = agent_command(start)
    if command is None:
        return (
            "Tymeline listener is up, but freecad-agent was not found. "
            "Link this addon from the project folder, or set FREECAD_AGENT_BIN."
        )
    log_dest = log_file if log_file is not None else Path.home() / ".config" / "tymeline-freecad" / "agent.log"
    try:
        log_dest.parent.mkdir(parents=True, exist_ok=True)
        log = log_dest.open("a", encoding="utf-8")
    except OSError as exc:
        return f"Tymeline agent did not start: {exc}"
    spawn = popen if popen is not None else subprocess.Popen
    try:
        spawn(
            [*command, "serve"],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
            close_fds=True,
            env=subprocess_env(),
        )
    except OSError as exc:
        log.close()
        return f"Tymeline agent did not start: {exc}"
    log.close()
    return "Tymeline agent started. It will connect once this listener answers."


def stop_daemon(pid_file: Path | None = None) -> str:
    existing = read_pid(pid_file)
    if existing is None or not pid_is_alive(existing):
        return "Tymeline agent was not running."
    os.kill(existing, signal.SIGTERM)
    return f"Tymeline agent stopping (pid {existing})."


def pair_and_start(token: str, *, start: Path | None = None) -> str:
    """Store a pairing key with the daemon program, then start it."""
    command = agent_command(start)
    if command is None:
        raise ValueError(
            "freecad-agent was not found. Link this addon from the project folder, "
            "or set FREECAD_AGENT_BIN."
        )
    proc = subprocess.run(
        [*command, "pair", token],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=subprocess_env(),
    )
    visible = (proc.stderr or proc.stdout or "Pairing failed.").replace(token, "[redacted]")
    if proc.returncode != 0:
        raise ValueError(visible.strip())
    started = start_daemon(start=start)
    saved = (proc.stdout or "").replace(token, "[redacted]").strip()
    return f"{saved} {started}".strip()


def _is_project(path: Path) -> bool:
    return (path / "pyproject.toml").is_file() and (path / "src" / "freecad_agent" / "cli.py").is_file()
