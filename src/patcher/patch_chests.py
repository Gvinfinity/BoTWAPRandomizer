# If roead is not installed natively, we handle dicts directly.
# In a real environment, roead.byml is used for serialization.
try:
    import roead
except ImportError:
    roead = None

def patch_chest_byml(byml_data: dict, location_map: dict) -> bool:
    """
    Modifies parsed BYML data. Returns True if any chests were patched.
    Replaces DropActor with AP_Dummy_Check for chests matching the location_map.
    """
    modified = False
    if 'Actors' in byml_data:
        for actor in byml_data['Actors']:
            gyml = actor.get('Gyml', '')
            # Identify Treasure Boxes
            if 'TBox' in gyml:
                hash_id = actor.get('HashId')
                
                # If location_map is empty (test mode) or hash_id is mapped to an AP location
                if not location_map or hash_id in location_map:
                    if '!Parameters' not in actor:
                        actor['!Parameters'] = {}
                    
                    # Prevent vanilla items from leaking
                    actor['!Parameters']['DropActor'] = 'AP_Dummy_Check'
                    
                    # Embed the AP Location ID directly into the chest's parameters
                    # The C++ Hook will read this when the actor spawns.
                    loc_id = location_map.get(hash_id, 0x5000) if location_map else 0x5000
                    actor['!Parameters']['AP_LocationID'] = loc_id
                    modified = True
                    
    return modified

def process_bdrop_file(filepath: str, location_map: dict):
    if not roead:
        raise ImportError("roead is required to process binary byml files.")
        
    with open(filepath, 'rb') as f:
        byml_data = roead.byml.from_binary(f.read())
        
    if patch_chest_byml(byml_data, location_map):
        with open(filepath, 'wb') as f:
            f.write(roead.byml.to_binary(byml_data))
