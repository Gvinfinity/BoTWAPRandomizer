import pytest

from src.patcher.core import ROOT  # initializes the standalone botw_static package
from botw_static.runes import catalog, patch_terminal_map, suppress_vanilla_rune_action


def test_plateau_rune_terminal_catalog_is_complete_and_bound_to_its_item():
    entries = catalog()['locations']
    assert {entry['dungeon']: entry['item'] for entry in entries} == {
        'Dungeon009': 'Progressive Stasis',
        'Dungeon038': 'Magnesis',
        'Dungeon041': 'Progressive Remote Bomb',
        'Dungeon065': 'Cryonis',
    }
    assert all(entry['map_sha256'] and entry['hash_id'] for entry in entries)


def test_rune_terminal_map_replacement_is_scoped_to_the_bound_actor():
    entry = catalog()['locations'][0]
    objects = [{'HashId': entry['hash_id'], 'UnitConfigName': entry['actor']}]
    patch_terminal_map({'Objs': objects}, [entry])
    assert objects[0]['UnitConfigName'] == catalog()['replacement_actor']

    with pytest.raises(ValueError, match='missing'):
        patch_terminal_map({'Objs': []}, [entry])
    with pytest.raises(ValueError, match='source terminal'):
        patch_terminal_map({'Objs': [{'HashId': entry['hash_id'], 'UnitConfigName': 'TBox_Field_Stone'}]}, [entry])


def test_vanilla_rune_get_action_becomes_the_known_noop():
    import oead

    ai = oead.aamp.ParameterIO()
    program = oead.aamp.ParameterList()
    node = oead.aamp.ParameterList()
    definition = oead.aamp.ParameterObject()
    definition.params['ClassName'] = oead.aamp.Parameter('DemoGetItem')
    node.objects['Def'] = definition
    program.lists['RuneReward'] = node
    ai.lists['AS'] = program
    raw = bytes(ai.to_binary())

    patched = oead.aamp.ParameterIO.from_binary(suppress_vanilla_rune_action(raw, raw))
    action = patched.lists['AS'].lists['RuneReward'].objects['Def'].params['ClassName']
    assert str(action.v) == 'DummyAction'


def test_rune_actor_preserves_check_metadata_from_previous_patch(monkeypatch):
    import binascii
    import hashlib
    import oead
    import botw_static.runes as runes
    from botw_static.resources import decode_byml

    source, replacement = 'DownloadTerminal', 'AP_RuneTerminal'
    link = oead.aamp.ParameterIO()
    link.objects['LinkTarget'] = oead.aamp.ParameterObject()
    writer = oead.SarcWriter(endian=oead.Endianness.Big)
    writer.files[f'Actor/ActorLink/{source}.bxml'] = bytes(link.to_binary())
    writer.files['Actor/AIProgram/DownloadTerminal.baiprog'] = b'AI fixture'
    pack = bytes(writer.write()[1])
    monkeypatch.setattr(runes, 'catalog', lambda: dict(
        source_actor=source, replacement_actor=replacement,
        source_actor_sha256=hashlib.sha256(pack).hexdigest()))
    monkeypatch.setattr(runes, 'suppress_vanilla_rune_action', lambda raw, original: raw)
    marker = 'AP_Check_B0013ACB'
    info = oead.byml.from_text('Actors: [{name: DownloadTerminal}, {name: AP_Check_B0013ACB}]\nHashes: [1, 2]')
    raw = bytes(oead.byml.to_binary(info, big_endian=True))

    class Dump:
        def read(self, path):
            assert path == f'content/Actor/Pack/{source}.sbactorpack'
            return pack

    result = runes.build_rune_terminal_actor(Dump(), raw)
    updated = decode_byml(result['content/Actor/ActorInfo.product.sbyml'])
    assert {str(actor['name']) for actor in updated['Actors']} == {source, replacement, marker}
    assert binascii.crc32(replacement.encode()) in {int(value) for value in updated['Hashes']}
