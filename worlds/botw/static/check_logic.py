"""Check-specific corrections to inherited Manual logic.

Vanilla weapons, ammunition and cooking remain available. Recommended armor
upgrades, hearts and stamina are not mandatory AP progression gates. Keep
physical rune/quest requirements separate from those recommendations.
"""
from .requirements import parse_requirement

# Stable physical identities: never assign numbered chest rules by sort order.
CHEST_RULES = {
    ('Map/MainField/D-6/D-6_Static.smubin', 0xF5EA1473): '|Progressive Remote Bomb|',
    ('Map/MainField/E-6/E-6_Dynamic.smubin', 0xA2A08719): '|Progressive Remote Bomb|',
    ('Map/MainField/E-6/E-6_Static.smubin', 0xE1F9BB4B): "|Progressive Remote Bomb| OR |Paraglider| OR |Progressive Revali's Gale| OR |Revali's Gale|",
    ('Map/MainField/E-6/E-6_Static.smubin', 0x78F0EAF1): "|Progressive Remote Bomb| OR |Paraglider| OR |Progressive Revali's Gale| OR |Revali's Gale|",
    ('Map/MainField/E-6/E-6_Dynamic.smubin', 0x6260C604): '|Magnesis|',
    ('Map/MainField/E-6/E-6_Dynamic.smubin', 0xDF4FC4CF): '|Magnesis|',
    ('Map/MainField/E-6/E-6_Dynamic.smubin', 0x123AEF57): '|Magnesis|',
    ('Map/MainField/E-7/E-7_Dynamic.smubin', 0x68BE4D6A): '|Progressive Remote Bomb|',
    ('Map/MainField/E-7/E-7_Static.smubin', 0xE382DE4C): '|Progressive Stasis|',
}

# Exterior/quest access for Guardian Scout shrines. Ordinary combat equipment
# is native. Cryonis/Magnesis pillars and upgraded armor are combat aids, not
# mandatory solutions to a Scout fight. Cave-opening runes remain separate.
STRENGTH_SHRINES = {
    'Soh Kofi', 'Pumaag Nitae', 'Dah Kaso', 'Katah Chuki', 'Noya Neha', 'Dah Hesho',
    'Sasa Kai', "Ke'nai Shakah", 'Mijah Rokee', 'Namika Ozz', 'Shoqa Tatone', 'Muwo Jeem',
    'Chaas Qeta', "Tena Ko'sah", 'Tutsuwa Nima', 'Kema Kosassa', 'Goma Asaagh',
    'Mozo Shenno', 'Hia Miu', "Saas Ko'sah",
}
STRENGTH_ENTRANCES = {
    'Noya Neha': '|Progressive Remote Bomb|',
    "Ke'nai Shakah": '|Progressive Remote Bomb|',
    'Shoqa Tatone': '|Camera|',
    'Tutsuwa Nima': "|Dinraal's Scale|",
}
# These protect exposed approaches. The native cooking branches below preserve
# ordinary no-glitch routes without requiring a randomized clothing set.
COLD_STRENGTH_SHRINES = {'Kema Kosassa', 'Goma Asaagh', 'Mozo Shenno', 'Hia Miu'}
SHRINE_RULES = {
    'Bosh Kala': '|Paraglider|',
    'Voo Lota': '|Freed Vah Medoh| AND |Paraglider|',
    'Sha Warvo': '|Paraglider| AND |Native Cold Protection Supplies|',
    # The rock pillar is climbable; Revali is an optional shortcut.
    'Zuna Kai': '',
}


# Normal routes retain the rune used for the shield/pillar phases. Native
# weapons, shields and bows cover the other fights. Beast interior rules still
# enforce Controls and puzzle runes before any of these checks can be reached.
CALAMITY_ROUTE = ('(|Freed Vah Rudania| OR |Progressive Remote Bomb|) AND '
                  '(|Freed Vah Naboris| OR |Magnesis|)')
