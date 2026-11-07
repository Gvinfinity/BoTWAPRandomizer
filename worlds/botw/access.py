"""Normal-route boarding and local story milestones, separate from AP rewards.

Supplies are renewable vanilla sources, not received AP ammunition counts.
Local events model the ability to complete a quest; they never write game flags.
The native game still requires performing the corresponding quests/actions.
"""
from .reference import manual_locations
from .static.check_logic import CALAMITY_ROUTE, check_requirement
from .static.combat import catalog as combat_catalog

GERUDO_DISGUISE = ('|Gerudo Top| AND (|Gerudo Veil| OR |Thunder Helm|) AND '
                  '(|Gerudo Sirwal| OR |Sand Boots| OR |Snow Boots|)')
COLD_PROTECTION = ('(|@Cold Resistant Head| AND |@Cold Resistant Body|) OR '
                   '(|@Cold Resistant Head| AND |@Cold Resistant Legs|) OR '
                   '(|@Cold Resistant Body| AND |@Cold Resistant Legs|)')
FIRE_PROTECTION = ('(|@Flame Resistant Head| AND |@Flame Resistant Body|) OR '
                   '(|@Flame Resistant Head| AND |@Flame Resistant Legs|) OR '
                   '(|@Flame Resistant Body| AND |@Flame Resistant Legs|)')
BOARDING = {
    'Vah Medoh': ('Tabantha', '|Paraglider|'),
    'Vah Rudania': ('Eldin', '|Progressive Remote Bomb| AND |Progressive Stasis|'),
    'Vah Ruta': ('Lanayru', '|Zora Armor| AND |Cryonis|'),
    'Vah Naboris': ('Gerudo Town', '|Thunder Helm| AND |Magnesis|'),
}
CHAMPION_ITEMS = frozenset({
    "Progressive Revali's Gale", "Progressive Daruk's Protection",
    "Progressive Mipha's Grace", "Progressive Urbosa's Fury",
    'Vah Medoh Cleared', 'Vah Rudania Cleared', 'Vah Ruta Cleared', 'Vah Naboris Cleared',
})
SONGS = {
    'Revali': ('Tabantha', ('Noe Rajee Shrine', 'Kiah Toza Shrine', 'Shira Gomar Shrine')),
    'Daruk': ('Eldin', ('Rinu Honika Shrine', 'Sharo Lun Shrine', 'Kamia Omuna Shrine')),
    'Mipha': ('Lanayru', ('Sato Koda Shrine', 'Mah Eliya Shrine', 'Kee Dafunia Shrine')),
    'Urbosa': ('Gerudo Desert', ('Keive Tala Shrine', 'Takama Shiri Shrine', 'Kihiro Moh Shrine')),
}
OBLITERATOR_SHRINES = ('Yowaka Ita Shrine', 'Rohta Chigah Shrine', 'Ruvo Korbah Shrine', 'Etsu Korima Shrine')


def story_events(world):
    events = [
        dict(name='Calamity Ganon Cleared Locally', region='Hyrule Castle', requires=CALAMITY_ROUTE),
        # Foothill Stable sells Fireproof Elixirs; Rito/Bazaar supplies and
        # renewable ingredients provide cold/heat protection without AP armor.
        dict(name='Native Fireproof Supplies', region='Eldin', requires=''),
        dict(name='Native Plateau Cold Protection Supplies', region='Great Plateau', requires=''),
        dict(name='Native Cold Protection Supplies', region='Tabantha', requires=''),
        dict(name='Native Desert Protection Supplies', region='Gerudo Desert', requires=''),
        # Flight Range has a bow and Teba supplies Bomb Arrows after training.
        dict(name='Medoh Flight Range Supplies', region='Tabantha', requires='|Paraglider|'),
        # Shock Arrows and bows can be gathered on the normal Zora approach;
        # defeating the Lynel or receiving AP arrow bundles is not required.
        dict(name='Ruta Boarding Supplies', region='Lanayru', requires='|Zora Armor|'),
        dict(name='Naboris Helm Returned', region='Gerudo Town', requires='|Thunder Helm| AND |Magnesis|'),
        dict(name='Naboris Riju Supplies', region='Gerudo Town', event_requires=('Naboris Helm Returned',)),
    ]
    for beast in BOARDING:
        boss = next(e for e in combat_catalog()['locations'] if e['region'] == f'Divine Beast {beast}')
        events.append(dict(name=f'Freed {beast}', region=f'Divine Beast {beast}', requires=boss['requires']))
    if world.trial_of_the_sword_enabled:
        events.extend([
            dict(name='Beginning Trials Completed', region='Trial of the Sword (Beginning Trials)', requires=''),
            dict(name='Middle Trials Completed', region='Trial of the Sword (Middle Trials)', requires=''),
        ])
    if world.options.enable_the_champions_ballad_dlc:
        names = {*OBLITERATOR_SHRINES, *(name for _, shrines in SONGS.values() for name in shrines)}
        for name in sorted(names):
            entry = next(e for e in manual_locations if e['name'] == name)
            events.append(dict(name=f'Completed {name}', region=entry['region'], requires=check_requirement(entry),
                               ballad=True, after_obliterator=name not in OBLITERATOR_SHRINES))
        events.append(dict(name='Obliterator Trials Completed', region='Great Plateau (One-Hit Obliterator)',
                           event_requires=tuple(f'Completed {name}' for name in OBLITERATOR_SHRINES)))
        for champion, (region, shrines) in SONGS.items():
            # Rematches provide their equipment; AP equipment ownership is not
            # a substitute for completing the three trials and the rematch.
            events.append(dict(name=f"Completed {champion}'s Song", region=region,
                               event_requires=tuple(f'Completed {name}' for name in shrines)))
    return events
