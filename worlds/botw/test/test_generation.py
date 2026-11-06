from pathlib import Path
import tempfile

from . import BotWTestBase


class TestBotWGeneration(BotWTestBase):
    def test_all_items_have_delivery_implementations(self):
        from ..reference import item_data, native_grants
        self.assertTrue(item_data)
        for name, entry in item_data.items():
            delivery = entry["delivery"]
            self.assertIn(delivery["kind"], {"actor", "rupees", "progression", "native"}, name)
            if delivery["kind"] == "native":
                self.assertIn(name, native_grants)
                self.assertTrue(native_grants[name]["Tiers"])

    def test_itempool_matches_checks(self):
        checks = self.multiworld.get_unfilled_locations(self.player)
        self.assertEqual(len(checks), len(self.multiworld.itempool))

    def test_initial_plateau_checks_exist(self):
        reachable = [location for location in self.multiworld.get_unfilled_locations(self.player)
                     if location.can_reach(self.multiworld.state)]
        self.assertTrue(reachable)
        self.assertTrue(all(location.parent_region.name == "Great Plateau" for location in reachable))

    def test_shrine_rune_requirement(self):
        location = self.world.get_location("Oman Au Shrine - Chest")
        self.assertFalse(location.can_reach(self.multiworld.state))
        self.multiworld.state.collect(self.world.create_item("Magnesis"))
        self.assertTrue(location.can_reach(self.multiworld.state))

    def test_marker_uses_location_id(self):
        from ..static.checks import check_actor_name
        data = self.world.fill_slot_data()
        for code, name in data["locations"].items():
            self.assertEqual(name, check_actor_name(int(code)))

    def test_slot_and_generated_hook_share_seed_identity(self):
        from ..static.protocol import MAILBOX_VERSION, seed_fingerprint
        from ..static.hook import build_seed_hook
        data = self.world.fill_slot_data()
        ids = [int(code) for code in data["locations"]]
        self.assertEqual(data["protocol_version"], MAILBOX_VERSION)
        self.assertEqual(data["player"], self.player)
        self.assertEqual(data["seed_fingerprint"], seed_fingerprint(data["seed"], self.player, ids, data["starting_state"]))
        plan = {"seed": data["seed"], "player": self.player,
                "locations": [{"id": code} for code in ids], "starting_state": data["starting_state"], "slot_data": data}
        self.assertIn(b"_AP_FlushPendingChecks:", build_seed_hook(plan))

    def test_generated_patch_round_trips_locations_and_item_delivery(self):
        from Fill import distribute_items_restrictive
        from ..reference import item_data
        from ..static.plan import read_plan

        distribute_items_restrictive(self.multiworld)
        with tempfile.TemporaryDirectory() as directory:
            self.world.generate_output(directory)
            patch_path = next(Path(directory).glob('*.apbotw'))
            plan = read_plan(str(patch_path))

        planned_ids = {entry['id'] for entry in plan['locations']}
        slot_ids = {int(location_id) for location_id in plan['slot_data']['locations']}
        self.assertEqual(planned_ids, slot_ids)
        self.assertEqual(len(planned_ids), len(plan['locations']))
        self.assertEqual(len(plan['slot_data']['items']), len(item_data))
        self.assertTrue(all(entry['placed_item']['id'] is not None for entry in plan['locations']))
        self.assertTrue(all(entry['placed_item']['player_name'] == self.multiworld.get_player_name(
            entry['placed_item']['player']) for entry in plan['locations']))

    def test_plateau_skip_starts_with_map_but_keeps_paraglider_in_pool(self):
        data = self.world.fill_slot_data()
        self.assertTrue(data["starting_state"]["skip_great_plateau"])
        self.assertFalse(self.multiworld.state.has("Paraglider", self.player))
        self.assertTrue(self.multiworld.state.has("Great Plateau Tower", self.player))
        self.assertEqual(sum(item.name == "Paraglider" for item in self.multiworld.itempool), 1)
        self.assertNotIn(str(self.world.item_name_to_id["Paraglider"]), data["starting_inventory"])


