"""Dependency-light entry for the source-backed app; app.py remains the app."""
from __future__ import annotations

import json
import os
from pathlib import Path
import runpy
import sys

try:
    from .bootstrap import ensure_environment
except ImportError:
    from bootstrap import ensure_environment


def app_bundle() -> Path | None:
    for path in Path(sys.executable).parents:
        if path.suffix == ".app":
            return path
    resource = os.environ.get("RESOURCEPATH")
    if resource:
        return Path(resource).parent.parent
    return None


def source_checkout() -> Path:
    return Path(__file__).resolve().parent.parent


def report_error(source: Path, message: str) -> None:
    sys.path.insert(0, str(source))
    from desktop import report_fatal
    report_fatal(message)


def main(*, check_only=False) -> int:
    source = source_checkout()
    try:
        bundle = app_bundle()
        if bundle:
            os.environ["TASK_TRACKER_APP_BUNDLE"] = str(bundle)
            configuration_path = bundle / "Contents/Resources/task-tracker.json"
            if configuration_path.is_file():
                configuration = json.loads(configuration_path.read_text(encoding="utf-8"))
                if Path(configuration["source"]).resolve() != source:
                    raise RuntimeError("The app launcher points at a different source checkout. Run run.command again.")
                os.environ.setdefault("CLAUDE_CONSOLE_PATH", configuration["console"])
                for key, variable in (("config_dir", "TASK_TRACKER_CONFIG_DIR"), ("port", "TASK_TRACKER_PORT")):
                    if key in configuration:
                        os.environ.setdefault(variable, str(configuration[key]))
        if check_only:
            console = ensure_environment(source, check_only=True)
            print(json.dumps({"source": str(source), "console": str(console),
                              "python": sys.version.split()[0], "bundle": str(bundle)}))
            return 0
        ensure_environment(source)
        os.chdir(source)
        sys.path.insert(0, str(source))
        runpy.run_path(str(source / "app.py"), run_name="__main__")
        return 0
    except Exception as error:
        if check_only:
            print(f"ERROR: {error}", file=sys.stderr)
        else:
            report_error(source, f"Task Tracker could not start.\n\n{error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(check_only="--check-only" in sys.argv))
