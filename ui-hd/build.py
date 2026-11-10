import argparse
from collections import defaultdict
from hashlib import file_digest, sha256
from io import BytesIO
import json
from pathlib import Path
from struct import pack, pack_into, unpack
from tempfile import NamedTemporaryFile
from zipfile import ZipFile

from PIL import Image, ImageChops

from refpack import refpack
from world import SETS

ARCHIVE_SHA256 = "27749962bc934779f867730cdb10617e3d7475313f920a7a966c56b75dbdbeda"
MODEL_FILE = "4x_IllustrationJaNai_V3detail_HAT_L_28k_bf16.safetensors"
PACKAGE_NAME = "000_Codex_UI_IllustrationJaNai.package"


def package_index(stream, package):
    header = stream.read(96)
    if header[:8] != b"DBPF\x03\0\0\0":
        raise ValueError(f"Unexpected DBPF version: {package}")
    count, = unpack("<I", header[36:40])
    offset, = unpack("<I", header[64:68])
    stream.seek(offset)
    flags, = unpack("<I", stream.read(4))
    if not 4 <= flags <= 7:
        raise ValueError(f"Unexpected index flags: {package}")
    shared = [unpack("<I", stream.read(4))[0] if flags & (1 << j) else None for j in range(3)]
    for _ in range(count):
        kind, group, high = [unpack("<I", stream.read(4))[0] if x is None else x for x in shared]
        instance, = unpack("<I", stream.read(4))
        slot = stream.tell()
        pos, stored, size, compression, _ = unpack("<IIIhH", stream.read(16))
        yield (kind, group, high, instance), slot, pos, stored & 0x7fffffff, size, compression


def extract(package, records=None, kinds=()):
    selected = None if records is None else {(r["kind"], r["group"], r["instance"]): r for r in records}
    with package.open("rb") as stream:
        matches = []
        for (kind, group, _, instance), _, pos, stored, size, compression in package_index(stream, package):
            if selected is None:
                row = dict(kind=kind, group=group, instance=instance) if kind in kinds else None
            else:
                row = selected.get((kind, group, instance))
            if row is not None:
                matches.append((row, pos, stored, size, compression))
        if selected is not None and len(matches) != len(selected):
            raise ValueError(f"Missing or duplicate resources in {package}")
        for row, pos, stored, size, compression in matches:
            stream.seek(pos)
            raw = stream.read(stored)
            if compression == -1:
                raw = refpack(raw, size)
            elif compression != 0:
                raise ValueError(f"Unsupported compression: {compression}")
            if len(raw) != size:
                raise ValueError("Unexpected decoded length")
            yield row, raw


def model_image(model, tensor, size, *, block=256, pad=32):
    import torch

    _, _, height, width = tensor.shape
    scale = model.scale
    output = torch.empty((3, height * scale, width * scale), dtype=torch.uint8, device="cpu")
    with torch.inference_mode():
        for y in range(0, height, block):
            for x in range(0, width, block):
                right, bottom = min(x + block, width), min(y + block, height)
                left0, top0 = max(0, x - pad), max(0, y - pad)
                patch = tensor[:, :, top0:min(bottom+pad, height), left0:min(right+pad, width)]
                result = model(patch.contiguous().to(model.device))[0]
                dx, dy = (x-left0)*scale, (y-top0)*scale
                result = result[:, dy:dy+(bottom-y)*scale, dx:dx+(right-x)*scale]
                output[:, y*scale:bottom*scale, x*scale:right*scale] = result.clamp(0, 1).mul(255).round().byte().cpu()
    raw = output.permute(1, 2, 0).contiguous().numpy().tobytes()
    image = Image.frombytes("RGB", (width*scale, height*scale), raw)
    return image if image.size == size else image.resize(size, Image.Resampling.LANCZOS)


def load_model(archive_path, device):
    from safetensors.torch import load
    from spandrel import ModelLoader
    import torch

    with archive_path.open("rb") as archive_file:
        if file_digest(archive_file, "sha256").hexdigest() != ARCHIVE_SHA256:
            raise ValueError(f"Unexpected model archive checksum: {archive_path}")
    with ZipFile(archive_path) as archive:
        weights = load(archive.read(MODEL_FILE))
    model = ModelLoader(device="cpu").load_from_state_dict(weights).eval()
    return model.to(device=device, dtype=torch.float32)


def upscale(model, source, size, alpha):
    import torch

    rgb = source.convert("RGB")
    tensor = torch.frombuffer(bytearray(rgb.tobytes()), dtype=torch.uint8)
    tensor = tensor.reshape(source.height, source.width, 3).permute(2, 0, 1).unsqueeze(0).float() / 255
    result = model_image(model, tensor, size, block=96, pad=16)
    result.putalpha(alpha)
    return result


