import roead

def patch_bshop_file(filepath: str, shop_map: dict):
    """
    Replaces items sold in stores with AP_Dummy_Check.
    """
    with open(filepath, 'rb') as f:
        byml_data = roead.byml.from_binary(f.read())
    
    # Overwrite shop entries
    # ...

    with open(filepath, 'wb') as f:
        f.write(roead.byml.to_binary(byml_data))
