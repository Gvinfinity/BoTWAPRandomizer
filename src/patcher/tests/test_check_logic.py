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
    reported = {0xF5EA1473, 0xA2A08719, 0xE1F9BB4B, 0x78F0EAF1, 0x6260C604, 0xDF4FC4CF, 0x123AEF57, 0x68BE4D6A, 0xE382DE4C}
    entries = json.loads((ROOT / 'worlds/botw/data/chests.json').read_text())['locations']
    found = {}
    for entry in entries:
        key = (entry['logical_map'], entry['hash_id'])
        if entry['hash_id'] in reported:
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
    assert {key[1] for key in found} == reported


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


def test_route_annotations_bind_all_187_checks_to_exact_actors():
    from botw_static.check_logic import ROUTES
    catalog = json.loads((ROOT / 'worlds/botw/data/chests.json').read_text())['locations']
    by_key = {(e['logical_map'], e['hash_id']): e for e in catalog}
    assert len(ROUTES) == 187
    assert len(CHEST_RULES) == 187
    for route in ROUTES:
        entry = by_key[(route['logical_map'], int(route['hash_id'], 16))]
        assert route['check_id'] == entry['id']
        assert route['original_actor'] == entry['original_actor']
        assert route['position'] == entry['position']
        assert route['requires'] == entry['requires']
        assert route['sources'] and route['route']
        assert not route['gameplay_verified']


def test_underwater_river_chests_and_cold_wooden_pond_chest():
    catalog = json.loads((ROOT / 'worlds/botw/data/chests.json').read_text())['locations']
    by_hash = {e['hash_id']: e for e in catalog if e.get('region') == 'Great Plateau'}
    for hash_id in (0xC986043B, 0xDE46BD48):
        rule = by_hash[hash_id]['requires']
        assert not evaluate(rule, {})
        assert evaluate(rule, {'Magnesis': 1})
    rule = by_hash[0xB326B249]['requires']
    assert not evaluate(rule, {'Magnesis': 1, 'Native Plateau Cold Protection Supplies': 1})
    assert evaluate(rule, {'Cryonis': 1, 'Native Plateau Cold Protection Supplies': 1})
    # These three metal chests are on dry ground inside the waterfall cave.
    for hash_id in (0x24A00436, 0x53A734A0, 0xC3182931):
        assert evaluate(by_hash[hash_id]['requires'], {})


def test_final_trial_is_champions_ballad_dungeon_and_bonus_chests_are_dlc():
    catalog = json.loads((ROOT / 'worlds/botw/data/chests.json').read_text())['locations']
    final = [e for e in catalog if e.get('binding') == 'champions-ballad-finaltrial-hash']
    assert len(final) == 7
    assert all(e['region'] == 'Final Trial' and e['category'] == ["The Champions' Ballad DLC"] for e in final)
    assert all(e['resource_variants'] for e in final)
    bonus = [e for e in catalog if e['hash_id'] in {0x2D3FEE5E, 0x1C3B3C05, 0xF3F989AC}]
    assert len(bonus) == 3
    assert all('The Master Trials DLC' in e['category'] for e in bonus)
