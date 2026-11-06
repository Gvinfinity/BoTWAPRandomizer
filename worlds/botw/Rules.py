from worlds.generic.Rules import set_rule

from .logic import compile_requirement
from .reference import item_data, item_groups, manual_regions
from .access import BOARDING, CHAMPION_ITEMS, COLD_PROTECTION, FIRE_PROTECTION, GERUDO_DISGUISE, SONGS


def set_rules(world):
    tower_items = frozenset(name for name in item_data if name.endswith(" Tower"))
    overworld = {
        "Great Plateau", "Central Hyrule", "Dueling Peaks", "Necluda", "Faron",
        "Lanayru", "Eldin", "Akkala", "Great Hyrule Forest", "Lake Hylia",
        "Tabantha", "Hyrule Ridge", "Gerudo Highlands", "Gerudo Desert", "Hebra",
        "Hyrule Castle",
    }

    logic_items = item_data | {entry['name']: {} for entry in world.story_events}

    def rule(expression, ballad=False):
        ignored = tower_items | CHAMPION_ITEMS if ballad else tower_items
        return compile_requirement(expression, world.player, logic_items, item_groups, ignored)

    def has_all(names):
        names = tuple(names)
        return lambda state: all(state.has(name, world.player) for name in names)

    for name, data in manual_regions.items():
        # Towers reveal maps; they do not grant physical access to the overworld.
        requirement = rule("" if name in overworld else data.get("requires", ""))
        if name != "Great Plateau":
            original = requirement
            requirement = lambda state, original=original: state.has("Paraglider", world.player) and original(state)
        if name.startswith('Divine Beast Vah '):
            beast = name.removeprefix('Divine Beast ')
            entrance = f'{beast} Boarding -> {name}'
        else:
            entrance = f'Menu -> {name}'
        if name == 'Trial of the Sword (Middle Trials)':
            original = requirement
            requirement = lambda state, original=original: original(state) and state.has('Beginning Trials Completed', world.player)
        elif name == 'Trial of the Sword (Final Trials)':
            original = requirement
            requirement = lambda state, original=original: original(state) and state.has('Middle Trials Completed', world.player)
        elif name == 'Great Plateau (One-Hit Obliterator)':
            original = requirement
            cleared = has_all(f'Freed {beast}' for beast in BOARDING)
            requirement = lambda state, original=original, cleared=cleared: original(state) and cleared(state)
        elif name == 'Final Trial':
            original = requirement
            songs = has_all(f"Completed {champion}'s Song" for champion in SONGS)
            requirement = lambda state, original=original, songs=songs: original(state) and songs(state)
        set_rule(world.get_entrance(entrance), requirement)

    set_rule(world.get_entrance('Gerudo Desert -> Gerudo Town'), rule(GERUDO_DISGUISE))
    cold, fire = rule(COLD_PROTECTION), rule(FIRE_PROTECTION)
    supplies = {'Vah Medoh': 'Medoh Flight Range Supplies', 'Vah Ruta': 'Ruta Boarding Supplies',
                'Vah Naboris': 'Naboris Riju Supplies'}
    for beast, (parent, expression) in BOARDING.items():
        base = rule(expression)
        def boarding(state, beast=beast, base=base):
            if not base(state):
                return False
            if beast in supplies and not state.has(supplies[beast], world.player):
                return False
            if beast == 'Vah Medoh':
                return cold(state) or state.has('Native Cold Protection Supplies', world.player)
            if beast == 'Vah Rudania':
                return fire(state) or state.has('Native Fireproof Supplies', world.player)
            if beast == 'Vah Naboris':
                return state.has('Native Desert Protection Supplies', world.player)
            return True
        set_rule(world.get_entrance(f'{parent} -> {beast} Boarding'), boarding)

    for entry in world.story_events:
        base = rule(entry.get('requires', ''), entry.get('ballad', False))
        prerequisites = list(entry.get('event_requires', ()))
        if entry.get('after_obliterator'):
            prerequisites.append('Obliterator Trials Completed')
        events = has_all(prerequisites)
        set_rule(world.get_location(entry['name']), lambda state, base=base, events=events: base(state) and events(state))
    for entry in world.active_locations:
        ballad = "The Champions' Ballad DLC" in entry.get('category', [])
        requirement = rule(entry.get("requires", ""), ballad)
        if ballad and entry['region'] != 'Great Plateau (One-Hit Obliterator)':
            original = requirement
            requirement = lambda state, original=original: original(state) and state.has('Obliterator Trials Completed', world.player)
        if entry.get("kind") == "tower":
            # Retain climbing/traversal requirements at the tower itself.
            traversal = rule(manual_regions[entry["region"]].get("requires", ""))
            original = requirement
            requirement = lambda state, original=original, traversal=traversal: original(state) and traversal(state)
        set_rule(world.get_location(entry["name"]), requirement)
    dark_beast = world.get_location('Dark Beast Ganon - Defeated')
    combat_rule = dark_beast.access_rule
    required = tuple(world.get_location(entry['name']) for entry in world.goal_requirements)
    set_rule(dark_beast, lambda state: combat_rule(state) and all(location.can_reach(state) for location in required))
    set_rule(world.get_location("Dark Beast Ganon Defeated"), lambda state: dark_beast.can_reach(state))
    world.multiworld.completion_condition[world.player] = lambda state: state.has("Victory", world.player)
