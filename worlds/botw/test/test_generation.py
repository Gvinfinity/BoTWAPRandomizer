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
