"""Fixture editor tests; no copyrighted save data needed."""
import importlib.util
from pathlib import Path
import struct
import zlib
import pytest

spec = importlib.util.spec_from_file_location('cemu_runner', Path(__file__).with_name('run.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
from items import world_reference


def fixture():
    data = bytearray(1027208)
    struct.pack_into('>I', data, 0, 0x471b)
    names = [('PlayerSavePos', 3), ('PlayerSavePosAngleYDegree', 1),
             ('MainField_TBox_Field_Stone_123', 1), ('PlayerSavePosMapType', 8),
             ('PlayerSavePosMapName', 8)]
    at = 12
    for name, count in names:
        for _ in range(count):
            struct.pack_into('>II', data, at, zlib.crc32(name.encode()), 1)
            at += 8
    return data, at


def test_editor_preserves_source_hashes_and_unrelated_bytes():
    source, end = fixture()
    original = bytes(source)
    output = runner.patch_save(source, [1, 2, 3], 180, 123)
    assert bytes(source) == original
    assert output[:12] == original[:12]
    assert output[end:] == original[end:]
    for at in range(12, end, 8):
        assert output[at:at+4] == original[at:at+4]
    assert [struct.unpack_from('>f', output, at)[0] for at in (16,24,32)] == [1,2,3]
    assert struct.unpack_from('>I', output, 48)[0] == 0


def test_missing_chest_flag_fails_instead_of_creating_unloadable_save():
    source, _ = fixture()
    with pytest.raises(ValueError, match='required field'):
        runner.patch_save(source, [1, 2, 3], 180, 456)


def test_wrong_version_rejected():
    source, _ = fixture()
    source[:4] = b'\x00\x00\x47\x1e'
    with pytest.raises(ValueError, match='v208'):
        runner.patch_save(source, [1,2,3], 180, 123)


def test_item_modes_cover_production_items_and_categories():
    full = runner.scenarios('full')
    partial = runner.scenarios('partial')
    simplified = runner.scenarios('simplified')
    reference = world_reference()
    assert {case['name'] for case in full} == set(reference.item_data)
    assert len(simplified) == 1
    assert {case['category'] for case in partial} == {case['category'] for case in full}
    for category in {case['category'] for case in partial}:
        assert len({case['item'] for case in partial if case['category'] == category}) == 1
    for name, profile in reference.native_grants.items():
        assert len([case for case in full if case['name'] == name]) == len(profile['Tiers'])
    with pytest.raises(ValueError, match='Unknown test mode'):
        runner.scenarios('unknown')


def test_delivery_save_reset_clears_pouch_and_flags_without_changing_hashes():
    reference = world_reference()
    names = {flag['Name'] for profile in reference.native_grants.values()
             for tier in profile['Tiers'] for flag in tier['Writes']}
    from importlib import import_module
    names.update(e['watch_flag'] for e in import_module(reference.__package__ + '.static.combat').catalog()['locations'])
    names.update(e['watch_flag'] for e in reference.load_completions() if 'watch_flag' in e)
    names.discard('GreatFairy_ArmorRank')  # transient, absent from real saves
    names.update(['MaxHartValue', 'WeaponPorchStockNum', 'BowPorchStockNum', 'ShieldPorchStockNum',
                  'CurrentRupee', 'IsGet_PlayerStole2', 'StaminaMax', 'StaminaCurrentMax',
                  'PorchItem', 'PorchItem_Value1', 'PorchItem_EquipFlag'])
    names.update(f'RevivalGreatFairy{i}' for i in range(1, 5))
    source = bytearray(1027208)
    struct.pack_into('>I', source, 0, 0x471b)
    at = 12; positions = {}
    for name in sorted(names):
        positions[name] = at + 4
        struct.pack_into('>II', source, at, zlib.crc32(name.encode()), 123)
        at += 8
    # Multiple records for string/array data must all be reset.
    struct.pack_into('>II', source, at, zlib.crc32(b'PorchItem'), 456)
    end = at + 8
    original = bytes(source)
    reset = runner.reset_delivery_state(source)
    assert bytes(source) == original
    assert reset[:12] == source[:12] and reset[end:] == source[end:]
    assert all(reset[i:i+4] == source[i:i+4] for i in range(12, end, 8))
    assert struct.unpack_from('>I', reset, positions['MaxHartValue'])[0] == 12
    assert struct.unpack_from('>f', reset, positions['StaminaMax'])[0] == 1000
    assert struct.unpack_from('>I', reset, positions['PorchItem'])[0] == 0
    assert struct.unpack_from('>I', reset, at + 4)[0] == 0
    assert struct.unpack_from('>I', reset, positions['IsGet_Obj_DLC_HeroSoul_Rito'])[0] == 0
    struct.pack_into('>I', source, positions['MaxHartValue'] - 4, 0)
    with pytest.raises(ValueError, match='MaxHartValue'):
        runner.reset_delivery_state(source)
