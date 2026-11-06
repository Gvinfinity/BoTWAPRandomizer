from collections import Counter
import hashlib
import json
from pathlib import Path

from BaseClasses import ItemClassification
from worlds.AutoWorld import World, WebWorld

from .Items import BotWItem, botw_items, classification
from .Locations import botw_locations, chest_data, completion_data, combat_data
from .Options import BotWOptions, Goal
from .Patch import BotWPatch
from .Regions import create_regions
from .Rules import set_rules
from .reference import categories, item_data, item_groups
from .static.checks import PROTOCOL_VERSION, check_actor_name
from .static.protocol import MAILBOX_VERSION, seed_fingerprint
from .static.starting import starting_state
from .static.objectives import BEAST_DEFEATS, SWORD_TRIAL


class BotWWebWorld(WebWorld):
    pass


class BotWWorld(World):
    """Native chest, shrine, tower and encounter defeat checks."""
    game = "Breath of the Wild"
    options_dataclass = BotWOptions
    options: BotWOptions
    item_name_to_id = botw_items
    location_name_to_id = botw_locations
    item_name_groups = item_groups
    web = BotWWebWorld()

    def category_enabled(self, entry):
        for category in entry.get("category", []):
            for condition in categories.get(category, {}).get("yaml_option", []):
                option_name = condition.removeprefix("!")
                # This first world does not expose Manual-only check types.
                enabled = option_name == "shuffle_shrine_chests" or bool(getattr(self.options, option_name, False))
                if enabled == condition.startswith("!"):
                    return False
        return True

    def generate_early(self):
        unsupported = [entry['name'] for entry in item_data.values()
                       if entry['delivery']['kind'] == 'unimplemented' and self.category_enabled(entry)]
        if unsupported:
            raise ValueError('Enabled items have no delivery implementation: ' + ', '.join(unsupported))
        for option, category in ((self.options.enable_the_master_trials_dlc, "The Master Trials DLC"),
                                 (self.options.enable_the_champions_ballad_dlc, "The Champions' Ballad DLC")):
            if option and not any(category in entry.get("category", []) for entry in chest_data):
                raise ValueError(f"{category} requires a chest catalog discovered with --dlc")
        self.trial_of_the_sword_enabled = bool(self.options.enable_the_master_trials_dlc
                                               and self.options.trial_of_the_sword)
        self.active_chests = [entry for entry in chest_data if self.category_enabled(entry)
                              and (self.trial_of_the_sword_enabled
                                   or not entry['region'].startswith('Trial of the Sword ('))
                              and (self.options.chest_sanity or "Overworld Chests" not in entry.get("category", []))]
        if not self.active_chests:
            raise ValueError("No mapped checks; create worlds/botw/data/chests.json using the static patcher")
        self.active_completions = [entry for entry in completion_data
                                   if (entry["kind"] == "shrine" and self.options.shrine_sanity)
                                   or (entry["kind"] == "tower" and self.options.tower_sanity
                                       and not (entry["tower"] == 7 and self.options.skip_great_plateau))]
        required_bosses = {'Dark Beast Ganon - Defeated'}
        if self.options.goal in (Goal.option_all_divine_beasts, Goal.option_all_divine_beasts_and_trials):
            required_bosses.update(BEAST_DEFEATS)
        self.active_combat = [entry for entry in combat_data if self.category_enabled(entry)
                              and ((entry['kind'] == 'miniboss' and self.options.miniboss_sanity)
                                   or (entry['kind'] == 'boss' and self.options.boss_sanity)
                                   or entry['name'] in required_bosses)]
        self.active_objectives = [dict(SWORD_TRIAL)] if self.trial_of_the_sword_enabled else []
        self.active_locations = [*self.active_chests, *self.active_completions, *self.active_combat, *self.active_objectives]
        if self.options.goal == Goal.option_all_checks:
            self.goal_requirements = [entry for entry in self.active_locations
                                      if entry['name'] != 'Dark Beast Ganon - Defeated']
        else:
            self.goal_requirements = [entry for entry in self.active_locations
                                      if entry['name'] in required_bosses - {'Dark Beast Ganon - Defeated'}
                                      or (self.options.goal == Goal.option_all_divine_beasts_and_trials
                                          and entry.get('kind') == 'objective')]
        self.starting_state = starting_state(bool(self.options.skip_great_plateau))
        # The static patch initializes these exact defaults before a new save.
        for name, count in self.starting_state["logical_inventory"].items():
            for _ in range(count):
                self.multiworld.push_precollected(self.create_item(name))

    def create_regions(self):
        create_regions(self)

    def create_item(self, name):
        entry = item_data[name]
        return BotWItem(name, classification(entry), entry["id"], self.player)

    def create_event(self, name):
        return BotWItem(name, ItemClassification.progression, None, self.player)

    def create_items(self):
        starting = Counter(item.name for item in self.multiworld.precollected_items[self.player])
        progression, optional = [], []
        for name, entry in item_data.items():
            if not self.category_enabled(entry):
                continue
            count = max(0, entry["count"] - starting[name])
            target = progression if entry.get("progression") else optional
            target.extend(self.create_item(name) for _ in range(count))
        slots = len(self.multiworld.get_unfilled_locations(self.player))
        if len(progression) > slots:
            raise ValueError(f"{slots} mapped checks cannot hold {len(progression)} progression items; add bindings")
        self.random.shuffle(optional)
        pool = progression + optional[:slots - len(progression)]
        pool.extend(self.create_item(self.get_filler_item_name()) for _ in range(slots - len(pool)))
        self.multiworld.itempool.extend(pool)

    def get_filler_item_name(self):
        return "Arrows (10)"

    def set_rules(self):
        set_rules(self)

    def fill_slot_data(self):
        return {
            "protocol_version": MAILBOX_VERSION,
            "seed": str(self.multiworld.seed_name),
            "player": self.player,
            "seed_fingerprint": seed_fingerprint(self.multiworld.seed_name, self.player,
                                                 [entry["id"] for entry in self.active_locations], self.starting_state),
            "starting_state": self.starting_state,
            "starting_inventory": {str(item_data[name]["id"]): count
                                   for name, count in self.starting_state["logical_inventory"].items()},
            "check_actor_prefix": "AP_Check_",
            "check_actor_id_format": "8 uppercase hexadecimal digits",
            "goal": self.options.goal.current_key,
            "goal_location_id": next(entry["id"] for entry in self.active_combat
                                      if entry["name"] == "Dark Beast Ganon - Defeated"),
            "goal_required_location_ids": [entry['id'] for entry in self.goal_requirements],
            "locations": {str(entry["id"]): check_actor_name(entry["id"]) for entry in self.active_locations},
            "items": {str(entry["id"]): entry["delivery"] for entry in item_data.values()},
        }

    def generate_output(self, output_directory):
        entries = []
        for entry in self.active_locations:
            location = self.get_location(entry["name"])
            item = location.item
            entries.append(dict(entry, check_actor=check_actor_name(entry["id"]),
                                placed_item={"name": item.name, "id": item.code, "player": item.player,
                                             "player_name": self.multiworld.get_player_name(item.player)}))
        digest = hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()
        plan = {"version": PROTOCOL_VERSION, "game": self.game, "player": self.player,
                "player_name": self.player_name, "seed": str(self.multiworld.seed_name),
                "catalog_digest": digest, "locations": entries, "starting_state": self.starting_state,
                "slot_data": self.fill_slot_data()}
        filename = Path(output_directory) / (self.multiworld.get_out_file_name_base(self.player) + ".apbotw")
        BotWPatch(str(filename), self.player, self.player_name, plan=plan).write()
