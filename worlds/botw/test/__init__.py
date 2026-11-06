from test.bases import WorldTestBase


class BotWTestBase(WorldTestBase):
    game = "Breath of the Wild"

    def collect_all_but(self, item_names, state=None):
        # Collect inventory, then earn local story events through their rules.
        # Granting locked event items directly would bypass the tested quests.
        if isinstance(item_names, str):
            item_names = (item_names,)
        state = state if state is not None else self.multiworld.state
        for item in self.multiworld.get_items():
            if item.code is not None and item.name not in item_names:
                state.collect(item)
        state.sweep_for_advancements()