class TestVanillaPlateauStart(BotWTestBase):
    options = {"skip_great_plateau": False}

    def test_paraglider_stays_in_pool_without_skip(self):
        self.assertFalse(self.multiworld.state.has("Paraglider", self.player))
        self.assertEqual(sum(item.name == "Paraglider" for item in self.multiworld.itempool), 1)
        self.assertFalse(self.world.fill_slot_data()["starting_state"]["skip_great_plateau"])

    def test_plateau_checks_reachable_before_tower(self):
        self.assertFalse(self.multiworld.state.has("Great Plateau Tower", self.player))
        self.assertTrue(any(location.can_reach(self.multiworld.state)
                            for location in self.multiworld.get_unfilled_locations(self.player)))


class TestCompletionChecks(BotWTestBase):
    def test_default_completion_counts_and_skipped_plateau(self):
        entries = self.world.active_completions
        self.assertEqual(sum(e['kind'] == 'shrine' for e in entries), 120)
        self.assertEqual(sum(e['kind'] == 'tower' for e in entries), 14)
        self.assertNotIn('Great Plateau Tower', {e['name'] for e in entries})

    def test_tower_check_needs_paraglider_but_not_tower_item(self):
        location = self.world.get_location('Central Tower')
        self.assertFalse(location.can_reach(self.multiworld.state))
        self.multiworld.state.collect(self.world.create_item('Paraglider'))
        self.assertTrue(location.can_reach(self.multiworld.state))

    def test_overworld_regions_are_open_without_tower_items(self):
        self.multiworld.state.collect(self.world.create_item('Paraglider'))
        for region in ('Central Hyrule', 'Faron', 'Hyrule Ridge', 'Hebra', 'Hyrule Castle'):
            self.assertTrue(self.world.get_region(region).can_reach(self.multiworld.state), region)

    def test_shrine_completion_keeps_rune_requirement(self):
        location = self.world.get_location('Ja Baij Shrine')
        self.assertFalse(location.can_reach(self.multiworld.state))
        self.multiworld.state.collect(self.world.create_item('Progressive Remote Bomb'))
        self.assertTrue(location.can_reach(self.multiworld.state))


class TestCompletionChecksOff(BotWTestBase):
    options = {'shrine_sanity': False, 'tower_sanity': False, 'miniboss_sanity': False, 'boss_sanity': False}

    def test_no_completion_checks(self):
        self.assertEqual(self.world.active_completions, [])
        self.assertEqual(len(self.world.active_locations), len(self.world.active_chests) + 5)
        self.assertEqual(len(self.world.goal_requirements), 4)
        goal = next(e for e in self.world.active_combat if e['name'] == 'Dark Beast Ganon - Defeated')
        self.assertEqual(self.world.fill_slot_data()['goal_location_id'], goal['id'])


class TestGoalPrerequisites(BotWTestBase):
    def test_naboris_and_goal_require_thunder_helm(self):
        from BaseClasses import ItemClassification
        self.assertEqual(self.world.create_item('Thunder Helm').classification, ItemClassification.progression)
        self.collect_all_but('Thunder Helm')
        region = self.world.get_region('Divine Beast Vah Naboris')
        boss = self.world.get_location('Thunderblight Ganon - Defeated')
        victory = self.world.get_location('Dark Beast Ganon Defeated')
        self.assertFalse(region.can_reach(self.multiworld.state))
        self.assertFalse(boss.can_reach(self.multiworld.state))
        self.assertFalse(victory.can_reach(self.multiworld.state))
        # The surrounding desert is still open without the Helm.
        self.assertTrue(self.world.get_region('Gerudo Desert').can_reach(self.multiworld.state))
        self.multiworld.state.collect(self.world.create_item('Thunder Helm'))
        self.assertTrue(region.can_reach(self.multiworld.state))
        self.assertTrue(boss.can_reach(self.multiworld.state))
        self.assertTrue(victory.can_reach(self.multiworld.state))

    def test_bow_and_paraglider_cannot_unlock_victory(self):
        for name in ('Paraglider', 'Bow of Light'):
            self.multiworld.state.collect(self.world.create_item(name))
        self.assertFalse(self.world.get_location('Dark Beast Ganon - Defeated').can_reach(self.multiworld.state))
        self.assertFalse(self.world.get_location('Dark Beast Ganon Defeated').can_reach(self.multiworld.state))

    def test_beast_controls_are_required_for_goal(self):
        self.collect_all_but('Vah Ruta Controls')
        self.assertFalse(self.world.get_location('Dark Beast Ganon Defeated').can_reach(self.multiworld.state))
        self.multiworld.state.collect(self.world.create_item('Vah Ruta Controls'))
        self.assertTrue(self.world.get_location('Dark Beast Ganon Defeated').can_reach(self.multiworld.state))


