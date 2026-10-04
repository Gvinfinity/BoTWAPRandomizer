import os
import glob
import roead

def patch_bdrop_file(filepath: str, location_map: dict):
    """
    Reads a .bdrop file, identifies chests tied to AP locations,
    and modifies their contents to drop AP_Dummy_Check.
    """
    with open(filepath, 'rb') as f:
        byml_data = roead.byml.from_binary(f.read())
    
    # Example parsing logic modeled after MelonSpeedruns/BotwRandomizer
    if 'Actors' in byml_data:
        for actor in byml_data['Actors']:
            if 'TBox' in actor.get('Gyml', ''):
                # Check if this chest maps to an AP location
                unique_id = actor.get('HashId')
                if unique_id in location_map:
                    # Overwrite item inside chest
                    actor['!Parameters']['DropActor'] = 'AP_Dummy_Check'
                    actor['!Parameters']['AP_LocationID'] = location_map[unique_id]

    with open(filepath, 'wb') as f:
        f.write(roead.byml.to_binary(byml_data))

def main():
    print("Patching .bdrop files...")
    # Load mapping from external/BotW-APManual
    # iterate and patch
    pass

if __name__ == "__main__":
    main()
