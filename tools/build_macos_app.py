"""Build a local py2app alias launcher; never publish into another checkout.

https://py2app.readthedocs.io/en/latest/tutorial.html documents alias mode.
It uses live source and this checkout's environment, so it is not distributable.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

try:
    from .bootstrap import BootstrapError, ensure_environment, find_uv, primary_checkout, python_path, run
except ImportError:
    from bootstrap import BootstrapError, ensure_environment, find_uv, primary_checkout, python_path, run


def bundle_settings(source: Path) -> dict:
    # A linked worktree still stays a preview if Git is temporarily unavailable.
    preview = (source / ".git").is_file() or source.resolve() != primary_checkout(source)
    suffix = hashlib.sha256(str(source.resolve()).encode()).hexdigest()[:10]
    name = "Task Tracker Preview" if preview else "Task Tracker"
    settings = {"name": name, "path": source / "dist" / f"{name}.app",
                "identifier": "local.tasktracker" + (f".preview.{suffix}" if preview else "")}
    if preview:
        settings["config_dir"] = str(source / ".preview-data")
        settings["port"] = 18000 + int(suffix, 16) % 20000
    return settings


def setup_source(source: Path, settings: dict) -> str:
    plist = {"CFBundleName": settings["name"], "CFBundleDisplayName": settings["name"],
             "CFBundleIdentifier": settings["identifier"], "CFBundleShortVersionString": "0.1.0",
             "NSHighResolutionCapable": True}
    options = {"alias": True, "argv_emulation": False,
               "iconfile": str(source / "ui/icon.icns"), "plist": plist}
    return ("from setuptools import setup\n"
            f"setup(name={settings['name']!r}, app=[{{'script': {str(source / 'tools/macos_entry.py')!r}, "
            f"'dest_base': {settings['name']!r}}}], options={{'py2app': {options!r}}})\n")


def build(source: Path, console: Path) -> Path:
    if sys.platform != "darwin":
        raise BootstrapError("Build Task Tracker.app on macOS; Windows uses run.bat.")
    source = source.resolve()
    settings = bundle_settings(source)
    python = python_path(source)
    # Build dependencies are optional; ordinary app launches never install them.
    available = run([python, "-c", "import py2app, setuptools"], capture_output=True, text=True)
    if available.returncode:
        install = run([find_uv(), "pip", "install", "--python", python, "-e", console,
                       "-e", f"{source}[mac-app]"], capture_output=True, text=True, timeout=300)
        if install.returncode:
            raise BootstrapError("Could not install Mac packaging tools. Reconnect and run.command again.\n" + install.stderr)
    destination = settings["path"]
    destination.parent.mkdir(exist_ok=True)
    # Stage inside this checkout. A failed build leaves its previous app usable.
    with tempfile.TemporaryDirectory(prefix=".mac-build-", dir=source) as temporary:
        scratch = Path(temporary)
        setup = scratch / "setup.py"
        setup.write_text(setup_source(source, settings), encoding="utf-8")
        result = run([python, setup, "py2app", "--alias", "--dist-dir", scratch / "dist",
                      "--bdist-base", scratch / "build"], cwd=scratch,
                     capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise BootstrapError("Mac app build failed; any previous launcher remains available.\n" + result.stderr + result.stdout[-3000:])
        bundle = scratch / "dist" / destination.name
        configuration = {"source": str(source), "console": str(console)}
        configuration.update({key: settings[key] for key in ("config_dir", "port") if key in settings})
        (bundle / "Contents/Resources/task-tracker.json").write_text(json.dumps(configuration, indent=2) + "\n", encoding="utf-8")
        # py2app signs its own output. The local configuration is an added resource.
        signed = run(["/usr/bin/codesign", "--force", "--sign", "-", bundle], capture_output=True, text=True)
        if signed.returncode:
            raise BootstrapError("Could not sign the local app launcher.\n" + signed.stderr)
        previous = destination.with_suffix(".app.previous")
        if previous.exists():
            shutil.rmtree(previous)
        if destination.exists():
            destination.rename(previous)
        try:
            shutil.move(bundle, destination)
        except OSError:
            if previous.exists():
                previous.rename(destination)
            raise
        if previous.exists():
            shutil.rmtree(previous)
    return destination


if __name__ == "__main__":
    repo = Path(__file__).resolve().parent.parent
    print(build(repo, ensure_environment(repo)))
