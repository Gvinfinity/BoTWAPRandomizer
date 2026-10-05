import pytest
import sys
import os

# Ensure the parent directory is in the path so we can import the modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from patch_chests import patch_chest_byml
from patch_shops import patch_shop_byml

def test_patch_chests_success():
    """
    Test that chests matching the location_map are successfully patched
    to drop a unique marker encoding the correct AP Location ID.
    """
    mock_byml = {
        'Objs': [
            {
                'UnitConfigName': 'TBox_Field_Iron',
                'HashId': 123456789,
                '!Parameters': {
                    'DropActor': 'Weapon_Sword_001',
                    'DropTable': 'Normal'
                }
            },
            {
                'UnitConfigName': 'Enemy_Bokoblin_01',
                'HashId': 987654321,
                '!Parameters': {}
            }
        ]
    }
    
    # We want to patch the chest with HashId 123456789 to represent AP Location 0x5001
    location_map = {123456789: 0x5001}
    modified = patch_chest_byml(mock_byml, location_map)
    
    assert modified is True, "The BYML should have been modified."
    
    # Verify the chest was patched (Vanilla Isolation Metric)
    chest_actor = mock_byml['Objs'][0]
    assert chest_actor['!Parameters']['DropActor'] == 'AP_Check_00005001'
    assert 'AP_LocationID' not in chest_actor['!Parameters']
    assert 'DropTable' not in chest_actor['!Parameters']
    
    # Verify the enemy was NOT patched
    enemy_actor = mock_byml['Objs'][1]
    assert enemy_actor['UnitConfigName'] == 'Enemy_Bokoblin_01'
    assert 'DropActor' not in enemy_actor['!Parameters']

def test_patch_chests_no_match():
    """
    Test that chests NOT in the location map are ignored.
    """
    mock_byml = {
        'Objs': [
            {
                'UnitConfigName': 'TBox_Field_Iron',
                'HashId': 111111111,
                '!Parameters': {
                    'DropActor': 'Weapon_Sword_001'
                }
            }
        ]
    }
    
    # The map doesn't contain this chest's hash
    location_map = {}
    modified = patch_chest_byml(mock_byml, location_map)
    
    assert modified is False, "The BYML should NOT have been modified."
    assert mock_byml['Objs'][0]['!Parameters']['DropActor'] == 'Weapon_Sword_001'


def test_missing_mapped_chest_fails():
    with pytest.raises(ValueError, match='absent'):
        patch_chest_byml({'Objs': []}, {999999999: 0x5001})


def test_identity_roundtrip_and_malformed_names():
    from botw_static.checks import check_actor_name, location_id_from_actor
    assert location_id_from_actor(check_actor_name(0xB1234567)) == 0xB1234567
    for name in ['Item_Ore_A', 'AP_Check_b1234567', 'AP_Check_00000000', 'AP_Check_B1234567_extra']:
        assert location_id_from_actor(name) is None


def test_nested_sarc_roundtrip_preserves_untracked_resources():
    oead = pytest.importorskip('oead')
    from botw_static.resources import replace_members
    inner = oead.SarcWriter(oead.Endianness.Big)
    inner.files['Map/test.smubin'] = b'original map'
    inner.files['untouched.bin'] = b'keep me'
    outer = oead.SarcWriter(oead.Endianness.Big)
    outer.files['inner.pack'] = inner.write()[1]
    result = replace_members(bytes(outer.write()[1]), {'inner.pack!Map/test.smubin': b'changed map'})
    parsed = oead.Sarc(bytes(oead.Sarc(result).get_file('inner.pack').data))
    assert bytes(parsed.get_file('untouched.bin').data) == b'keep me'
    assert bytes(parsed.get_file('Map/test.smubin').data) == b'changed map'

def test_patch_shops_success():
    """
    Test that shop items are successfully replaced with dummy checks.
    """
    mock_bshop = {
        'Items': [
            {'ItemName': 'Item_Fruit_A', 'Price': 10},
            {'ItemName': 'Item_Material_01', 'Price': 20}
        ]
    }
    
    shop_map = {0: 0x6001, 1: 0x6002}
    modified = patch_shop_byml(mock_bshop, shop_map)
    
    assert modified is True
    
    # Verify shop contents
    assert mock_bshop['Items'][0]['ItemName'] == 'AP_Dummy_Check'
    assert mock_bshop['Items'][0]['AP_LocationID'] == 0x6001
    assert mock_bshop['Items'][0]['Price'] == 10  # Price should remain intact
    
    assert mock_bshop['Items'][1]['ItemName'] == 'AP_Dummy_Check'
    assert mock_bshop['Items'][1]['AP_LocationID'] == 0x6002
