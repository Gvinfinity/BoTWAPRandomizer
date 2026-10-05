"""Grow vanilla allocation budgets without inventing archive allocations."""
import re

from .resources import binary_modules, decompress


def rstb_name(resource: str) -> str:
    # Archive members inherit the mount of their outer archive. Cemu's overlay
    # uses lower-case aoc; the game's resource table uses upper-case Aoc.
    dlc = resource.startswith("aoc/0010/")
    name = resource.split("!")[-1]
    for prefix in ("content/", "aoc/0010/"):
        name = name.removeprefix(prefix)
    parent, _, basename = name.rpartition("/")
    stem, dot, suffix = basename.rpartition(".")
    if suffix.startswith("s"):
        basename = stem + dot + suffix[1:]
    name = f"{parent}/{basename}" if parent else basename
    return "Aoc/0010/" + name if dlc else name


def update_resource_sizes(table, dump, files: dict[str, bytes]) -> None:
    """Retain parse allowances and zero/absent entries; grow changed resources.

    These edits preserve resource structure (map drops, flags, actor templates,
    message labels). Reserve twice the aligned serialized growth on top of the
    vanilla budget, rather than multiplying the entire original resource size.
    Compare every changed nested member with its source, including DLC members.
    """
    oead, _ = binary_modules()
    budgets = {}

    def visit(path, data, original, template_path):
        if data == original and path == template_path:
            return
        raw, source = decompress(data), decompress(original)
        name, template = rstb_name(path), rstb_name(template_path)
        budget = table.get_size(template)
        if budget:
            growth = max(0, ((len(raw) + 31) & ~31) - ((len(source) + 31) & ~31))
            budgets[name] = max(budgets.get(name, 0), budget + 2 * growth)
        # Archives absent from the vanilla RSTB use the engine's normal sizing
        # path. Adding a guessed budget here can exhaust the resource heap.
        if raw[:4] == b"SARC":
            source_archive = oead.Sarc(source)
            for entry in oead.Sarc(raw).get_files():
                if entry.name is None:
                    continue
                source_name = re.sub(r"AP_Check_[0-9A-F]{8}", "Item_Ore_A", entry.name)
                old = source_archive.get_file(source_name)
                if old is None:
                    raise ValueError(f"No allocation template for {path}!{entry.name}")
                visit(f"{path}!{entry.name}", bytes(entry.data), bytes(old.data),
                      f"{template_path}!{source_name}")

    for path, data in sorted(files.items()):
        template = re.sub(r"AP_Check_[0-9A-F]{8}", "Item_Ore_A", path)
        visit(path, data, dump.read(template), template)
    # Apply after traversal: shared resources must use the original budget,
    # never compound another language/archive's growth.
    for name, budget in budgets.items():
        table.set_size(name, budget)
