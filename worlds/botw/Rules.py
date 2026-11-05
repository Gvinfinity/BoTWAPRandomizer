from worlds.generic.Rules import set_rule

from .logic import compile_requirement
from .reference import item_data, item_groups, manual_regions


def set_rules(world):
    tower_items = frozenset(name for name in item_data if name.endswith(" Tower"))
    overworld = {
        "Great Plateau", "Central Hyrule", "Dueling Peaks", "Necluda", "Faron",
        "Lanayru", "Eldin", "Akkala", "Great Hyrule Forest", "Lake Hylia",
        "Tabantha", "Hyrule Ridge", "Gerudo Highlands", "Gerudo Desert", "Hebra",
        "Hyrule Castle",
    }

    def rule(expression):
        return compile_requirement(expression, world.player, item_data, item_groups, tower_items)

    for name, data in manual_regions.items():
        # Towers reveal maps; they do not grant physical access to the overworld.
        requirement = rule("" if name in overworld else data.get("requires", ""))
        if name != "Great Plateau":
            original = requirement
            requirement = lambda state, original=original: state.has("Paraglider", world.player) and original(state)
        set_rule(world.get_entrance(f"Menu -> {name}"), requirement)
    for entry in world.active_locations:
        requirement = rule(entry.get("requires", ""))
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
