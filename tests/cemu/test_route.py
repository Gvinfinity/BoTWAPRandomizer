"""Coverage contracts: omitted checks or rewards must not produce a full pass."""
from importlib import import_module
from items import world_reference
from route import manifest


def test_full_route_contains_every_production_location_and_item_type():
    reference = world_reference()
    combat = import_module(reference.__package__ + '.static.combat').catalog()['locations']
    expected = [*reference.load_chests(), *reference.load_completions(), *combat]
    full = manifest('full')
    assert len(full) == len(expected)
    assert {case['location']['id'] for case in full} == {entry['id'] for entry in expected}
    assert {case['reward'] for case in full} == set(reference.item_data)
    assert all('position' in c['location'] or c['location']['kind'] in {'shrine','tower'} for c in full)


def test_partial_visits_each_kind_and_simple_visits_one_chest():
    assert {c['location']['kind'] for c in manifest('partial')} == {'chest','shrine','tower','miniboss','boss'}
    simple = manifest('simplified')
    assert len(simple) == 1 and simple[0]['location']['kind'] == 'chest'


def test_kind_filter_runs_complete_non_chest_catalog_without_chest_visits():
    selected = manifest('full', {'shrine', 'tower', 'miniboss', 'boss'})
    assert len(selected) == 228
    assert {case['location']['kind'] for case in selected} == {'shrine', 'tower', 'miniboss', 'boss'}
    assert len({case['location']['id'] for case in selected}) == len(selected)
    partial = manifest('partial', {'shrine', 'tower'})
    assert {case['location']['kind'] for case in partial} == {'shrine', 'tower'}
