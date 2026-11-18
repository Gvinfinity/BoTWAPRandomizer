from itertools import product

from BaseClasses import CollectionState
from worlds.generic.Rules import set_rule

from . import BotWTestBase


class TestBeastBoarding(BotWTestBase):
    def test_town_requires_disguise_but_desert_and_outside_shrine_do_not(self):
        self.collect_all_but('Gerudo Top')
        state = self.multiworld.state
        self.assertTrue(self.world.get_region('Gerudo Desert').can_reach(state))
        self.assertTrue(self.world.get_location('Daqo Chisay Shrine').can_reach(state))
        self.assertFalse(self.world.get_region('Gerudo Town').can_reach(state))
        self.assertFalse(self.world.get_region('Vah Naboris Boarding').can_reach(state))
        state.collect(self.world.create_item('Gerudo Top'))
        self.assertTrue(self.world.get_region('Vah Naboris Boarding').can_reach(state))

    def test_all_normal_disguise_combinations(self):
        for head, legs in product(('Gerudo Veil', 'Thunder Helm'), ('Gerudo Sirwal', 'Sand Boots', 'Snow Boots')):
            with self.subTest(head=head, legs=legs):
                state = CollectionState(self.multiworld)
                for name in ('Paraglider', 'Gerudo Top', head, legs):
                    state.collect(self.world.create_item(name))
                self.assertTrue(self.world.get_region('Gerudo Town').can_reach(state))
                # A disguise alone does not replace recovery of the stolen helm.
                self.assertFalse(self.world.get_region('Vah Naboris Boarding').can_reach(state))

    def test_ruta_needs_waterfall_armor_and_cryonis(self):
        for omitted in ('Zora Armor', 'Cryonis'):
            with self.subTest(omitted=omitted):
                state = CollectionState(self.multiworld)
                self.collect_all_but(omitted, state)
                self.assertFalse(self.world.get_region('Vah Ruta Boarding').can_reach(state))
                self.assertFalse(self.world.get_region('Divine Beast Vah Ruta').can_reach(state))
                state.collect(self.world.create_item(omitted))
                self.assertTrue(self.world.get_region('Vah Ruta Boarding').can_reach(state))

    def test_rudania_needs_cannon_bombs_and_boulder_clearance(self):
        for omitted in ('Progressive Remote Bomb', 'Progressive Stasis'):
            with self.subTest(omitted=omitted):
                state = CollectionState(self.multiworld)
                self.collect_all_but(omitted, state)
                self.assertFalse(self.world.get_region('Vah Rudania Boarding').can_reach(state))
                state.collect(self.world.create_item(omitted))
                self.assertTrue(self.world.get_region('Vah Rudania Boarding').can_reach(state))

    def test_naboris_needs_magnesis_for_kohga_even_with_helm(self):
        self.collect_all_but('Magnesis')
        state = self.multiworld.state
        self.assertTrue(state.has('Thunder Helm', self.player))
        self.assertFalse(state.has('Naboris Helm Returned', self.player))
        self.assertFalse(self.world.get_region('Vah Naboris Boarding').can_reach(state))
        state.collect(self.world.create_item('Magnesis'))
        self.assertTrue(state.has('Naboris Helm Returned', self.player))
        self.assertTrue(self.world.get_region('Vah Naboris Boarding').can_reach(state))

    def test_native_supplies_do_not_require_ap_bows_or_arrow_bundles(self):
        state = self.multiworld.state
        # Teba's training supplies the attack arrows; a bow is available at the
        # Flight Range. Riju similarly supplies arrows after recovering the helm.
        for name in ('Paraglider', 'Zora Armor', 'Cryonis', 'Thunder Helm',
                     'Gerudo Top', 'Sand Boots', 'Magnesis'):
            state.collect(self.world.create_item(name))
        for beast in ('Vah Medoh', 'Vah Ruta', 'Vah Naboris'):
            self.assertTrue(self.world.get_region(f'{beast} Boarding').can_reach(state), beast)
        self.assertFalse(self.world.get_region('Divine Beast Vah Medoh').can_reach(state))
        state.collect(self.world.create_item('Vah Medoh Controls'))
        self.assertFalse(self.world.get_region('Divine Beast Vah Medoh').can_reach(state))
        state.collect(self.world.create_item('Progressive Remote Bomb'))
        self.assertTrue(self.world.get_region('Divine Beast Vah Medoh').can_reach(state))

    def test_controls_do_not_substitute_for_boarding(self):
        state = self.multiworld.state
        for name in ('Vah Medoh', 'Vah Ruta', 'Vah Rudania', 'Vah Naboris'):
            state.collect(self.world.create_item(name + ' Controls'))
            self.assertFalse(self.world.get_region('Divine Beast ' + name).can_reach(state))

    def test_lakna_rokee_camera_requirement_matches_chest_and_monk(self):
        self.collect_all_but('Camera')
        for name in ('Lakna Rokee Shrine', 'Lakna Rokee Shrine - Chest'):
            self.assertFalse(self.world.get_location(name).can_reach(self.multiworld.state))
        self.multiworld.state.collect(self.world.create_item('Camera'))
        for name in ('Lakna Rokee Shrine', 'Lakna Rokee Shrine - Chest'):
            self.assertTrue(self.world.get_location(name).can_reach(self.multiworld.state))


