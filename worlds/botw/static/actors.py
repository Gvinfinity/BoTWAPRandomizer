"""Create actual per-check actor packs and sorted ActorInfo metadata."""
from __future__ import annotations

import binascii

from .checks import check_actor_name
from .resources import binary_modules, decode_byml, decompress, encode_byml, rewrap

TEMPLATE_ACTOR = "Item_Ore_A"


def build_check_actors(dump, location_ids: list[int]) -> tuple[dict[str, bytes], dict[str, int]]:
    oead, _ = binary_modules()
    pack_raw = dump.read(f"content/Actor/Pack/{TEMPLATE_ACTOR}.sbactorpack")
    pack = oead.Sarc(decompress(pack_raw))
    link_path = f"Actor/ActorLink/{TEMPLATE_ACTOR}.bxml"
    link = pack.get_file(link_path)
    if link is None:
        raise ValueError("Template actor has no ActorLink")
    gparam_path = f"Actor/GeneralParamList/{TEMPLATE_ACTOR}.bgparamlist"
    gparam = pack.get_file(gparam_path)
    if gparam is None:
        raise ValueError("Template actor has no GeneralParamList")
    info_raw = dump.read("content/Actor/ActorInfo.product.sbyml")
    info = decode_byml(info_raw)
    template = next(actor for actor in info["Actors"] if actor["name"] == TEMPLATE_ACTOR)
    entries = {int(code): actor for code, actor in zip(info["Hashes"], info["Actors"])}
    if len(entries) != len(info["Actors"]):
        raise ValueError("ActorInfo contains duplicate CRCs")
    template_pack_size = len(decompress(pack_raw))
    files, resource_sizes = {}, {}
    for code in sorted(location_ids):
        name = check_actor_name(code)
        crc = binascii.crc32(name.encode())
        if crc in entries:
            raise ValueError(f"Check actor CRC collides with an existing actor: {name}")
        actor = oead.byml.from_text(oead.byml.to_text(template))
        actor["name"] = name
        actor["itemUseIconActorName"] = TEMPLATE_ACTOR
        # Never alias systemSameGroupActorName to the template: the hook must
        # receive the distinct AP name before native pouch conversion.
        actor["systemSameGroupActorName"] = ""
        actor["itemBuyingPrice"] = oead.S32(0)
        actor["itemSellingPrice"] = oead.S32(0)
        entries[crc] = actor
        writer = oead.SarcWriter.from_sarc(pack)
        new_link = f"Actor/ActorLink/{name}.bxml"
        link_data = oead.aamp.ParameterIO.from_binary(link.data)
        link_data.objects["LinkTarget"].params["GParamUser"] = oead.aamp.Parameter(name)
        link_data.objects["LinkTarget"].params["ActorNameJpn"] = oead.aamp.Parameter(f"Archipelago Item [{code:08X}]")
        writer.files[new_link] = bytes(link_data.to_binary())
        del writer.files[link_path]
        new_gparam = f"Actor/GeneralParamList/{name}.bgparamlist"
        gparam_data = oead.aamp.ParameterIO.from_binary(gparam.data)
        item_params = gparam_data.objects["Item"].params
        item_params["BuyingPrice"] = oead.aamp.Parameter(0)
        item_params["SellingPrice"] = oead.aamp.Parameter(0)
        item_params["UseIconActorName"] = oead.aamp.Parameter(oead.FixedSafeString64(TEMPLATE_ACTOR))
        writer.files[new_gparam] = bytes(gparam_data.to_binary())
        del writer.files[gparam_path]
        raw = bytes(writer.write()[1])
        files[f"content/Actor/Pack/{name}.sbactorpack"] = rewrap(raw, pack_raw)
        # Include the actor-link allocation and the renamed archive. All model,
        # AI and physics resources are shared with the vanilla template.
        resource_sizes[new_link] = len(writer.files[new_link])
        resource_sizes[new_gparam] = len(writer.files[new_gparam])
        resource_sizes[f"Actor/Pack/{name}.bactorpack"] = max(template_pack_size, len(raw))
    # BYML distinguishes signed and unsigned integer nodes. The game reads
    # ActorInfo hashes using typed getters, so preserve the source encoding:
    # values whose high bit is set use U32; all others use S32.
    info["Hashes"] = oead.byml.Array([
        oead.U32(code) if code > 0x7FFFFFFF else oead.S32(code)
        for code in sorted(entries)
    ])
    info["Actors"] = oead.byml.Array([entries[code] for code in sorted(entries)])
    files["content/Actor/ActorInfo.product.sbyml"] = encode_byml(info, info_raw)
    resource_sizes["Actor/ActorInfo.product.byml"] = len(decompress(files["content/Actor/ActorInfo.product.sbyml"]))
    return files, resource_sizes
