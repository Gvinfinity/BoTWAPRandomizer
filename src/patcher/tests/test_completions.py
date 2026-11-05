import copy
import io

import evfl
import pytest
from evfl.actor import Actor
from evfl.common import ActorIdentifier, Argument, StringHolder
from evfl.container import Container
from evfl.entry_point import EntryPoint
from evfl.event import ActionEvent, Event, SubFlowEvent, SwitchEvent
from evfl.flowchart import Flowchart
from evfl.util import make_index, make_rindex

from src.patcher.core import ROOT
from botw_static.completions import (TOWER_ACTOR, TOWER_TEMPLATE, catalog, patch_shrine_flow,
                                     patch_tower_flow, patch_tower_map)
from botw_static.plan import validate_plan
from botw_static.protocol import seed_fingerprint
from botw_static.checks import check_actor_name
from botw_static.resource_sizes import allocation_template


def serialize(document):
    out = io.BytesIO(); assert document.write(out); return out.getvalue()


def read(raw):
    doc = evfl.EventFlow(); doc.read(raw); return doc.flowchart


def source(shrine=True):
    document = evfl.EventFlow(); document.name = 'Test'; flow = Flowchart(); flow.name = 'Test'
    document.flowchart = flow
    actor = Actor(); actor.identifier = ActorIdentifier('EventSystemActor') if shrine else ActorIdentifier(TOWER_TEMPLATE, 'TowerTerminal01')
    actor.concurrent_clips = 1; action = StringHolder('Demo_SetCurrentDungeonClearFlag' if shrine else 'Activate')
    actor.actions.append(action); flow.actors.append(actor)
    finish = Event(); finish.name = 'OriginalCompletion'; finish.data = ActionEvent()
    finish.data.actor = make_rindex(actor); finish.data.actor_action = make_rindex(action)
    finish.data.params = Container(); finish.data.params.data = {'Literal': TOWER_TEMPLATE,
        'Binding': ActorIdentifier(TOWER_TEMPLATE, 'TowerTerminal01'), 'Variable': Argument(TOWER_TEMPLATE)}
    flow.events.append(finish)
    start = finish
    if shrine:
        start = Event(); start.name = 'Reward'; start.data = SubFlowEvent()
        start.data.res_flowchart_name = 'GetDemo'; start.data.entry_point_name = 'GetItemByName'
        start.data.params = Container(); start.data.params.data = {'CheckTargetActorName': 'Obj_DungeonClearSeal'}
        start.data.nxt = make_index(finish); flow.events.append(start)
    entry = EntryPoint('Talk' if shrine else 'Demo004_0_01'); entry.main_event = make_index(start)
    flow.entry_points.append(entry)
    return serialize(document)


def walk_shrine(flow, dungeon):
    event = flow.entry_points[0].main_event.v; rewards = []; cleared = False
    while event:
        node = event.data
        if isinstance(node, SwitchEvent):
            event = node.cases[int(node.params.data['MapName'] == dungeon)].v
        else:
            if isinstance(node, SubFlowEvent): rewards.append(node.params.data['CheckTargetActorName'])
            if isinstance(node, ActionEvent):
                if str(node.actor_action)=='Demo_IncreasePorchItem': rewards.append(node.params.data['PorchItemName'])
                else: cleared = True
            event = node.nxt.v
    return rewards, cleared


def test_shrine_dispatch_replaces_only_tracked_orbs_and_preserves_completion():
    entries = [e for e in catalog()['locations'] if e['kind'] == 'shrine']
    patched = read(patch_shrine_flow(source(), entries))
    for entry in entries:
        rewards, cleared = walk_shrine(patched, entry['dungeon'])
        assert rewards == [check_actor_name(entry['id'])]
        assert cleared
    assert walk_shrine(patched, 'Dungeon120') == (['Obj_DungeonClearSeal'], True)
    assert walk_shrine(patched, 'MainField') == (['Obj_DungeonClearSeal'], True)


def test_tower_reward_runs_after_physical_activation_and_preserves_bindings():
    tower = next(e for e in catalog()['locations'] if e.get('tower') == 1)
    flow = read(patch_tower_flow(source(False), [tower]))
    public = next(e for e in flow.entry_points if e.name == 'Demo004_0_01')
    gate = public.main_event.v.data
    assert gate.params.data['FlagName'] == 'MapTower_01'
    assert gate.cases[1].v.data.params.data['PorchItemName'] == check_actor_name(tower['id'])
    node = gate.cases[0].v.data
    assert node.nxt.v.data.params.data['PorchItemName'] == check_actor_name(tower['id'])
    assert str(node.actor_action) == 'Activate'
    assert node.actor.v.identifier.name == TOWER_ACTOR
    assert node.params.data['Binding'].name == TOWER_ACTOR
    assert node.params.data['Variable'] == TOWER_TEMPLATE  # variable names remain valid


def test_only_bound_tower_terminals_are_replaced():
    data = {'Objs': [{'HashId': 1, 'UnitConfigName': TOWER_TEMPLATE, 'UniqueName': 'TowerTerminal01'},
                     {'HashId': 2, 'UnitConfigName': TOWER_TEMPLATE, 'UniqueName': 'HatenoTanmatsu'}]}
    patch_tower_map(data, [{'hash_id': 1}])
    assert data['Objs'][0]['UnitConfigName'] == TOWER_ACTOR
    assert data['Objs'][1]['UnitConfigName'] == TOWER_TEMPLATE
    with pytest.raises(ValueError, match='physical tower'):
        patch_tower_map(data, [{'hash_id': 2}])


def completion_plan(entry):
    locations = {str(entry['id']): check_actor_name(entry['id'])}
    return {'version': 1, 'game': 'Breath of the Wild', 'seed': 'test', 'player': 1,
            'locations': [copy.deepcopy(entry)], 'slot_data': {
                'protocol_version': 2, 'seed': 'test', 'player': 1, 'locations': locations,
                'check_actor_prefix': 'AP_Check_', 'seed_fingerprint': seed_fingerprint('test', 1, [entry['id']])}}


def test_event_only_plans_and_identity_validation():
    for entry in catalog()['locations']:
        plan = completion_plan(entry)
        assert validate_plan(plan) is plan
    plan = completion_plan(next(e for e in catalog()['locations'] if e['kind'] == 'tower'))
    plan['locations'][0]['terminals'][0]['hash_id'] += 1
    with pytest.raises(ValueError, match='catalog'):
        validate_plan(plan)


def test_completion_catalog_has_unique_ids_and_all_base_checks():
    entries = catalog()['locations']
    assert len({e['id'] for e in entries}) == len({e['name'] for e in entries}) == 135
    assert {e['dungeon'] for e in entries if e['kind'] == 'shrine'} == {f'Dungeon{i:03}' for i in range(120)}
    assert {e['tower'] for e in entries if e['kind'] == 'tower'} == set(range(1, 16))
    assert allocation_template('content/Actor/Pack/AP_TowerTerminal.sbactorpack').endswith(TOWER_TEMPLATE + '.sbactorpack')
    assert allocation_template('Actor/AIProgram/AP_TowerTerminal.baiprog') == 'Actor/AIProgram/DownloadTerminal.baiprog'


def test_monk_cinematic_and_dialogue_reward_owners_are_both_patched():
    assert {'Npc_DungeonPriest001', 'Demo033_0'} <= {e['flow'] for e in catalog()['events']}