class TestDlcStoryMilestones(BotWTestBase):
    options = {'enable_the_master_trials_dlc': True, 'enable_the_champions_ballad_dlc': True}

    def test_champion_and_cleared_items_cannot_skip_beast_quests(self):
        self.collect_all_but('Vah Ruta Controls')
        state = self.multiworld.state
        self.assertTrue(state.has("Progressive Mipha's Grace", self.player))
        self.assertTrue(state.has('Vah Ruta Cleared', self.player))
        self.assertFalse(state.has('Freed Vah Ruta', self.player))
        self.assertFalse(self.world.get_region('Great Plateau (One-Hit Obliterator)').can_reach(state))
        state.collect(self.world.create_item('Vah Ruta Controls'))
        self.assertTrue(self.world.get_region('Great Plateau (One-Hit Obliterator)').can_reach(state))

    def test_upgrades_cannot_skip_obliterator_stage_or_unlock_final_trial(self):
        self.collect_all_but('One-Hit Obliterator')
        state = self.multiworld.state
        self.assertTrue(state.has("Progressive Revali's Gale", self.player, 2))
        self.assertFalse(self.world.get_location('Noe Rajee Shrine - Chest').can_reach(state))
        self.assertFalse(self.world.get_region('Final Trial').can_reach(state))
        state.collect(self.world.create_item('One-Hit Obliterator'))
        self.assertTrue(self.world.get_region('Final Trial').can_reach(state))

    def test_trial_tiers_cannot_skip_beginning_clear(self):
        set_rule(self.world.get_location('Beginning Trials Completed'), lambda state: False)
        self.collect_all_but([])
        state = self.multiworld.state
        self.assertTrue(state.has('Progressive Master Sword', self.player, 4))
        self.assertTrue(self.world.get_region('Trial of the Sword (Beginning Trials)').can_reach(state))
        self.assertFalse(self.world.get_region('Trial of the Sword (Middle Trials)').can_reach(state))
        self.assertFalse(self.world.get_region('Trial of the Sword (Final Trials)').can_reach(state))

    def test_final_trial_requires_every_song(self):
        set_rule(self.world.get_location("Completed Urbosa's Song"), lambda state: False)
        self.collect_all_but([])
        state = self.multiworld.state
        self.assertTrue(state.has("Completed Revali's Song", self.player))
        self.assertFalse(self.world.get_region('Final Trial').can_reach(state))


