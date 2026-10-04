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
    to drop AP_Dummy_Check and are assigned the correct AP Location ID.
    """
    mock_byml = {
        'Actors': [
            {
                'Gyml': 'TBox_Field_Iron',
                'HashId': 123456789,
                '!Parameters': {
                    'DropActor': 'Weapon_Sword_001'
                }
            },
            {
                'Gyml': 'Enemy_Bokoblin_01',
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
    chest_actor = mock_byml['Actors'][0]
    assert chest_actor['!Parameters']['DropActor'] == 'AP_Dummy_Check'
    assert chest_actor['!Parameters']['AP_LocationID'] == 0x5001
    
    # Verify the enemy was NOT patched
    enemy_actor = mock_byml['Actors'][1]
    assert enemy_actor['Gyml'] == 'Enemy_Bokoblin_01'
    assert 'DropActor' not in enemy_actor['!Parameters']

def test_patch_chests_no_match():
    """
    Test that chests NOT in the location map are ignored.
    """
    mock_byml = {
        'Actors': [
            {
                'Gyml': 'TBox_Field_Iron',
                'HashId': 111111111,
                '!Parameters': {
                    'DropActor': 'Weapon_Sword_001'
                }
            }
        ]
    }
    
    # The map doesn't contain this chest's hash
    location_map = {999999999: 0x5001}
    modified = patch_chest_byml(mock_byml, location_map)
    
    assert modified is False, "The BYML should NOT have been modified."
    assert mock_byml['Actors'][0]['!Parameters']['DropActor'] == 'Weapon_Sword_001'

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
