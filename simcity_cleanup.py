"""Build and manage SimCity cleanup mods from a local installation."""

import argparse
import hashlib
import os
from pathlib import Path
import re
from struct import pack, pack_into, unpack_from
import subprocess
from tempfile import TemporaryDirectory

PROPERTY = 0x00B1B104
JAVASCRIPT = 0x67771F5C
SPONSORED = {
    "SimCity_DLC0.package": {
        (0x53F0C900, 0xFB212A3C),  # Nissan
        (0x56F0C900, 0x2AD521BA), (0x56F0C900, 0xD1C6C819),  # Crest
        (0x56F0C900, 0xDAE498C6), (0x56F0C900, 0xED2CD768),
        (0x56F0C900, 0x51B708A9), (0x56F0C900, 0x3CFDEABA),
        (0x56F0C900, 0x103BB38A), (0x56F0C900, 0x83559008),
        (0x56F0C900, 0x59F58F96), (0x56F0C900, 0x83B7F016),
    },
    "SimCityDataEP1.package": {(0x65F0C900, 0x2E446857)},  # Progressive
}
LEGACY_TEXT = Path("Locale/ru-ru/000_Codex_EP1_Russian_Thoughts.package")
LEGACY_HASH = "0abd2b4f2d9b1108253776a03c89e1f7e036101bf1e62bb71098adfde61d7d69"

def refpack(data, expected):
    flags, magic = data[:2]
    width = 4 if flags & 128 else 3
    assert flags & 0x3e == 0x10 and magic == 0xfb
    assert int.from_bytes(data[2:2+width], 'big') == expected
    cursor = 2 + width * (2 if flags & 1 else 1)
    result = bytearray()
    while cursor < len(data):
        code = data[cursor]
        cursor += 1
        length = distance = 0
        if code < 0x80:
            length = ((code & 28) >> 2) + 3
            distance = ((code & 96) << 3) + data[cursor] + 1
            literal = code & 3
            cursor += 1
        elif code < 0xc0:
            first, second = data[cursor:cursor+2]
            length = (code & 63) + 4
            distance = ((first & 63) << 8) + second + 1
            literal = first >> 6
            cursor += 2
        elif code < 0xe0:
            first, second, third = data[cursor:cursor+3]
            length = ((code & 12) << 6) + third + 5
            distance = ((code & 16) << 12) + (first << 8) + second + 1
            literal = code & 3
            cursor += 3
        else:
            literal = (code & 31) * 4 + 4 if code < 0xfc else code & 3
        result.extend(data[cursor:cursor+literal])
        cursor += literal
        for _ in range(length):
            result.append(result[-distance])
        if code >= 0xfc:
            break
    assert len(result) == expected
    return result

def read_resources(path, select):
    """Read only matching resources from a retail SimCity DBPF package."""
    resources = {}
    with path.open("rb") as stream:
        header = stream.read(96)
        if header[:8] != b"DBPF\x03\0\0\0":
            raise ValueError(f"Unsupported DBPF version in {path.name}")
        count, = unpack_from("<I", header, 36)
        index_offset, = unpack_from("<I", header, 64)
        stream.seek(index_offset)
        flags, = unpack_from("<I", stream.read(4))
        if not 4 <= flags <= 7:
            raise ValueError(f"Unsupported DBPF index in {path.name}")
        shared = [
            unpack_from("<I", stream.read(4))[0] if flags & (1 << field) else None
            for field in range(3)
        ]
        index = []
        for _ in range(count):
            kind, group, _ = [
                unpack_from("<I", stream.read(4))[0] if value is None else value
                for value in shared
            ]
            instance, offset, stored, expanded, compression, _ = unpack_from(
                "<IIIIhH", stream.read(20)
            )
            key = kind, group, instance
            if select(key):
                index.append((key, offset, stored & 0x7FFFFFFF, expanded, compression))

        for key, offset, stored, expanded, compression in index:
            if key in resources or offset < 96 or offset + stored > index_offset:
                raise ValueError(f"Invalid resource {key} in {path.name}")
            stream.seek(offset)
            raw = stream.read(stored)
            if compression == -1:
                raw = refpack(raw, expanded)
            elif compression != 0:
                raise ValueError(f"Unsupported compression in {path.name}")
            if len(raw) != expanded:
                raise ValueError(f"Wrong resource size in {path.name}")
            resources[key] = bytes(raw)
    return resources


def without_menu_category(raw):
    marker = bytes.fromhex("0db9fc630020")
    offset = raw.find(marker)
    if offset < 0:
        return raw
    flags, count, width = unpack_from(">HII", raw, offset + 6)
    start = offset + 16
    end = start + width * count
    if raw.find(marker, offset + 1) >= 0 or not flags & 0x30 or flags & 0x40 or width != 12 or end > len(raw):
        raise ValueError("Unexpected construction menu category format")
    return raw[:offset + 8] + pack(">I", 0) + raw[offset + 12:start] + raw[end:]


