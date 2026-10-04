from BaseClasses import Item

class BotWItem(Item):
    game: str = "Breath of the Wild"

botw_items = {
    # Parsed from JDLKMR/BotW-APManual
    "Paraglider": 0x4000,
    "Master Sword": 0x4001,
}
