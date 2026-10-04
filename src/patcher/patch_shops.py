try:
    import roead
except ImportError:
    roead = None

def patch_shop_byml(byml_data: dict, shop_map: dict) -> bool:
    """
    Modifies .bshop BYML data. Returns True if modified.
    Replaces items sold in stores with AP_Dummy_Check.
    """
    modified = False
    
    # Standard BotW shop structure usually contains 'Items' or 'ItemNames'
    if 'Items' in byml_data:
        for i, item in enumerate(byml_data['Items']):
            item_name = item.get('ItemName', '')
            
            # Optionally filter out arrows if the user wants them vanilla, 
            # but usually we replace progression checks.
            item['ItemName'] = 'AP_Dummy_Check'
            
            # Map the specific shop slot to an AP Location ID
            # In a real setup, shop_map would key off the original item or shop ID
            loc_id = shop_map.get(i, 0x6000 + i)
            item['AP_LocationID'] = loc_id
            modified = True
            
    return modified

def process_bshop_file(filepath: str, shop_map: dict):
    if not roead:
        raise ImportError("roead is required to process binary byml files.")
        
    with open(filepath, 'rb') as f:
        byml_data = roead.byml.from_binary(f.read())
        
    if patch_shop_byml(byml_data, shop_map):
        with open(filepath, 'wb') as f:
            f.write(roead.byml.to_binary(byml_data))
