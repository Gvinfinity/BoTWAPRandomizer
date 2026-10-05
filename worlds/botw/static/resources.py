"""Read a legal extracted Wii U game; preserve endianness and Yaz0 envelopes."""
from __future__ import annotations

from pathlib import Path

from .checks import validate_resource_path


def binary_modules():
    try:
        import oead
        import rstb
    except ImportError as exc:
        raise RuntimeError("Install the patcher requirements with Python 3.12 (oead and rstb)") from exc
    return oead, rstb


def decompress(data: bytes) -> bytes:
    oead, _ = binary_modules()
    return bytes(oead.yaz0.decompress(data)) if data[:4] == b"Yaz0" else bytes(data)


def rewrap(data: bytes, original: bytes) -> bytes:
    oead, _ = binary_modules()
    return bytes(oead.yaz0.compress(data)) if original[:4] == b"Yaz0" else bytes(data)


def decode_byml(data: bytes):
    oead, _ = binary_modules()
    return oead.byml.from_binary(decompress(data))


def encode_byml(data, original: bytes) -> bytes:
    oead, _ = binary_modules()
    raw = decompress(original)
    return rewrap(bytes(oead.byml.to_binary(data, big_endian=raw[:2] == b"BY")), original)


class GameDump:
    """Update files override base files. DLC resources live under aoc/0010."""
    def __init__(self, base: str, update: str, dlc: str | None = None):
        self.base, self.update = Path(base).resolve(), Path(update).resolve()
        self.dlc = Path(dlc).resolve() if dlc else None
        for root in (self.base, self.update):
            if not root.is_dir():
                raise ValueError(f"Missing content directory: {root}")
        if not (self.update / "Actor/ActorInfo.product.sbyml").is_file():
            raise ValueError("--update must be the v208 content directory")
        if self.dlc and not (self.dlc / "0010").is_dir():
            raise ValueError("--dlc must contain the 0010 directory")

    def resolve(self, resource: str) -> Path:
        validate_resource_path(resource)
        outer = resource.split("!")[0]
        if outer.startswith("aoc/"):
            if not self.dlc:
                raise ValueError(f"DLC required for {resource}")
            roots, relative = (self.dlc,), outer.removeprefix("aoc/")
        elif outer.startswith("content/"):
            roots, relative = (self.update, self.base), outer.removeprefix("content/")
        else:
            raise ValueError("Resource must start with content/ or aoc/")
        for root in roots:
            path = (root / relative).resolve()
            if not path.is_relative_to(root):
                raise ValueError(f"Resource escapes content directory: {resource}")
            if path.is_file():
                return path
        raise FileNotFoundError(resource)

    def read(self, resource: str) -> bytes:
        oead, _ = binary_modules()
        data = self.resolve(resource).read_bytes()
        for member in resource.split("!")[1:]:
            entry = oead.Sarc(decompress(data)).get_file(member)
            if entry is None:
                raise FileNotFoundError(resource)
            data = bytes(entry.data)
        return data

    def outer_resources(self):
        resources = set()
        for prefix, roots in (("content", (self.base, self.update)),
                              ("aoc", (self.dlc,) if self.dlc else ())):
            for root in roots:
                for folder in ("Map", "Pack") if prefix == "content" else ("0010/Map", "0010/Pack"):
                    for path in (root / folder).rglob("*"):
                        if path.is_file() and path.suffix in {".smubin", ".pack"}:
                            resources.add(f"{prefix}/{path.relative_to(root).as_posix()}")
        return sorted(resources)


def map_resources(resource: str, data: bytes):
    """Recursively enumerate map BYML without unpacking files to disk."""
    oead, _ = binary_modules()
    if resource.endswith(".smubin"):
        yield resource, data
    elif decompress(data)[:4] == b"SARC":
        for entry in oead.Sarc(decompress(data)).get_files():
            if entry.name and entry.name.endswith((".smubin", ".pack")):
                yield from map_resources(f"{resource}!{entry.name}", bytes(entry.data))


def replace_members(data: bytes, replacements: dict[str, bytes]) -> bytes:
    """Rebuild only changed SARC branches and preserve every other member."""
    if "" in replacements:
        if len(replacements) != 1:
            raise ValueError("Cannot replace a container and a member simultaneously")
        return replacements[""]
    oead, _ = binary_modules()
    archive = oead.Sarc(decompress(data))
    writer = oead.SarcWriter.from_sarc(archive)
    groups = {}
    for key, payload in replacements.items():
        name, _, rest = key.partition("!")
        groups.setdefault(name, {})[rest] = payload
    for name, children in groups.items():
        entry = archive.get_file(name)
        if entry is None:
            raise FileNotFoundError(name)
        writer.files[name] = replace_members(bytes(entry.data), children)
    return rewrap(bytes(writer.write()[1]), data)