BOSS_RULES = {
    'Windblight Ganon - Defeated': '',
    'Fireblight Ganon - Defeated': '|Progressive Remote Bomb|',
    'Waterblight Ganon - Defeated': '',
    'Thunderblight Ganon - Defeated': '|Magnesis|',
    'Calamity Ganon - Defeated': CALAMITY_ROUTE,
    'Maz Koshia - Defeated': '',
    # Zelda supplies the native Bow of Light after Calamity. An AP bow receipt
    # is not the prerequisite for progressing to the final encounter.
    'Dark Beast Ganon - Defeated': '|Calamity Ganon Cleared Locally|',
}


def combine(op, children):
    flattened = []
    for child in children:
        for value in child[1] if child[0] == op else (child,):
            if value not in flattened:
                flattened.append(value)
    children = tuple(flattened)
    if op == 'all':
        children = tuple(c for c in children if c[0] != 'true')
    elif any(c[0] == 'true' for c in children):
        return ('true',)
    if not children:
        return ('true',)
    if len(children) == 1:
        return children[0]
    return (op, children)


def native_routes(tree):
    op = tree[0]
    if op in ('all', 'any'):
        return combine(op, (native_routes(c) for c in tree[1]))
    if op == 'item':
        name = tree[1]
        if name in {'Progressive Armor Upgrade', 'Heart Container', 'Stamina Vessel'}:
            return ('true',)
        if name.startswith('Vah ') and name.endswith(' Cleared'):
            return ('item', 'Freed ' + name.removesuffix(' Cleared'), 1)
    if op == 'category':
        name = tree[1].removeprefix('Upgradeable ')
        if name in {'Head', 'Body', 'Legs'}:
            return ('true',)
        if 'Cold Resist' in name:
            supply = ('Native Plateau Cold Protection Supplies' if name == 'Cold Resistance'
                      else 'Native Cold Protection Supplies')
        elif 'Flame Resist' in name:
            supply = 'Native Fireproof Supplies'
        elif 'Heat Resist' in name:
            supply = 'Native Desert Protection Supplies'
        else:
            return tree
        return ('any', (('category', name, tree[2]), ('item', supply, 1)))
    return tree


def render(tree):
    op = tree[0]
    if op == 'true':
        return ''
    if op in ('item', 'category'):
        name = ('@' if op == 'category' else '') + tree[1]
        return f'|{name}{":" + str(tree[2]) if tree[2] != 1 else ""}|'
    join = ' AND ' if op == 'all' else ' OR '
    return '(' + join.join(render(child) for child in tree[1]) + ')'


def check_requirement(entry):
    """Return the effective base expression; region/event/goal rules add to it."""
    identity = (entry.get('logical_map'), entry.get('hash_id'))
    if identity in CHEST_RULES:
        return CHEST_RULES[identity]
    if entry.get('kind') == 'boss':
        return BOSS_RULES[entry['name']]
    if entry.get('kind') == 'miniboss':
        if entry['family'] in {'hinox', 'talus'}:
            return ''
        if entry['family'] == 'molduga':
            # Teba's training supplies Bomb Arrows and a Flight Range bow.
            return '|Progressive Remote Bomb| OR |Medoh Flight Range Supplies|'
        raise ValueError(f'Unreviewed miniboss family: {entry["family"]}')
    name = entry['name'].split(' Shrine', 1)[0]
    if ' Shrine' not in entry['name']:
        return entry.get('requires', '')
    if name in STRENGTH_SHRINES:
        expression = STRENGTH_ENTRANCES.get(name, '')
        if name in COLD_STRENGTH_SHRINES:
            expression = (f'({expression}) AND ' if expression else '') + '|Native Cold Protection Supplies|'
        return expression
    expression = SHRINE_RULES.get(name, entry.get('requires', ''))
    return render(native_routes(parse_requirement(expression)))


def apply_check_logic(entry):
    return dict(entry, requires=check_requirement(entry))
