"""Install or remove a locally built World texture mod."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from world import BACKUP_SUFFIX, OVERLAYS, SETS, checksum


def ensure_closed():
    if os.name == "nt":
        processes = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq SimCity.exe", "/FO", "CSV", "/NH"]
        )
        if b'"simcity.exe"' in processes.lower():
            raise ValueError("Close SimCity before changing its files")


def check_hash(path, expected):
    if not path.is_file() or checksum(path) != expected:
        raise ValueError(f"Unexpected or missing file: {path}")


def update(mode, game, build, sets):
    data = game.resolve() / "SimCityData"
    build = build.resolve()
    if not data.is_dir() or build.is_relative_to(data.parent):
        raise ValueError("Choose the game directory and a build directory outside it")
    manifest = json.loads((build / "install.json").read_text(encoding="utf-8"))
    available = set(manifest["overlays"])
    if manifest["archives"]:
        available.add("conflicts")
    selected = set(sets or available)
    if not selected or not selected <= available:
        raise ValueError(f"Sets available in this build: {', '.join(sorted(available))}")
    archives = manifest["archives"] if "conflicts" in selected else {}
    overlays = {}
    files = []
    cleanup_backups = []
    for name, hashes in archives.items():
        if Path(name).name != name or not name.startswith("SimCity") or not name.endswith(".package"):
            raise ValueError(f"Unexpected archive name: {name}")
        installed = data / name
        backup = data / (name + BACKUP_SUFFIX)
        original, patched = hashes["original"], hashes["patched"]
        current = checksum(installed)
        has_backup = backup.exists()
        if has_backup:
            check_hash(backup, original)
        if current not in (original, patched):
            raise ValueError(f"Unexpected archive version: {installed}")
        if current == patched and not has_backup:
            raise ValueError(f"Missing original backup: {backup}")

        if mode == "install" and current == original:
            check_hash(build / name, patched)
            files.append((build / name, installed, None if has_backup else backup, patched, original))
        elif mode == "uninstall":
            if current == patched:
                files.append((backup, installed, None, original, patched))
            if has_backup:
                cleanup_backups.append((installed, backup, original))

    for set_name, digest in manifest["overlays"].items():
        if set_name not in selected:
            continue
        name = OVERLAYS[set_name]
        installed = data / name
        if installed.exists():
            check_hash(installed, digest)
            if mode == "uninstall":
                overlays[name] = digest
        elif mode == "install":
            check_hash(build / name, digest)
            overlays[name] = digest
    ensure_closed()
    with TemporaryDirectory(dir=data, prefix=".world-install-") as scratch:
        temporary = Path(scratch)
        for source, target, _, expected, previous_hash in files:
            stage = temporary / target.name
            shutil.copyfile(source, stage)
            check_hash(stage, expected)
            previous = temporary / (target.name + ".previous")
            shutil.copyfile(target, previous)
            check_hash(previous, previous_hash)
        if mode == "install":
            for name, digest in overlays.items():
                shutil.copyfile(build / name, temporary / name)
                check_hash(temporary / name, digest)
        ensure_closed()
        changes = []
        new_backups = []
        changed_overlays = []
        try:
            for _, target, backup, _, previous_hash in files:
                check_hash(target, previous_hash)
                previous = temporary / (target.name + ".previous")
                if backup is not None:
                    if backup.exists():
                        raise ValueError(f"Backup already exists: {backup}")
                    previous.rename(backup)
                    new_backups.append(backup)
                    previous = backup
                (temporary / target.name).replace(target)
                changes.append((previous, target))
            for name, digest in overlays.items():
                installed = data / name
                stage = temporary / name
                if mode == "install":
                    if installed.exists():
                        raise ValueError(f"Overlay already exists: {name}")
                    stage.rename(installed)
                else:
                    check_hash(installed, digest)
                    installed.rename(stage)
                changed_overlays.append(name)
        except (OSError, ValueError):
            for name in reversed(changed_overlays):
                if mode == "install":
                    (data / name).unlink()
                else:
                    (temporary / name).rename(data / name)
            for previous, target in reversed(changes):
                previous.replace(target)
            for backup in new_backups:
                backup.unlink(missing_ok=True)
            raise
        for installed, backup, original in cleanup_backups:
            check_hash(installed, original)
            check_hash(backup, original)
            backup.unlink()
    action = "Installed" if mode == "install" else "Removed"
    print(f"{action} World sets: {', '.join(sorted(selected))}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("install", "uninstall"))
    parser.add_argument("--game", required=True, type=Path)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--sets", nargs="+", choices=SETS, help="Sets to change (default: all in the build)")
    args = parser.parse_args()
    try:
        update(args.mode, args.game, args.build, args.sets)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
