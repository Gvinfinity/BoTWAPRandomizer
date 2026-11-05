"""Suppress the vanilla Plateau rune rewards while preserving terminal use."""
from __future__ import annotations

import binascii
import hashlib
import json
from importlib.resources import files

from .resources import binary_modules, decode_byml, decompress, encode_byml, rewrap


def catalog():
    return json.loads(files(__package__).joinpath('runes.json').read_text())


def patch_terminal_map(data, entries):
    expected = {entry['hash_id'] for entry in entries}
    found = set()
    for obj in data.get('Objs', []):
        hash_id = int(obj.get('HashId', -1))
        if hash_id not in expected:
            continue
        if obj.get('UnitConfigName') != 'DgnObj_DownloadTerminal_A_01':
            raise ValueError('Rune terminal binding does not identify the source terminal')
        obj['UnitConfigName'] = catalog()['replacement_actor']
        found.add(hash_id)
    if found != expected:
        raise ValueError('A Plateau rune terminal is missing from its source map')


def suppress_vanilla_rune_action(raw, source_format: bytes):
    """Replace exactly one DemoGetItem AI action with the known no-op action."""
    oead, _ = binary_modules()
    ai = oead.aamp.ParameterIO.from_binary(raw)
    disabled = 0
    for program in ai.lists.values():
        for node in program.lists.values():
            definition = node.objects.get('Def')
            if definition is None:
                continue
            class_name = definition.params.get('ClassName')
            if class_name is not None and str(class_name.v) == catalog()['disabled_action']:
                definition.params['ClassName'] = oead.aamp.Parameter('DummyAction')
                disabled += 1
    if disabled != 1:
        raise ValueError(f'Expected one vanilla rune action, found {disabled}')
    output = bytes(ai.to_binary())
    return rewrap(output, source_format)


def build_rune_terminal_actor(dump, actor_info):
    """Clone the download terminal and remove its vanilla item-get action.

    The vanilla actor's DemoGetItem AI state grants the map's rune directly.
    The AP clone keeps the terminal's activation flow and visuals but makes that
    one action a no-op; the AP client remains the sole rune grant path.
    """
    oead, _ = binary_modules()
    data = catalog()
    source = data['source_actor']
    replacement = data['replacement_actor']
    original = dump.read(f'content/Actor/Pack/{source}.sbactorpack')
    if hashlib.sha256(original).hexdigest() != data['source_actor_sha256']:
        raise ValueError('Game version/rune terminal actor mismatch')
    archive = oead.Sarc(decompress(original))
    members = {item.name: item for item in archive.get_files()}
    link_path = f'Actor/ActorLink/{source}.bxml'
    ai_path = f'Actor/AIProgram/DownloadTerminal.baiprog'
    if link_path not in members or ai_path not in members:
        raise ValueError('Rune terminal source actor is incomplete')

    link = oead.aamp.ParameterIO.from_binary(members[link_path].data)
    link.objects['LinkTarget'].params['AIProgramUser'] = oead.aamp.Parameter(replacement)
    ai_source = bytes(members[ai_path].data)
    ai = suppress_vanilla_rune_action(ai_source, ai_source)

    writer = oead.SarcWriter.from_sarc(archive)
    new_link = f'Actor/ActorLink/{replacement}.bxml'
    new_ai = f'Actor/AIProgram/{replacement}.baiprog'
    writer.files[new_link] = bytes(link.to_binary())
    writer.files[new_ai] = ai
    del writer.files[link_path]
    del writer.files[ai_path]
    raw = bytes(writer.write()[1])

    # Extend the current overlay, which already contains the per-check actors.
    # Reloading vanilla metadata here erases every chest/shrine marker.
    info_raw = actor_info
    info = decode_byml(info_raw)
    actors = {int(code): actor for code, actor in zip(info['Hashes'], info['Actors'])}
    if len(actors) != len(info['Actors']):
        raise ValueError('ActorInfo contains duplicate CRCs')
    crc = binascii.crc32(replacement.encode())
    if crc in actors:
        raise ValueError('Rune terminal clone CRC collides with an existing actor')
    template = next((actor for actor in info['Actors'] if actor['name'] == source), None)
    if template is None:
        raise ValueError('Rune terminal template is absent from ActorInfo')
    clone = oead.byml.from_text(oead.byml.to_text(template))
    clone['name'] = replacement
    actors[crc] = clone
    info['Hashes'] = oead.byml.Array([
        oead.U32(code) if code > 0x7FFFFFFF else oead.S32(code) for code in sorted(actors)
    ])
    info['Actors'] = oead.byml.Array([actors[code] for code in sorted(actors)])
    return {
        f'content/Actor/Pack/{replacement}.sbactorpack': rewrap(raw, original),
        'content/Actor/ActorInfo.product.sbyml': encode_byml(info, info_raw),
    }