class TestDlcGoalPrerequisites(TestGoalPrerequisites):
    options = {'enable_the_master_trials_dlc': True}

    def test_trial_is_a_native_completion_objective(self):
        objective = self.world.active_objectives[0]
        self.assertEqual(objective['watch_flag'], '100enemy_Clear_Senior')
        self.assertIn(objective['id'], self.world.fill_slot_data()['goal_required_location_ids'])
        self.collect_all_but('Heart Container')
        self.assertFalse(self.world.get_location('Dark Beast Ganon Defeated').can_reach(self.multiworld.state))


class TestDarkBeastOnlyGoal(BotWTestBase):
    options = {'goal': 'dark_beast_ganon', 'boss_sanity': False,
               'enable_the_master_trials_dlc': True, 'miniboss_sanity': False}

    def test_goal_has_no_beast_or_trial_prerequisites(self):
        slot = self.world.fill_slot_data()
        self.assertEqual(slot['goal'], 'dark_beast_ganon')
        self.assertEqual(slot['goal_required_location_ids'], [])
        self.assertEqual([e['name'] for e in self.world.active_combat], ['Dark Beast Ganon - Defeated'])
        for name in ('Paraglider', 'Bow of Light'):
            self.multiworld.state.collect(self.world.create_item(name))
        self.assertTrue(self.world.get_location('Dark Beast Ganon Defeated').can_reach(self.multiworld.state))


class TestBeastsOnlyGoal(TestGoalPrerequisites):
    options = {'goal': 'all_divine_beasts', 'enable_the_master_trials_dlc': True,
               'boss_sanity': False}

    def test_trial_remains_optional_and_beasts_remain_required(self):
        self.assertEqual(len(self.world.goal_requirements), 4)
        self.assertTrue(all(entry['kind'] == 'boss' for entry in self.world.goal_requirements))
        self.assertEqual(sum(e['kind'] == 'boss' for e in self.world.active_combat), 5)


class TestAllChecksGoal(BotWTestBase):
    options = {'goal': 'all_checks', 'enable_the_master_trials_dlc': True}

    def test_every_enabled_check_is_required_except_the_goal_itself(self):
        slot = self.world.fill_slot_data()
        self.assertEqual(set(slot['goal_required_location_ids']),
                         {e['id'] for e in self.world.active_locations} - {slot['goal_location_id']})
        self.collect_all_but('Magnesis')
        self.assertFalse(self.world.get_location('Dark Beast Ganon Defeated').can_reach(self.multiworld.state))
        self.multiworld.state.collect(self.world.create_item('Magnesis'))
        self.assertTrue(self.world.get_location('Dark Beast Ganon Defeated').can_reach(self.multiworld.state))


class TestTrialOfTheSwordDisabled(BotWTestBase):
    options = {'enable_the_master_trials_dlc': True, 'trial_of_the_sword': False}

    def test_trial_checks_and_goal_requirement_are_removed(self):
        self.assertFalse(self.world.trial_of_the_sword_enabled)
        self.assertEqual(self.world.active_objectives, [])
        self.assertFalse(any(e['region'].startswith('Trial of the Sword (')
                             for e in self.world.active_locations))
        self.assertEqual(len(self.world.goal_requirements), 4)
        self.collect_all_but('Heart Container')
        self.assertTrue(self.world.get_location('Dark Beast Ganon Defeated').can_reach(self.multiworld.state))

    def test_other_master_trials_items_remain_enabled(self):
        pool = {item.name for item in self.multiworld.itempool}
        self.assertIn('Travel Medallion', pool)
        self.assertIn('Progressive Master Sword', pool)


class TestTrialDisabledWithAllChecksGoal(TestTrialOfTheSwordDisabled):
    options = {'goal': 'all_checks', 'enable_the_master_trials_dlc': True,
               'trial_of_the_sword': False}

    def test_trial_checks_and_goal_requirement_are_removed(self):
        self.assertFalse(self.world.trial_of_the_sword_enabled)
        self.assertEqual(self.world.active_objectives, [])
        self.assertFalse(any(e['region'].startswith('Trial of the Sword (')
                             for e in self.world.active_locations))
        slot = self.world.fill_slot_data()
        self.assertEqual(set(slot['goal_required_location_ids']),
                         {e['id'] for e in self.world.active_locations} - {slot['goal_location_id']})


