"""Build IllustrationJaNai texture replacements for SimCity’s 3D world."""
from collections import Counter
from contextlib import ExitStack
from hashlib import file_digest, sha256
from io import BytesIO
import json
from pathlib import Path
from shutil import copyfile
from struct import error as StructError, iter_unpack, pack, pack_into, unpack_from
from tempfile import NamedTemporaryFile, TemporaryDirectory

from PIL import Image

RW4, RASTER = 0x2F4E681B, 0x2F4E681C
TEXTURE, BLOB = 0x20003, 0x10030
FORMATS = {21: "BGRA8", 50: "L8", 0x31545844: "DXT1", 0x33545844: "DXT3", 0x35545844: "DXT5"}


def decode_pixels(fmt, width, height, payload):
    if not (1 <= width <= 8192 and 1 <= height <= 8192):
        raise ValueError(f"Unsupported dimensions {width}×{height}")
    if fmt == 21:
        size = width * height * 4
        if len(payload) < size:
            raise ValueError("Truncated BGRA pixels")
        return Image.frombytes("RGBA", (width, height), payload[:size], "raw", "BGRA")
    if fmt == 50:
        size = width * height
        if len(payload) < size:
            raise ValueError("Truncated L8 pixels")
        return Image.frombytes("L", (width, height), payload[:size])
    if fmt not in FORMATS:
        raise ValueError(f"Unsupported pixel format 0x{fmt:08x}")
    block_size = 8 if fmt == 0x31545844 else 16
    size = ((width + 3) // 4) * ((height + 3) // 4) * block_size
    if len(payload) < size:
        raise ValueError("Truncated DXT pixels")
    header = b"DDS " + pack("<7I", 124, 0x81007, height, width, size, 0, 1)
    header += bytes(44) + pack("<8I", 32, 4, fmt, 0, 0, 0, 0, 0)
    header += pack("<5I", 0x1000, 0, 0, 0, 0)
    with Image.open(BytesIO(header + payload[:size])) as image:
        return image.convert("RGBA")


def textures(kind, raw):
    if kind == RASTER:
        _, w, h, mips, _, fmt, size = unpack_from(">7I", raw)
        if not mips or size > len(raw) - 28:
            raise ValueError("Invalid Raster mip payload")
        yield 0, fmt, w, h, mips, raw[28:28 + size]
        return
    if raw[:8] != b"\x89RW4w32\0":
        raise ValueError("Unknown RenderWare signature")
    _, count = unpack_from("<II", raw, 28)
    index, = unpack_from("<I", raw, 48)
    base, = unpack_from("<I", raw, 68)
    if not (index >= 152 and index + 24 * count <= base <= len(raw)):
        raise ValueError("Invalid RW4 section index")
    sections = []
    for n in range(count):
        position, _, length, _, _, code = unpack_from("<6I", raw, index + n * 24)
        if code == BLOB:
            position += base
        sections.append((position, length, code))
    for n, (position, length, code) in enumerate(sections):
        if code != TEXTURE:
            continue
        if length < 32 or position + length > len(raw):
            raise ValueError("Invalid RW4 texture header")
        fmt, _, _, w, h, mip_info, _, _, blob = unpack_from("<IIIHHIIII", raw, position)
        if blob >= count:
            raise ValueError("Missing RW4 mip section")
        start, size, code = sections[blob]
        if code != BLOB or start + size > len(raw):
            raise ValueError("Invalid RW4 mip section")
        yield n, fmt, w, h, mip_info >> 8, raw[start:start + size]


OVERLAYS = {
    "rw4": "000_Codex_World_RW4.package",
    "l8": "000_Codex_World_L8.package",
    "decals": "000_Codex_World_Decals.package",
    "raster": "000_Codex_World_Raster.package",
    "cubemaps": "000_Codex_World_Cubemaps.package",
}
SETS = (*OVERLAYS, "conflicts")
BACKUP_SUFFIX = ".before-world-hd.bak"
# The cache is versioned independently of UI because channel handling differs.
CACHE_VERSION = "world-illustration-v1"


def checksum(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def mip_size(fmt, width, height):
    if fmt in (21, 50):
        return width * height * (4 if fmt == 21 else 1)
    block = 8 if fmt == 0x31545844 else 16
    return ((width + 3) // 4) * ((height + 3) // 4) * block


def encode_pixels(image, fmt):
    if fmt == 21:
        return image.tobytes("raw", "BGRA")
    if fmt == 50:
        return image.tobytes()
    if fmt == 0x31545844:
        alpha = image.getchannel("A").point(lambda value: 255 if value >= 128 else 0)
        image.putalpha(alpha)
    dds = BytesIO()
    image.save(dds, "DDS", pixel_format=FORMATS[fmt])
    data = dds.getvalue()
    if data[:4] != b"DDS " or unpack_from("<I", data, 84)[0] != fmt:
        raise ValueError(f"Pillow cannot encode {FORMATS[fmt]}")
    pixels = data[128:]
    if len(pixels) != mip_size(fmt, *image.size):
        raise ValueError(f"Unexpected encoded size for {FORMATS[fmt]}")
    if fmt == 0x31545844 and decode_pixels(fmt, *image.size, pixels).getchannel("A").tobytes() != alpha.tobytes():
        return None
    return pixels


def eligible(fmt, w, h, mips):
    return fmt in FORMATS and 4 < min(w, h) <= max(w, h) <= 8192 and 1 <= mips <= max(w, h).bit_length()


def upgrade_raster(raw, render, stats):
    raster_type, w, h, mips, pixel_size, fmt = unpack_from(">6I", raw)
    if fmt != 21 or not eligible(fmt, w, h, mips):
        stats["unsupported or small Raster"] += 1
        return None
    offset = 24
    for level in range(mips):
        if offset + 4 > len(raw):
            raise ValueError("Truncated Raster mip chain")
        length, = unpack_from(">I", raw, offset)
        if length != mip_size(fmt, max(1, w >> level), max(1, h >> level)):
            stats["unrecognized Raster layout"] += 1
            return None
        offset += 4 + length
    if offset != len(raw):
        stats["unrecognized Raster layout"] += 1
        return None
    top = encode_pixels(render(fmt, w, h, raw[28:28 + w*h*4], True), fmt)
    stats["Raster"] += 1
    return pack(">7I", raster_type, 2*w, 2*h, mips+1, pixel_size, fmt, len(top)) + top + raw[24:]


def upgrade_rw4(raw, source, render, stats):
    if not source:
        return None
    kind, count = unpack_from("<II", raw, 28)
    index, = unpack_from("<I", raw, 48)
    base, = unpack_from("<I", raw, 68)
    if unpack_from("<I", raw, 76)[0] != len(raw) - base:
        stats["unrecognized RW4 length"] += len(source)
        return None
    entries = [unpack_from("<6I", raw, index + 24*i) for i in range(count)]
    refs = Counter(unpack_from("<I", raw, entries[n][0] + 28)[0] for n, *_ in source)
    updated = None
    for n, fmt, w, h, mips, old in source:
        if not eligible(fmt, w, h, mips):
            stats["unsupported or small RW4"] += 1
            continue
        pos = entries[n][0]
        texture_flags, = unpack_from("<I", raw, pos + 4)
        blob, = unpack_from("<I", raw, pos + 28)
        alignment = max(1, entries[blob][3])
        chain = sum(mip_size(fmt, max(1, w >> i), max(1, h >> i)) for i in range(mips))
        cube = kind == 0x04000000 and bool(texture_flags & 0x1000) and w == h
        if refs[blob] != 1 or len(old) != chain * (6 if cube else 1) or alignment > 4096 or alignment & (alignment-1):
            stats["unrecognized RW4 layout"] += 1
            continue
        replacements = []
        for start in range(0, len(old), chain):
            original = old[start:start+chain]
            top = encode_pixels(render(fmt, w, h, original, False), fmt)
            if top is None:
                break
            replacements.extend((top, original))
        else:
            data = b"".join(replacements)
            if updated is None:
                updated = bytearray(raw)
            updated.extend(bytes((-len(updated)) % alignment))
            pack_into("<I", updated, index + 24*blob, len(updated)-base)
            pack_into("<I", updated, index + 24*blob + 8, len(data))
            info, = unpack_from("<I", raw, pos+16)
            pack_into("<HHI", updated, pos+12, 2*w, 2*h, info+256)
            updated.extend(data)
            stats["cubemaps" if cube else FORMATS[fmt]] += 1
            continue
        stats["changed DXT1 alpha coverage"] += 1
    if updated is not None:
        pack_into("<I", updated, 76, len(updated)-base)
    return updated


def renderer(args, load_model, upscale):
    cache = args.cache.resolve() / CACHE_VERSION
    if cache.is_relative_to(args.game.resolve()):
        raise ValueError("Put the cache outside the game directory")
    cache.mkdir(parents=True, exist_ok=True)
    model = None

    def render(fmt, w, h, payload, raster):
        nonlocal model
        key = sha256(pack("<III?", fmt, w, h, raster) + payload).hexdigest()
        path = cache / f"{key}.png"
        size = 2*w, 2*h
        mode = "L" if fmt == 50 else "RGBA"
        if path.is_file():
            with Image.open(path) as cached:
                if cached.size != size or cached.mode != mode:
                    raise ValueError(f"Invalid cached image. Remove it and retry: {path}")
                return cached.copy()
        if model is None:
            import torch

            device = args.device if args.device != "auto" else "cuda" if torch.cuda.is_available() else "cpu"
            if device == "cuda" and not torch.cuda.is_available():
                raise ValueError("CUDA unavailable. Install a CUDA build of PyTorch or use --device cpu.")
            torch.set_num_threads(min(torch.get_num_threads(), 4))
            print(f"Loading IllustrationJaNai HAT-L on {device}", flush=True)
            model = load_model(args.weights, device)
        source = decode_pixels(fmt, w, h, payload).convert("RGBA")
        sampler = Image.Resampling.NEAREST if raster else Image.Resampling.BILINEAR
        alpha = source.getchannel("A").resize(size, sampler)
        image = upscale(model, source, size, alpha).convert(mode)
        with NamedTemporaryFile(dir=cache, suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
        try:
            image.save(temporary, "PNG", compress_level=1)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return image

    return render


def write_resource(stream, data):
    offset = stream.tell()
    size = len(data)
    if size >= 2**31 or offset + size >= 2**32:
        raise ValueError("World package exceeds DBPF size limits")
    stream.write(data)
    return offset, size | 0x80000000, size


def finish_overlay(stream, entries):
    header = bytearray(96)
    header[:4] = b"DBPF"
    for offset, value in [(4, 3), (36, len(entries)), (44, 8+28*len(entries)), (60, 3), (64, 96)]:
        pack_into("<I", header, offset, value)
    stream.seek(0)
    stream.write(header)
    stream.write(pack("<II", 4, 0))
    for entry in sorted(entries):
        stream.write(pack("<7I", *entry, 0))


def decal_instances(package, records, extract):
    instances = set()
    for row, raw in extract(package, records):
        marker = pack(">IH", 0x0CE5EF58, 32)
        pos = raw.find(marker)
        if pos < 0:
            continue
        flags, count, stride = unpack_from(">HII", raw, pos+6)
        end = pos+16+12*count
        if not flags & 0x30 or flags & 0x40 or stride != 12 or end > len(raw):
            raise ValueError(f"Invalid decal reference array in {package.name}: {row['instance']:08x}")
        instances.update(instance for instance, _, _ in iter_unpack(">III", raw[pos+16:end]) if instance)
    return instances


def rw4_set(raw, sections):
    # A single RW4 resource can own multiple textures. Keep it in one set so
    # overlays from independently installed sets cannot replace one another.
    formats = {fmt for _, fmt, w, h, mips, _ in sections if eligible(fmt, w, h, mips)}
    if formats == {50}:
        return "l8"
    if len(sections) == 1 and unpack_from("<I", raw, 28)[0] == 0x04000000:
        n = sections[0][0]
        index, = unpack_from("<I", raw, 48)
        position, = unpack_from("<I", raw, index+24*n)
        if unpack_from("<I", raw, position+4)[0] & 0x1000:
            return "cubemaps"
    return "rw4"


def build_world(args, extract, package_index, load_model, upscale):
    game = args.game.resolve()
    data = game / "SimCityData"
    output = (args.output or Path("world-hd")).resolve()
    if output.is_relative_to(game):
        raise ValueError("Put the world output outside the game directory")
    if args.cache.resolve().is_relative_to(output):
        raise ValueError("Put the cache outside the world output directory")
    if output.exists():
        raise ValueError(f"Choose a new output directory: {output}")
    if any(data.glob(f"*{BACKUP_SUFFIX}")):
        raise ValueError("Uninstall the archive-order World set before building from this installation")
    packages = [p for p in sorted(data.glob("SimCity*.package")) if not p.name.startswith("SimCity_Audio_")]
    if not packages:
        raise ValueError(f"No SimCity packages under {data}")
    selected = set(args.sets or SETS)
    locations = Counter()
    slots = {}
    decals = set()
    for package in packages:
        records = []
        found = {}
        with package.open("rb") as stream:
            for resource, slot, *_ in package_index(stream, package):
                kind, group, high, instance = resource
                if kind in (RW4, RASTER):
                    if high or resource in found:
                        raise ValueError(f"Unsupported or duplicate DBPF texture key in {package}")
                    found[resource] = slot
                elif selected & {"raster", "decals"} and kind == 0x00B1B104 and group & 0xFFFF in (0xB185, 0x1651, 0x1652):
                    records.append(dict(kind=kind, group=group, instance=instance))
        slots[package] = found
        locations.update(found.keys())
        if records:
            decals.update(decal_instances(package, records, extract))

    render = renderer(args, load_model, upscale)
    stats = Counter()
    set_counts = Counter()
    entries = {name: [] for name in OVERLAYS if name in selected}
    manifest = {"overlays": {}, "archives": {}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".world-build-") as scratch:
        staged = Path(scratch) / "result"
        staged.mkdir()
        with ExitStack() as stack:
            overlays = {name: stack.enter_context((staged / OVERLAYS[name]).open("wb")) for name in entries}
            for overlay in overlays.values():
                overlay.seek(104 + 28*len(locations))
            for package in packages:
                print(f"Processing {package.name}", flush=True)
                original_hash = None
                patched_path = staged / package.name
                records = []
                for key in slots[package]:
                    kind, group, _, instance = key
                    if locations[key] > 1:
                        name = "conflicts"
                    elif kind == RASTER:
                        name = "decals" if instance in decals else "raster"
                    elif selected & {"rw4", "l8", "cubemaps"}:
                        name = None
                    else:
                        continue
                    if name is None or name in selected:
                        records.append(dict(kind=kind, group=group, instance=instance, set_name=name))
                with ExitStack() as archive:
                    for row, raw in extract(package, records):
                        kind, group, instance = row["kind"], row["group"], row["instance"]
                        key = kind, group, 0, instance
                        try:
                            sections = list(textures(RW4, raw)) if kind == RW4 else None
                            name = row["set_name"] or rw4_set(raw, sections)
                            if name not in selected:
                                continue
                            upgraded = upgrade_rw4(raw, sections, render, stats) if kind == RW4 else upgrade_raster(raw, render, stats)
                        except StructError as error:
                            raise ValueError(f"Invalid texture {instance:08x} in {package.name}") from error
                        if upgraded is None:
                            continue
                        if name != "conflicts":
                            entries[name].append((kind, group, instance, *write_resource(overlays[name], upgraded)))
                        else:
                            if original_hash is None:
                                original_hash = checksum(package)
                                copyfile(package, patched_path)
                                if checksum(patched_path) != original_hash:
                                    raise ValueError(f"Source changed while copying: {package.name}")
                                patched = archive.enter_context(patched_path.open("r+b"))
                            patched.seek(0, 2)
                            end = write_resource(patched, upgraded)
                            patched.seek(slots[package][key])
                            patched.write(pack("<IIIh", *end, 0))
                        stats["updated resources"] += 1
                        set_counts[name] += 1
                        if stats["updated resources"] % 100 == 0:
                            print(f'{stats["updated resources"]} resources', flush=True)
                if original_hash is not None:
                    manifest["archives"][package.name] = {"original": original_hash, "patched": checksum(patched_path)}
            for name, resources in entries.items():
                if resources:
                    finish_overlay(overlays[name], resources)
        for name, resources in entries.items():
            path = staged / OVERLAYS[name]
            if resources:
                manifest["overlays"][name] = checksum(path)
            else:
                path.unlink()
        if not stats["updated resources"]:
            raise ValueError("No supported textures were found in the selected World sets")
        (staged / "install.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        (staged / "summary.json").write_text(json.dumps({"sets": dict(set_counts), "textures": dict(stats)}, indent=2) + "\n", encoding="utf-8")
        staged.rename(output)
    print(f'Built {stats["updated resources"]} world resources in {output}')
