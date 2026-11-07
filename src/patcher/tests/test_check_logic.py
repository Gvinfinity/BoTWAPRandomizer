"""Regression coverage for physical requirements and valid native alternatives."""
import json

from src.patcher.core import ROOT
from botw_static.check_logic import apply_check_logic, CHEST_RULES, STRENGTH_SHRINES
from botw_static.requirements import parse_requirement


def evaluate(expression, owned):
    def visit(tree):
        if tree[0] == 'true':
            return True
        if tree[0] == 'item':
            return owned.get(tree[1], 0) >= tree[2]
        if tree[0] in ('all', 'any'):
            return (all if tree[0] == 'all' else any)(visit(c) for c in tree[1])
        raise AssertionError(tree)
    return visit(parse_requirement(expression))


def test_all_reported_chests_have_physical_requirements_and_alternatives():
    assert len(CHEST_RULES) == 9
    entries = json.loads((ROOT / 'worlds/botw/data/chests.json').read_text())['locations']
    found = {}
    for entry in entries:
        key = (entry['logical_map'], entry['hash_id'])
        if key in CHEST_RULES:
            rule = apply_check_logic(entry)['requires']
            assert not evaluate(rule, {})
            if entry['hash_id'] in {0xE1F9BB4B, 0x78F0EAF1}:
                for name in ('Progressive Remote Bomb', 'Paraglider', "Progressive Revali's Gale", "Revali's Gale"):
                    assert evaluate(rule, {name: 1})
                assert not evaluate(rule, {'Magnesis': 1})
            else:
                required = 'Magnesis' if entry['hash_id'] in {0x6260C604, 0xDF4FC4CF, 0x123AEF57} else 'Progressive Stasis' if entry['hash_id'] == 0xE382DE4C else 'Progressive Remote Bomb'
                assert evaluate(rule, {required: 1})
                assert not evaluate(rule, {'Cryonis': 1, 'Camera': 1})
            found[key] = rule
    assert found.keys() == CHEST_RULES.keys()


def test_ordinary_minibosses_allow_native_equipment_and_molduga_alternative():
    entries = json.loads((ROOT / 'worlds/botw/static/combat.json').read_text())['locations']
    for entry in entries:
        if entry['kind'] != 'miniboss':
            continue
        rule = apply_check_logic(entry)['requires']
        if entry['family'] == 'molduga':
            assert not evaluate(rule, {})
            assert evaluate(rule, {'Progressive Remote Bomb': 1})
            assert evaluate(rule, {'Medoh Flight Range Supplies': 1})
        else:
            assert evaluate(rule, {}), entry['name']


def test_scout_shrines_keep_exterior_gates_without_equipment_recommendations():
    entries = json.loads((ROOT / 'worlds/botw/static/completions.json').read_text())['locations']
    reviewed = []
    for entry in entries:
        if entry['name'].removesuffix(' Shrine') in STRENGTH_SHRINES:
            rule = apply_check_logic(entry)['requires']
            assert 'Upgradeable' not in rule and 'Armor Upgrade' not in rule
            reviewed.append(entry['name'])
    assert len(reviewed) == 20
    shoqa = next(e for e in entries if e['name'] == 'Shoqa Tatone Shrine')
    rule = apply_check_logic(shoqa)['requires']
    assert not evaluate(rule, {}) and evaluate(rule, {'Camera': 1})
    tutsuwa = next(e for e in entries if e['name'] == 'Tutsuwa Nima Shrine')
    rule = apply_check_logic(tutsuwa)['requires']
    assert not evaluate(rule, {}) and evaluate(rule, {"Dinraal's Scale": 1})


def test_logic_is_idempotent_and_never_mutates_input():
    for path in ('data/chests.json', 'static/completions.json', 'static/combat.json'):
        entries = json.loads((ROOT / 'worlds/botw' / path).read_text())['locations']
        for entry in entries:
            before = dict(entry)
            normalized = apply_check_logic(entry)
            assert normalized == apply_check_logic(normalized), entry['name']
            assert entry == before


def test_endgame_requires_gauntlet_runes_and_native_calamity_step_not_ap_bow():
    from botw_static.check_logic import BOSS_RULES, CALAMITY_ROUTE
    assert not evaluate(CALAMITY_ROUTE, {})
    assert not evaluate(CALAMITY_ROUTE, {'Progressive Remote Bomb': 1})
    assert evaluate(CALAMITY_ROUTE, {'Progressive Remote Bomb': 1, 'Magnesis': 1})
    assert evaluate(CALAMITY_ROUTE, {'Freed Vah Rudania': 1, 'Freed Vah Naboris': 1})
    assert evaluate(CALAMITY_ROUTE, {'Freed Vah Rudania': 1, 'Magnesis': 1})
    dark = BOSS_RULES['Dark Beast Ganon - Defeated']
    assert not evaluate(dark, {'Bow of Light': 1})
    assert evaluate(dark, {'Calamity Ganon Cleared Locally': 1})


def test_materialized_catalogs_match_the_authoritative_rules():
    for path in ('data/chests.json', 'static/completions.json', 'static/combat.json'):
        for entry in json.loads((ROOT / 'worlds/botw' / path).read_text())['locations']:
            if entry.get('region'):
                assert entry == apply_check_logic(entry), entry['name']
