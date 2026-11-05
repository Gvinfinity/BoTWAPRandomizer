"""Save-backed goal objectives that cannot be granted as inventory items."""

BEAST_DEFEATS = (
    'Windblight Ganon - Defeated', 'Fireblight Ganon - Defeated',
    'Waterblight Ganon - Defeated', 'Thunderblight Ganon - Defeated',
)
SWORD_TRIAL = {
    'id': 0xC2100000, 'kind': 'objective',
    'name': 'Trial of the Sword - Completed',
    'region': 'Trial of the Sword (Final Trials)',
    'category': ['The Master Trials DLC'], 'requires': '',
    'watch_flag': '100enemy_Clear_Senior', 'watch_type': 'bool', 'watch_threshold': 1,
}
