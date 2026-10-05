from . import BotWTestBase


class TestBotWGeneration(BotWTestBase):
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
