"""Bundle the core hook with a seed-bound check table in the static pack."""
from importlib.resources import files
from pathlib import Path

from .protocol import PROTOCOL, seed_fingerprint
from .checks import check_actor_name


def mailbox_assembly(location_ids=(), fingerprint="0" * 32) -> str:
    p = PROTOCOL
    ids = sorted(location_ids)
    for value in ids:
        check_actor_name(value)
    if len(fingerprint) != 32 or any(c not in "0123456789abcdef" for c in fingerprint):
        raise ValueError("Invalid seed fingerprint")
    if len(ids) > p["max_locations"] or len(set(ids)) != len(ids):
        raise ValueError("Invalid seed location table")
    words = [0x41504D42, 0x424F5457] + [0] * 6
    words += [0] * ((p["extension_offset"] - 32) // 4)
    words += [0x41505632, p["version"], sum(p["capabilities"].values()), int(bool(ids)), len(ids), 0, 0, 0]
    words += [int(fingerprint[index:index + 8], 16) for index in range(0, 32, 8)]
    for index in range(p["max_locations"]):
        words += [ids[index] if index < len(ids) else 0, 0]
    assert len(words) * 4 == p["mailbox_size"]
    return "_AP_Mailbox_Base:\n" + "\n".join(
        ".int " + ", ".join(f"0x{word:08X}" for word in words[index:index + 16])
        for index in range(0, len(words), 16)) + "\n"


def build_seed_hook(plan):
    template_path = Path(__file__).resolve().parents[3] / "src/hook/patch_Archipelago.asm"
    if template_path.is_file():
        template = template_path.read_text()
    else:
        template = files(__package__).joinpath("hook_template.asm").read_text()
    fingerprint = seed_fingerprint(plan["seed"], plan["player"], [entry["id"] for entry in plan["locations"]],
                                   plan.get("starting_state"))
    if plan.get("slot_data", {}).get("seed_fingerprint") != fingerprint:
        raise ValueError("Patch/slot seed fingerprint mismatch; regenerate this seed")
    begin, end = template.index("_AP_Mailbox_Base:"), template.index("_AP_Is_Injecting:")
    return (template[:begin] + mailbox_assembly([entry["id"] for entry in plan["locations"]], fingerprint)
            + template[end:]).encode()
