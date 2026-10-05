"""Fresh-save defaults preserve chest checks and unrelated vanilla progress."""
import pytest
from src.patcher.core import ROOT
from botw_static.starting import starting_state, patch_starting_gamedata


def documents():
    oead = pytest.importorskip('oead')
    state = starting_state(True)
    rows = lambda names: oead.byml.Array([oead.byml.Hash({'DataName': name, 'InitValue': oead.S32(0),
                                                         'IsSave': True, 'HashValue': oead.S32(42)}) for name in names])
    flags = oead.byml.Hash({'bool_data': rows(list(state['bool_flags']) + ['IsGet_PlayerStole2',
                                                                            'IsGet_PlayerStole2_Vagrant',
                                                                            'Clear_Dungeon009',
                                                                            'IsGet_Obj_Magnetglove'])})
    integers = oead.byml.Hash({'s32_data': rows(state['s32_flags'])})
    def array(name, default):
        values = oead.byml.Array([default for _ in range(420)])
        return oead.byml.Hash({'DataName': name, 'InitValue': oead.byml.Array([oead.byml.Hash({'Values': values})])})
    pouch = oead.byml.Hash({'string64_array_data': oead.byml.Array([array('PorchItem', '')]),
                           's32_array_data': oead.byml.Array([array('PorchItem_Value1', oead.S32(0))]),
                           'bool_array_data': oead.byml.Array([array('PorchItem_EquipFlag', oead.S32(0))])})
    return {'flags.bgdata': flags, 'integers.bgdata': integers, 'pouch.bgdata': pouch}


def entries(docs):
    return {row['DataName']: row for doc in docs.values() for rows in doc.values() for row in rows}


def test_skip_plateau_seeds_map_and_tutorial_state_without_paraglider():
    docs = documents()
    assert patch_starting_gamedata(docs, starting_state(True)) == set(docs)
    flags = entries(docs)
    for flag in starting_state(True)['bool_flags']:
        assert int(flags[flag]['InitValue']) == 1
        assert int(flags[flag]['HashValue']) == 42
        assert flags[flag]['IsSave'] is True
    assert int(flags['Location_MapTower07']['InitValue']) == 1
    assert int(flags['IsGet_PlayerStole2']['InitValue']) == 0
    assert int(flags['IsGet_PlayerStole2_Vagrant']['InitValue']) == 0
    assert int(flags['MaxHartValue']['InitValue']) == 12
    assert int(flags['Clear_Dungeon009']['InitValue']) == 0
    assert int(flags['IsGet_Obj_Magnetglove']['InitValue']) == 0
    names = flags['PorchItem']['InitValue'][0]['Values']
    values = flags['PorchItem_Value1']['InitValue'][0]['Values']
    assert list(names[:2]) == ['Obj_DRStone_Get', '']
    assert [int(value) for value in values[:2]] == [1, 0]
    patch_starting_gamedata(docs, starting_state(True))
    assert sum(str(name) == 'PlayerStole2' for name in names) == 0


def test_vanilla_profile_does_not_grant_paraglider_or_complete_tutorial():
    docs = documents()
    assert patch_starting_gamedata(docs, starting_state(False)) == {'integers.bgdata'}
    flags = entries(docs)
    assert int(flags['IsGet_PlayerStole2']['InitValue']) == 0
    assert int(flags['FirstTower_Finish']['InitValue']) == 0
    assert all(str(name) == '' for name in flags['PorchItem']['InitValue'][0]['Values'])


def test_initial_pouch_preserves_existing_unrelated_items():
    docs = documents(); flags = entries(docs)
    flags['PorchItem']['InitValue'][0]['Values'][0] = 'Item_Fruit_A'
    oead = pytest.importorskip('oead')
    flags['PorchItem_Value1']['InitValue'][0]['Values'][0] = oead.S32(2)
    patch_starting_gamedata(docs, starting_state(True))
    assert list(flags['PorchItem']['InitValue'][0]['Values'][:3]) == ['Item_Fruit_A', 'Obj_DRStone_Get', 'PlayerStole2']
    assert int(flags['PorchItem_Value1']['InitValue'][0]['Values'][0]) == 2


def test_missing_initial_flag_and_wrong_array_shape_are_rejected():
    docs = documents()
    docs['flags.bgdata']['bool_data'].pop(0)
    with pytest.raises(ValueError, match='Missing starting-state'): patch_starting_gamedata(docs, starting_state(True))
    docs = documents(); flags = entries(docs)
    flags['PorchItem']['InitValue'][0]['Values'].pop()
    with pytest.raises(ValueError, match='capacity'): patch_starting_gamedata(docs, starting_state(True))


def test_starting_profile_is_bound_into_seed_identity():
    from botw_static.protocol import seed_fingerprint
    ids = [0xB1234567]
    assert seed_fingerprint('same', 1, ids, starting_state(True)) != seed_fingerprint('same', 1, ids, starting_state(False))


def test_starting_profile_rejects_arbitrary_progression_grants():
    state = starting_state(True); state['bool_flags']['Clear_Dungeon009'] = True
    with pytest.raises(ValueError, match='Unsupported fresh-save'):
        patch_starting_gamedata(documents(), state)
