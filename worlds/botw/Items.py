from BaseClasses import Item, ItemClassification

from .reference import item_data


class BotWItem(Item):
    game = "Breath of the Wild"


botw_items = {name: entry["id"] for name, entry in item_data.items()}


def classification(entry):
    if entry.get("progression"):
        return ItemClassification.progression
    if entry.get("useful"):
        return ItemClassification.useful
    if entry.get("trap"):
        return ItemClassification.trap
    return ItemClassification.filler