def build(args):
    import torch

    data_dir = args.game / "SimCityData"
    if not data_dir.is_dir():
        raise ValueError(f"Point --game at the installation folder containing SimCityData: {args.game}")
    rows = json.loads(Path(__file__).with_name("ui-manifest.json").read_text(encoding="utf-8"))
    if args.match:
        rows = [row for row in rows if args.match.casefold() in row["name"].casefold()]
        if not rows:
            raise ValueError(f"No matching textures: {args.match}")
    # The two logo resources share an ID. An overlay can only supply one version.
    groups = defaultdict(list)
    ids = set()
    for row in rows:
        key = row["kind"], row["group"], row["instance"]
        if row["name"] == "EP1_FEHub_LogoHexPattern.png" and row["package"] == "SimCity_App.package":
            continue
        if key in ids:
            raise ValueError(f"Duplicate resource ID: {row}")
        ids.add(key)
        groups[row["package"]].append(row)

    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA unavailable. Install a CUDA build of PyTorch or use --device cpu.")
    torch.set_num_threads(min(torch.get_num_threads(), 4))
    model = None
    count = len(ids)
    index_size = 8 + 28 * count
    header = bytearray(96)
    header[:4] = b"DBPF"
    for offset, value in [(4, 3), (36, count), (44, index_size), (60, 3), (64, 96)]:
        pack_into("<I", header, offset, value)

    destination = args.output.resolve()
    if destination.is_relative_to(args.game.resolve()):
        raise ValueError("Build the package outside the game directory, then install it after closing the game.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    index = []
    with NamedTemporaryFile(dir=destination.parent, suffix=".tmp", delete=False) as output:
        temporary = Path(output.name)
    try:
        with temporary.open("wb") as output:
            output.write(header)
            output.seek(len(header) + index_size)
            for package, records in groups.items():
                for row, raw in extract(data_dir / package, records):
                    key = row["kind"], row["group"], row["instance"]
                    with Image.open(BytesIO(raw)) as original:
                        source = original.convert("RGBA")
                    size = source.width * 2, source.height * 2
                    alpha = source.getchannel("A").resize(size, Image.Resampling.LANCZOS)
                    cache = args.cache / sha256(raw).hexdigest()[:24] / "illustration.webp"
                    if cache.is_file():
                        with Image.open(cache) as image:
                            result = image.convert("RGBA")
                        if result.size != size or ImageChops.difference(result.getchannel("A"), alpha).getbbox():
                            raise ValueError(f"Invalid cached texture. Delete this file and retry: {cache}")
                    else:
                        if model is None:
                            print(f"Loading IllustrationJaNai HAT-L on {device}", flush=True)
                            model = load_model(args.weights, device)
                        result = upscale(model, source, size, alpha)
                        cache.parent.mkdir(parents=True, exist_ok=True)
                        with NamedTemporaryFile(dir=cache.parent, suffix=".tmp", delete=False) as file:
                            staged_cache = Path(file.name)
                        try:
                            result.save(staged_cache, format="WEBP", lossless=True, method=1)
                            staged_cache.replace(cache)
                        finally:
                            staged_cache.unlink(missing_ok=True)

                    encoded = BytesIO()
                    if key[0] == 0x2F7D0004:
                        result.save(encoded, "PNG", compress_level=3)
                    elif key[0] == 0x3F8662EA and alpha.getextrema() == (255, 255):
                        result.convert("RGB").save(encoded, "JPEG", quality=96, subsampling=0)
                    else:
                        raise ValueError(f"Unsupported image resource: {row['name']}")
                    data = encoded.getbuffer()
                    index.append((*key, output.tell(), len(data) | 0x80000000, len(data), 0))
                    output.write(data)
                    if len(index) % 100 == 0:
                        print(f"{len(index)}/{count} resources", flush=True)
            if len(index) != count:
                raise ValueError(f"Expected {count} resources, received {len(index)}")
            output.seek(len(header))
            output.write(pack("<II", 4, 0))
            for entry in sorted(index):
                output.write(pack("<7I", *entry))
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Built {count} overrides: {destination}")


def main():
    parser = argparse.ArgumentParser(description="Prepare separate SimCity (2013) UI and world texture upgrades.")
    parser.add_argument("mode", nargs="?", choices=("ui", "world"), default="ui")
    parser.add_argument("--game", type=Path, required=True, help="installation folder containing SimCityData")
    parser.add_argument("--weights", type=Path, default=Path("IllustrationJaNai_V3detail.zip"))
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--cache", type=Path, default=Path(".illustration-cache"))
    parser.add_argument("--output", type=Path, help="UI package file or world output directory")
    parser.add_argument("--match", help="build a test package for filenames containing this text")
    parser.add_argument("--sets", nargs="+", choices=SETS, help="World sets to build (default: all)")
    args = parser.parse_args()
    if args.mode == "world":
        if args.match:
            parser.error("--match is only supported in ui mode")
        from world import build_world

        try:
            build_world(args, extract, package_index, load_model, upscale)
        except (OSError, ValueError, RuntimeError) as error:
            parser.exit(1, f"World build failed: {error}\n")
        return
    if args.sets:
        parser.error("--sets is only supported in world mode")
    args.output = args.output or Path(PACKAGE_NAME)
    if args.match and args.output.name == PACKAGE_NAME:
        parser.error("--match requires a separate --output filename")
    try:
        build(args)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Build failed: {error}\n")


if __name__ == "__main__":
    main()
