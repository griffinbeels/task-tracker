"""Shared source-launch policy for Windows setup, Mac setup and the Dock app.

The environment belongs to this checkout. Git identifies the primary repository
only to discover its sibling dependency; setup never repoints another checkout.
"""
from __future__ import annotations

import argparse
import importlib
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
from urllib.parse import urlparse
from urllib.request import url2pathname

REPO = Path(__file__).resolve().parent.parent


class BootstrapError(RuntimeError):
    """An actionable setup failure, safe to show before GUI imports."""


def run(args, **kwargs):
    """Setup children inherit no extra Windows console or mouse feedback."""
    if sys.platform == "win32":
        startup = subprocess.STARTUPINFO()
        # STARTF_FORCEOFFFEEDBACK is a Win32 flag not re-exported by Python 3.12.
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW | 0x80
        startup.wShowWindow = subprocess.SW_HIDE
        kwargs.update(creationflags=subprocess.CREATE_NO_WINDOW, startupinfo=startup)
    return subprocess.run([str(arg) for arg in args], **kwargs)


def primary_checkout(source: Path) -> Path:
    """Find the primary checkout regardless of linked-worktree nesting depth."""
    try:
        result = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                     cwd=source, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            common = Path(result.stdout.strip())
            return (common if common.is_absolute() else source / common).resolve().parent
    except (OSError, subprocess.TimeoutExpired):
        pass
    # A source archive has no Git identity; its actual sibling is still useful.
    return source.resolve()


def find_console(source: Path, env=None) -> Path:
    env = os.environ if env is None else env
    configured = env.get("CLAUDE_CONSOLE_PATH")
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_absolute():
            candidate = source / candidate
        if is_console_checkout(candidate):
            return candidate.resolve()
        raise BootstrapError("CLAUDE_CONSOLE_PATH does not point to the claude-console "
                             "checkout with its pyproject.toml. Correct that path and run setup again.")
    for name in ("claude-console", "claude_console"):
        candidate = primary_checkout(source).parent / name
        if is_console_checkout(candidate):
            return candidate.resolve()
    raise BootstrapError("Could not find claude-console. Clone "
                         "https://github.com/griffinbeels/claude_console.git beside the "
                         "primary Task Tracker repository, or set CLAUDE_CONSOLE_PATH "
                         "to its checkout. Both claude-console and claude_console work.")


def is_console_checkout(path: Path) -> bool:
    try:
        project = tomllib.loads((path / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        return project.get("name", "").lower().replace("_", "-") == "claude-console"
    except (OSError, ValueError, KeyError):
        return False


def find_uv(env=None, home=None) -> Path:
    env = os.environ if env is None else env
    configured = env.get("TASK_TRACKER_UV")
    if configured and Path(configured).is_file():
        return Path(configured)
    found = shutil.which("uv", path=env.get("PATH", ""))
    if found:
        return Path(found)
    home = Path.home() if home is None else home
    for candidate in (home / ".local/bin/uv", Path("/opt/homebrew/bin/uv"), Path("/usr/local/bin/uv")):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise BootstrapError("uv was not found. Install it from https://docs.astral.sh/uv/ "
                         "then double-click run.command (Mac) or run.bat (Windows).")


def python_path(source: Path) -> Path:
    return source / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def check_editable(name: str, source: Path) -> None:
    """Reject stale requirements and editables belonging to another checkout.

    pip check alone cannot see a requirement added to the source since its last
    installation. Compare the declared requirements with installed metadata too.
    """
    from packaging.requirements import Requirement

    distribution = metadata.distribution(name)
    direct = json.loads(distribution.read_text("direct_url.json") or "{}")
    parsed = urlparse(direct.get("url", ""))
    file_path = f"//{parsed.netloc}{parsed.path}" if parsed.netloc else parsed.path
    location = Path(url2pathname(file_path)) if parsed.scheme == "file" else None
    if not direct.get("dir_info", {}).get("editable") or location is None or location.resolve() != source.resolve():
        raise BootstrapError(f"{name} is installed from a different checkout or is not editable.")
    project = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    installed = {Requirement(value) for value in distribution.requires or []}
    if any(Requirement(value) not in installed for value in project.get("dependencies", [])):
        raise BootstrapError(f"{name} requirements changed. Setup must refresh the installation.")


def probe(source: Path, console: Path) -> None:
    if sys.version_info[:2] != (3, 12):
        raise BootstrapError("Task Tracker needs Python 3.12. Run setup to repair .venv.")
    check_editable("task-tracker", source)
    check_editable("claude-console", console)
    # These imports must be safe before any native window is created. They also
    # catch a broken platform backend that dependency metadata cannot describe.
    for name in ("webview", "pyperclip", "yaml", "claude_console"):
        importlib.import_module(name)


def readiness(source: Path, console: Path, uv: Path) -> tuple[bool, str]:
    python = python_path(source)
    commands = ([python, source / "tools/bootstrap.py", "--probe", console],
                [uv, "pip", "check", "--python", python])
    for command in commands:
        try:
            result = run(command, cwd=source, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as error:
            return False, str(error)
        if result.returncode:
            return False, (result.stderr or result.stdout).strip()
    return True, ""


def ensure_environment(source: Path, *, check_only=False) -> Path:
    source = source.resolve()
    console = find_console(source)
    uv = find_uv()
    ready, reason = readiness(source, console, uv)
    if ready:
        return console
    if not check_only:
        result = run([uv, "pip", "install", "--python", python_path(source),
                      "-e", console, "-e", source], cwd=source,
                     capture_output=True, text=True, timeout=300)
        ready, reason = readiness(source, console, uv)
        if ready:
            return console
        reason = "\n".join(filter(None, [reason, result.stderr.strip()]))
    raise BootstrapError("Task Tracker's environment is not ready. Double-click "
                         "run.command (Mac) or run.bat (Windows) to repair it; "
                         "reconnect if packages need downloading.\n\n" + reason)


def mac_open_command(bundle: Path) -> list[str]:
    """LaunchServices needs explicit forwarding; Popen's environment is insufficient."""
    command = ["/usr/bin/open", "-n"]
    for variable in ("TASK_TRACKER_CONFIG_DIR", "TASK_TRACKER_PORT", "CLAUDE_CONSOLE_PATH"):
        if variable in os.environ:
            command.extend(["--env", f"{variable}={os.environ[variable]}"])
    return command + [str(bundle)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--mac-app", action="store_true")
    parser.add_argument("--setup-only", action="store_true")
    parser.add_argument("--install", action="store_true", help="Link the daily Mac app into Applications")
    args = parser.parse_args(argv)
    try:
        if args.install and not args.mac_app:
            raise BootstrapError("Use run.command --install for Mac installation.")
        if args.probe:
            probe(REPO, args.probe)
            return 0
        console = ensure_environment(REPO, check_only=args.check_only)
        if args.mac_app:
            from build_macos_app import build
            bundle = build(REPO, console)
            if args.install:
                from install_macos_app import install
                bundle = install(REPO)
            print(f"Ready: {bundle}")
            if not args.setup_only:
                run(mac_open_command(bundle), check=True)
        return 0
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
