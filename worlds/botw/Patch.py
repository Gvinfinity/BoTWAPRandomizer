"""Seed output follows AP's custom APPatch container convention.

Applying a BotW patch requires several extracted content roots, so it is a
custom patch rather than a delta against one monolithic ROM file.
"""
import json

from worlds.Files import APPatch

from .static.plan import validate_plan


class BotWPatch(APPatch):
    game = "Breath of the Wild"
    patch_file_ending = ".apbotw"
    procedure = "custom"

    def __init__(self, *args, plan=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.plan = plan

    def write_contents(self, archive):
        validate_plan(self.plan)
        super().write_contents(archive)
        archive.writestr("botw_patch.json", json.dumps(self.plan, indent=2, sort_keys=True))

    def read_contents(self, archive):
        super().read_contents(archive)
        self.plan = validate_plan(json.loads(archive.read("botw_patch.json")))