class TestPhysicalCheckRules(BotWTestBase):
    def test_reported_chests_require_their_physical_capabilities(self):
        from ..Locations import chest_data
        for entry in chest_data:
            if entry['hash_id'] not in {0xF5EA1473, 0xA2A08719, 0xE1F9BB4B, 0x78F0EAF1, 0x6260C604, 0xDF4FC4CF, 0x123AEF57, 0x68BE4D6A, 0xE382DE4C}:
                continue
            location = self.world.get_location(entry['name'])
            self.assertFalse(location.can_reach(self.multiworld.state), entry['name'])
        self.multiworld.state.collect(self.world.create_item('Magnesis'))
        for hash_id in (0x6260C604, 0xDF4FC4CF, 0x123AEF57):
            entry = next(e for e in chest_data if e['hash_id'] == hash_id)
            self.assertTrue(self.world.get_location(entry['name']).can_reach(self.multiworld.state))
        bomb_chest = next(e for e in chest_data if e['hash_id'] == 0xF5EA1473)
        self.assertFalse(self.world.get_location(bomb_chest['name']).can_reach(self.multiworld.state))
        self.multiworld.state.collect(self.world.create_item('Progressive Remote Bomb'))
        self.assertTrue(self.world.get_location(bomb_chest['name']).can_reach(self.multiworld.state))

    def test_native_weapons_can_defeat_a_hinox_without_ap_weapons_or_bombs(self):
        self.multiworld.state.collect(self.world.create_item('Paraglider'))
        entry = next(e for e in self.world.active_combat if e.get('family') == 'hinox')
        self.assertTrue(self.world.get_location(entry['name']).can_reach(self.multiworld.state))
        self.assertFalse(self.multiworld.state.has('Master Sword', self.player))
        self.assertFalse(self.multiworld.state.has('Progressive Remote Bomb', self.player))

    def test_scout_does_not_require_randomized_armor_upgrades(self):
        self.multiworld.state.collect(self.world.create_item('Paraglider'))
        self.assertTrue(self.world.get_location('Chaas Qeta Shrine').can_reach(self.multiworld.state))
        self.assertFalse(self.multiworld.state.has('Progressive Armor Upgrade', self.player))
        self.assertFalse(self.world.get_location('Shoqa Tatone Shrine').can_reach(self.multiworld.state))
        self.multiworld.state.collect(self.world.create_item('Camera'))
        self.assertTrue(self.world.get_location('Shoqa Tatone Shrine').can_reach(self.multiworld.state))

    def test_plateau_cold_food_does_not_require_ap_clothing(self):
        self.assertFalse(self.world.get_location('Keh Namut Shrine').can_reach(self.multiworld.state))
        self.multiworld.state.collect(self.world.create_item('Cryonis'))
        self.assertTrue(self.world.get_location('Keh Namut Shrine').can_reach(self.multiworld.state))

    def test_cleared_reward_cannot_skip_voo_lota_quest(self):
        from BaseClasses import CollectionState
        state = CollectionState(self.multiworld)
        for name in ('Paraglider', 'Vah Medoh Cleared'):
            state.collect(self.world.create_item(name))
        self.assertFalse(self.world.get_location('Voo Lota Shrine').can_reach(state))
        self.collect_all_but('Vah Medoh Controls', state)
        self.assertFalse(self.world.get_location('Voo Lota Shrine').can_reach(state))
        state.collect(self.world.create_item('Vah Medoh Controls'))
        self.assertTrue(self.world.get_location('Voo Lota Shrine').can_reach(state))


class TestEntranceSideChestRoutes(BotWTestBase):
    def test_initial_mirro_shaz_and_wahgo_katta_chests_need_no_local_rune(self):
        self.multiworld.state.collect(self.world.create_item('Paraglider'))
        state = self.multiworld.state
        self.assertTrue(self.world.get_location('Mirro Shaz Shrine - Chest 1').can_reach(state))
        self.assertFalse(self.world.get_location('Mirro Shaz Shrine - Chest 3').can_reach(state))
        self.assertTrue(self.world.get_location('Wahgo Katta Shrine - Chest').can_reach(state))
        self.assertFalse(self.world.get_location('Oman Au Shrine - Chest').can_reach(state))
        state.collect(self.world.create_item('Progressive Stasis'))
        self.assertTrue(self.world.get_location('Mirro Shaz Shrine - Chest 3').can_reach(state))
