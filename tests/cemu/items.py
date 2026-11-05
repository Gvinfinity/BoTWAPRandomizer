"""Live scenarios built from the production world contract, without installing AP."""
from importlib import import_module, util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]


def world_reference():
    name = '_botw_live_world'
    if name not in sys.modules:
        path = ROOT / 'worlds/botw'
        spec = util.spec_from_file_location(name, path / '__init__.py', submodule_search_locations=[str(path)])
        # Keep the real resource loader, but skip the AP-dependent world initializer.
        package = util.module_from_spec(spec)
        sys.modules[name] = package
    return import_module(name + '.reference')


def category(name, delivery):
    kind = delivery['kind']
    if kind == 'actor':
        actor = delivery['actor']
        for prefix, group in [('Weapon_Sword_', 'melee'), ('Weapon_Bow_', 'bows'),
                              ('Weapon_Shield_', 'shields'), ('Armor_', 'armor')]:
            if actor.startswith(prefix): return group
        if 'Arrow' in actor: return 'arrows'
        if actor == 'PlayerStole2': return 'key_items'
        return 'materials'
    if kind == 'progression': return delivery['command']
    if kind == 'rupees': return 'rupees'
    if kind == 'native':
        if name.endswith(' Tower'): return 'towers'
        if name.endswith(' Controls'): return 'dungeon_controls'
        if name.endswith(' Cleared'): return 'dungeon_completion'
        if 'Gale' in name or 'Protection' in name or 'Grace' in name or 'Fury' in name:
            return 'champion_upgrades' if name.startswith('Progressive ') else 'champion_abilities'
        if name == 'Progressive Master Sword': return 'master_sword_upgrades'
        if name == 'Progressive Armor Upgrade': return 'armor_upgrades'
        if name == 'Travel Medallion': return 'travel_medallion'
        if name == 'One-Hit Obliterator': return 'obliterator'
        if name == 'Master Cycle Zero': return 'motorcycle'
        if name == 'Camera': return 'camera'
        if name == 'Progressive Sheikah Sensor': return 'sensor'
        if name.startswith('Progressive '): return 'rune_upgrades'
        return 'runes'
    raise ValueError(f'Unsupported delivery: {name}: {delivery}')


def scenarios(mode):
    reference = world_reference()
    entries = [dict(item=entry['id'], name=name, category=category(name, entry['delivery']),
                    delivery=entry['delivery']) for name, entry in reference.item_data.items()]
    if mode == 'simplified':
        entries = [next(e for e in entries if e['name'] == 'Arrows (10)')]
    elif mode == 'partial':
        seen = set()
        selected = []
        for entry in entries:
            if entry['category'] not in seen:
                seen.add(entry['category'])
                selected.append(entry)
        entries = selected
    elif mode != 'full':
        raise ValueError(f'Unknown test mode: {mode}')
    cases = []
    for entry in entries:
        profile = reference.native_grants.get(entry['name'])
        # Exercise each tier of the selected progressive item, including replacement.
        repeats = len(profile['Tiers']) if profile else 1
        for receipt in range(repeats):
            cases.append(dict(entry, receipt=receipt + 1))
    return cases


def reset_delivery_state(data):
    """Reset only the isolated test save; hashes and record ordering are preserved."""
    import struct, zlib
    reference = world_reference()
    resets = {flag['Name']: 0 for profile in reference.native_grants.values()
              for tier in profile['Tiers'] for flag in tier['Writes']}
    from importlib import import_module
    encounters = import_module(reference.__package__ + '.static.combat').catalog()['locations']
    resets.update({entry['watch_flag']: 0 for entry in encounters})
    resets.update({entry['watch_flag']: 0 for entry in reference.load_completions() if 'watch_flag' in entry})
    resets.update(MaxHartValue=12, WeaponPorchStockNum=8, BowPorchStockNum=5,
                  ShieldPorchStockNum=4, CurrentRupee=0, IsGet_PlayerStole2=0)
    resets.update(StaminaMax=struct.unpack('>I', struct.pack('>f', 1000.0))[0],
                  StaminaCurrentMax=struct.unpack('>I', struct.pack('>f', 1000.0))[0])
    # A deterministic, empty pouch prevents preowned items and full slots masking grants.
    resets.update(PorchItem=0, PorchItem_Value1=0, PorchItem_EquipFlag=0)
    # This rank is transient (IsSave=false); fountain revival flags reconstruct it.
    resets.pop('GreatFairy_ArmorRank', None)
    resets.update({f'RevivalGreatFairy{i}': 0 for i in range(1, 5)})
    by_hash = {zlib.crc32(name.encode()): (name, value) for name, value in resets.items()}
    found = set(); output = bytearray(data)
    for at in range(12, len(output) - 4, 8):
        key = struct.unpack_from('>I', output, at)[0]
        if key in by_hash:
            name, value = by_hash[key]; found.add(name)
            struct.pack_into('>I', output, at + 4, value)
    missing = resets.keys() - found
    if missing: raise ValueError('Save lacks delivery test fields: ' + ', '.join(sorted(missing)))
    return output


def physical_check(kind):
    reference = world_reference()
    entries = reference.load_completions()
    return next(e for e in entries if e.get('tower') == 8) if kind == 'tower' else next(
        e for e in entries if e.get('dungeon') == 'Dungeon000')


def set_save_values(data, values):
    """Set named existing scalar test-precondition fields without adding records."""
    import struct, zlib
    output = bytearray(data)
    pending = {zlib.crc32(name.encode()): (name, value) for name, value in values.items()}
    found = set()
    for at in range(12, len(output) - 4, 8):
        key = struct.unpack_from('>I', output, at)[0]
        if key in pending:
            name, value = pending[key]; found.add(name)
            struct.pack_into('>I', output, at + 4, value)
    if values.keys() - found: raise ValueError('Save lacks test preconditions: ' + str(values.keys() - found))
    return output