class TestShrineSanityOnly(BotWTestBase):
    options = {'shrine_sanity': True, 'tower_sanity': False}

    def test_only_shrine_completions(self):
        self.assertEqual(len(self.world.active_completions), 120)
        self.assertTrue(all(e['kind'] == 'shrine' for e in self.world.active_completions))


class TestTowerSanityOnly(BotWTestBase):
    options = {'shrine_sanity': False, 'tower_sanity': True, 'skip_great_plateau': False}

    def test_all_towers_and_plateau_access_without_its_item(self):
        self.assertEqual(len(self.world.active_completions), 15)
        self.assertTrue(all(e['kind'] == 'tower' for e in self.world.active_completions))
        location = self.world.get_location('Great Plateau Tower')
        self.assertTrue(location.can_reach(self.multiworld.state))


class TestDlcOptionsOff(BotWTestBase):
    options = {'enable_the_master_trials_dlc': False, 'enable_the_champions_ballad_dlc': False}

    def test_dlc_items_and_checks_are_excluded(self):
        pool = {item.name for item in self.multiworld.itempool}
        self.assertNotIn('Travel Medallion', pool)
        self.assertNotIn('Progressive Master Sword', pool)
        self.assertNotIn('One-Hit Obliterator', pool)
        self.assertNotIn('Master Cycle Zero', pool)
        self.assertFalse(any("The Master Trials DLC" in entry.get('category', [])
                             or "The Champions' Ballad DLC" in entry.get('category', [])
                             for entry in self.world.active_locations))
        self.assertEqual(len(self.world.active_locations), 389)


class TestDlcOptionsOn(BotWTestBase):
    options = {'enable_the_master_trials_dlc': True, 'enable_the_champions_ballad_dlc': True}

    def test_dlc_items_and_checks_are_included(self):
        pool = {item.name for item in self.multiworld.itempool}
        self.assertIn('Travel Medallion', pool)
        self.assertIn('Progressive Master Sword', pool)
        self.assertIn('One-Hit Obliterator', pool)
        self.assertIn('Master Cycle Zero', pool)
        self.assertEqual(sum("The Master Trials DLC" in entry.get('category', [])
                             for entry in self.world.active_locations), 8)
        self.assertEqual(sum("The Champions' Ballad DLC" in entry.get('category', [])
                             for entry in self.world.active_locations), 18)
        self.assertEqual(len(self.world.active_locations), 415)


class TestMasterTrialsOnly(BotWTestBase):
    options = {'enable_the_master_trials_dlc': True, 'enable_the_champions_ballad_dlc': False}

    def test_only_master_trials_items_are_enabled(self):
        pool = {item.name for item in self.multiworld.itempool}
        self.assertIn('Travel Medallion', pool)
        self.assertIn('Progressive Master Sword', pool)
        self.assertNotIn('One-Hit Obliterator', pool)
        self.assertNotIn('Master Cycle Zero', pool)


class TestChampionsBalladOnly(BotWTestBase):
    options = {'enable_the_master_trials_dlc': False, 'enable_the_champions_ballad_dlc': True}

    def test_only_champions_ballad_items_are_enabled(self):
        pool = {item.name for item in self.multiworld.itempool}
        self.assertIn('One-Hit Obliterator', pool)
        self.assertIn('Master Cycle Zero', pool)
        self.assertNotIn('Travel Medallion', pool)
        self.assertNotIn('Progressive Master Sword', pool)


class TestCombatChecks(BotWTestBase):
    def test_base_encounter_counts_and_death_signals(self):
        combat = self.world.active_combat
        self.assertEqual(sum(e['kind'] == 'miniboss' for e in combat), 84)
        self.assertEqual(sum(e['kind'] == 'boss' for e in combat), 6)
        self.assertTrue(all(not e['watch_flag'].startswith(('Clear_Remains', 'MapTower_', 'IsGet_')) for e in combat))

    def test_minibosses_preserve_region_access(self):
        entry = next(e for e in self.world.active_combat if e['region'] == 'Central Hyrule')
        location = self.world.get_location(entry['name'])
        self.multiworld.state.collect(self.world.create_item('Progressive Remote Bomb'))
        self.assertFalse(location.can_reach(self.multiworld.state))
        self.multiworld.state.collect(self.world.create_item('Paraglider'))
        self.assertTrue(location.can_reach(self.multiworld.state))
