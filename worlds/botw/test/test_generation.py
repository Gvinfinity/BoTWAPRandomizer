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
        self.assertEqual(data["seed_fingerprint"], seed_fingerprint(data["seed"], self.player, ids))
        plan = {"seed": data["seed"], "player": self.player,
                "locations": [{"id": code} for code in ids], "slot_data": data}
        self.assertIn(b"_AP_FlushPendingChecks:", build_seed_hook(plan))