def without_balloons(source):
    declaration = b"simcity.SpeechBalloonPolling.DLC_EP1 = {"
    prefix, polling, events = re.split(
        rb"simcity\.SpeechBalloonPolling\.DLC_EP1 = \{|// Event-Driven Speech Balloons",
        source,
    )
    event_prefix = b"simcity.SpeechBalloonEvents.DataBindings["
    assignments = re.findall(rb"^simcity\..*", events, re.M)
    if not assignments or any(not row.startswith(event_prefix) for row in assignments):
        raise ValueError("Unexpected Cities of Tomorrow balloon script")
    if b"DataBindings: {" not in polling or b"kLocalSpeechBalloonEP1LocaleTable" not in prefix:
        raise ValueError("Unexpected Cities of Tomorrow polling script")
    return prefix + declaration + (
        b"\r\n    unlockBin: simcity.DLC_EP1.kResourceIDDLC_EP1,"
        b"\r\n    DataBindings: {}\r\n};\r\n"
    )


def write_package(records):
    if not records:
        raise ValueError("No resources matched")
    index_size = 8 + 28 * len(records)
    header = bytearray(96)
    header[:4] = b"DBPF"
    for field, value in ((4, 3), (36, len(records)), (44, index_size), (60, 3), (64, 96)):
        pack_into("<I", header, field, value)
    index = bytearray(pack("<II", 4, 0))
    payload = bytearray()
    for key, raw in sorted(records.items()):
        offset = 96 + index_size + len(payload)
        index.extend(pack("<7I", *key, offset, len(raw) | 0x80000000, len(raw), 0))
        payload.extend(raw)
    return bytes(header + index + payload)


def build(data_dir):
    ep1 = data_dir / "SimCityDataEP1.package"
    balloon = JAVASCRIPT, 0, 0x202D03A8
    entries = read_resources(
        ep1, lambda key: key == balloon or (key[0] == PROPERTY and key[1] & 0xFFFF == 0xC900)
    )
    source = entries.pop(balloon, None)
    if not source:
        raise ValueError("Cities of Tomorrow balloon script was not found")

    menu = {}
    for key, raw in entries.items():
        updated = without_menu_category(raw)
        if updated != raw:
            menu[key] = updated

    sponsored = {}
    for filename, ids in SPONSORED.items():
        keys = {(PROPERTY, group, instance) for group, instance in ids}
        originals = read_resources(data_dir / filename, keys.__contains__)
        if originals.keys() != keys:
            raise ValueError(f"Expected sponsored entries were not found in {filename}")
        for key, raw in originals.items():
            updated = without_menu_category(raw)
            if updated == raw:
                raise ValueError(f"Expected sponsored menu category was not found in {filename}")
            sponsored[key] = updated

    return {
        "000_Codex_EP1_Menu_Test.package": write_package(menu),
        "000_Codex_EP1_No_Balloons.package": write_package({balloon: without_balloons(source)}),
        "000_Codex_Sponsored_Buildings.package": write_package(sponsored),
    }


def require_closed():
    if os.name != "nt":
        return
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq SimCity.exe", "/FO", "CSV", "/NH"],
        capture_output=True, check=True,
    )
    if b'"simcity.exe"' in result.stdout.lower():
        raise ValueError("Close SimCity before changing mods")


def apply(data_dir, packages, remove):
    changes = {}
    for name, content in packages.items():
        path = data_dir / name
        if path.exists():
            if path.read_bytes() != content:
                raise ValueError(f"Existing file differs from this mod: {path}")
            if remove:
                changes[path] = None
        elif not remove:
            changes[path] = content
    legacy = data_dir / LEGACY_TEXT
    if legacy.is_file() and hashlib.sha256(legacy.read_bytes()).hexdigest() == LEGACY_HASH:
        changes[legacy] = None
    if not changes:
        print("No changes needed.")
        return

    with TemporaryDirectory(prefix=".simcity-cleanup-", dir=data_dir) as staging:
        folder = Path(staging)
        originals = {}
        staged = {}
        for number, (path, content) in enumerate(changes.items()):
            if content is None:
                originals[path] = folder / f"{number}.original"
            else:
                staged[path] = folder / f"{number}.new"
                staged[path].write_bytes(content)
        require_closed()
        applied = []
        try:
            for path, content in changes.items():
                if content is None:
                    path.rename(originals[path])
                else:
                    if path.exists():
                        raise FileExistsError(path)
                    staged[path].rename(path)
                applied.append(path)
        except OSError:
            for path in reversed(applied):
                if path in originals:
                    originals[path].rename(path)
                else:
                    path.unlink()
            raise
    for path, content in changes.items():
        print(f"{'Removed' if content is None else 'Installed'} {path.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game", type=Path, help="SimCity installation directory")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true", help="Build in memory and print checksums")
    modes.add_argument("--remove", action="store_true", help="Remove matching generated mods")
    args = parser.parse_args()
    data_dir = args.game / "SimCityData"
    try:
        packages = build(data_dir)
        if args.check:
            for name, content in packages.items():
                print(f"{hashlib.sha256(content).hexdigest()}  {name}")
        else:
            require_closed()
            apply(data_dir, packages, args.remove)
    except (OSError, ValueError, AssertionError, IndexError, subprocess.SubprocessError) as error:
        parser.exit(1, f"SimCity cleanup failed: {error or 'unexpected package format'}\n")


if __name__ == "__main__":
    main()
