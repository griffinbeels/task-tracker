"""Link Applications to the daily bundle so rebuilds and source updates stay live."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

try:
    from .bootstrap import BootstrapError, primary_checkout
except ImportError:
    from bootstrap import BootstrapError, primary_checkout


def install(source: Path, applications: Path = Path("/Applications"), *, dry_run=False) -> Path:
    source = source.resolve()
    if sys.platform != "darwin":
        raise BootstrapError("Applications installation is available on macOS only.")
    if not (source / ".git").is_dir() or source != primary_checkout(source):
        raise BootstrapError("Install from the primary checkout after merging; worktrees stay previews.")
    bundle = source / "dist/Task Tracker.app"
    try:
        configuration = json.loads((bundle / "Contents/Resources/task-tracker.json").read_text(encoding="utf-8"))
        console = Path(configuration["console"]).resolve()
        daily = (Path(configuration["source"]).resolve() == source
                 and not {"config_dir", "port"}.intersection(configuration)
                 and (console / ".git").is_dir())
    except (OSError, ValueError, KeyError, TypeError):
        daily = False
    if not daily:
        raise BootstrapError("Build the daily app with run.command first; its source and console must use primary checkouts.")
    target = applications.expanduser().absolute() / bundle.name
    if target.is_symlink() and target.resolve() == bundle:
        return target
    if target.exists() or target.is_symlink():
        raise BootstrapError(f"{target} already exists and is not this checkout's app; nothing was replaced.")
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Keep the target path stable: the builder atomically replaces dist's
        # bundle and this link follows it, without an updater or a second copy.
        target.symlink_to(bundle, target_is_directory=True)
    return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--applications", type=Path, default=Path("/Applications"))
    args = parser.parse_args(argv)
    source = Path(__file__).resolve().parent.parent
    try:
        target = install(source, args.applications, dry_run=args.dry_run)
        print(f"{'Would link' if args.dry_run else 'Installed'}: {target} -> {source / 'dist/Task Tracker.app'}")
        return 0
    except (BootstrapError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
