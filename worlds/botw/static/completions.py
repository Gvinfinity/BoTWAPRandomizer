"""Physical completion event patches, independent of incoming AP item grants."""
from __future__ import annotations

import binascii
import hashlib
import io
import json
from importlib.resources import files

from .checks import check_actor_name
from .resources import binary_modules, decode_byml, decompress, encode_byml, rewrap

TOWER_ACTOR = 'AP_TowerTerminal'
TOWER_TEMPLATE = 'FldObj_DownloadTerminal_A_01'


def catalog():
    # This module is also loaded as botw_static by the standalone patcher.
    return json.loads(files(__package__).joinpath('completions.json').read_text())


def _evfl():
    try:
        import evfl
        return evfl
    except ImportError as exc:
        raise RuntimeError('Install evfl>=1.2.0,<2 to patch shrine/tower events') from exc


def _reward(flow, name, location, nxt=None, silent=False):
    evfl = _evfl()
    from evfl.container import Container
    from evfl.event import Event, SubFlowEvent
    from evfl.util import make_index
    event = Event(); event.name = name
    if silent:
        from evfl.actor import Actor
        from evfl.common import ActorIdentifier, StringHolder
        from evfl.event import ActionEvent
        from evfl.util import make_rindex
        actor = next((a for a in flow.actors if a.identifier.name == 'EventSystemActor'), None)
        if actor is None:
            actor = Actor(); actor.identifier = ActorIdentifier('EventSystemActor'); actor.concurrent_clips = 1
            flow.actors.append(actor)
        action = next((a for a in actor.actions if a.v == 'Demo_IncreasePorchItem'), None)
        if action is None:
            action = StringHolder('Demo_IncreasePorchItem'); actor.actions.append(action)
        event.data = ActionEvent(); event.data.actor = make_rindex(actor); event.data.actor_action = make_rindex(action)
        event.data.params = Container()
        event.data.params.data = dict(IsWaitFinish=True, PorchItemName=check_actor_name(location), Value=1)
        event.data.nxt = make_index(nxt); flow.events.append(event)
        return event
    event.data = SubFlowEvent()
    event.data.res_flowchart_name = 'GetDemo'
    event.data.entry_point_name = 'GetItemByName'
    event.data.params = Container()
    event.data.params.data = dict(IsInvalidOpenPouch=False, CheckTargetActorName=check_actor_name(location))
    event.data.nxt = make_index(nxt)
    flow.events.append(event)
    return event


def patch_shrine_flow(raw, locations):
    evfl = _evfl()
    from evfl.common import StringHolder
    from evfl.container import Container
    from evfl.event import Event, SubFlowEvent, SwitchEvent
    from evfl.util import make_index, make_rindex
    document = evfl.EventFlow(); document.read(raw); flow = document.flowchart
    targets = [e for e in flow.events if isinstance(e.data, SubFlowEvent) and e.data.params
               and e.data.params.data.get('CheckTargetActorName') == 'Obj_DungeonClearSeal']
    if len(targets) != 1:
        raise ValueError('Expected one monk Spirit Orb grant in the source event')
    original = targets[0]
    actor = next(a for a in flow.actors if a.identifier.name == 'EventSystemActor')
    query = next((q for q in actor.queries if q.v == 'CheckCurrentMap'), None)
    if query is None:
        query = StringHolder('CheckCurrentMap'); actor.queries.append(query)
    fallback = Event(); fallback.name = 'AP_UntrackedShrineReward'; fallback.data = original.data
    flow.events.append(fallback)
    next_case = fallback
    for entry in reversed(sorted(locations, key=lambda e: e['dungeon'])):
        reward = _reward(flow, f'AP_ShrineReward_{entry["dungeon"]}', entry['id'], fallback.data.nxt.v, silent=True)
        branch = Event(); branch.name = f'AP_ShrineMap_{entry["dungeon"]}'; branch.data = SwitchEvent()
        branch.data.actor = make_rindex(actor); branch.data.actor_query = make_rindex(query)
        branch.data.params = Container(); branch.data.params.data = {'MapName': entry['dungeon']}
        branch.data.cases = {0: make_rindex(next_case), 1: make_rindex(reward)}
        flow.events.append(branch); next_case = branch
    original.data = next_case.data
    flow.events.remove(next_case)
    return _write(document)


def patch_tower_flow(raw, locations):
    evfl = _evfl()
    from evfl.common import ActorIdentifier
    from evfl.util import make_index
    document = evfl.EventFlow(); document.read(raw); flow = document.flowchart
    # The tower-only clone keeps all original model/animation resources. Bind
    # this event's actors and literal identifiers to that clone, preserving args.
    selected = {f'TowerTerminal{e["tower"]:02}' for e in locations}
    if any(e['tower'] == 7 for e in locations): selected.add('TowerTerminal07_Before')
    for actor in flow.actors:
        if actor.identifier.name == TOWER_TEMPLATE and actor.identifier.sub_name in selected:
            actor.identifier.name = TOWER_ACTOR
    for event in flow.events:
        params = getattr(event.data, 'params', None)
        if params:
            selected_context = any((isinstance(v, ActorIdentifier) and v.sub_name in selected)
                                   or (type(v) is str and v in selected) for v in params.data.values())
            for key, value in list(params.data.items()):
                if isinstance(value, ActorIdentifier) and value.name == TOWER_TEMPLATE and value.sub_name in selected:
                    params.data[key] = ActorIdentifier(TOWER_ACTOR, value.sub_name)
                elif selected_context and type(value) is str and value == TOWER_TEMPLATE:
                    params.data[key] = TOWER_ACTOR
    for entry in locations:
        names = [f'Demo004_0_{entry["tower"]:02}'] if entry['tower'] != 7 else [
            'Demo004_0_FirstTower', 'MapTower07_After']
        for name in names:
            source = next((e for e in flow.entry_points if e.name == name), None)
            if source is None: raise ValueError(f'Missing tower event entry point: {name}')
            reward = _reward(flow, 'AP_Reward_' + name, entry['id'], silent=True)
            # Keep entry point names and argument scopes intact. Follow only the
            # outer continuation of forks; branch returns belong to their join.
            from evfl.event import ForkEvent, SwitchEvent
            pending = [source.main_event.v]; visited = set(); tails = []
            while pending:
                event = pending.pop()
                if event is None or event in visited: continue
                visited.add(event); node = event.data
                if isinstance(node, ForkEvent): pending.append(node.join.v)
                elif isinstance(node, SwitchEvent): pending.extend(case.v for case in node.cases.values())
                elif node.nxt.v is None: tails.append(node)
                else: pending.append(node.nxt.v)
            if not tails: raise ValueError('Tower activation has no return continuation')
            for tail in tails: tail.nxt = make_index(reward)
            # An AP tower item has already revealed this map. Re-running the
            # vanilla download cinematic in that state can wait for a map-open
            # animation which will never start. Physical reactivation only needs
            # to emit its check, while an unopened vanilla tower keeps its flow.
            from evfl.common import StringHolder
            from evfl.container import Container
            from evfl.event import Event
            from evfl.util import make_rindex
            actor = next(a for a in flow.actors if a.identifier.name == 'EventSystemActor')
            query = next((q for q in actor.queries if q.v == 'CheckFlag'), None)
            if query is None: query = StringHolder('CheckFlag'); actor.queries.append(query)
            gate = Event(); gate.name = 'AP_Reactivation_' + name; gate.data = SwitchEvent()
            gate.data.actor = make_rindex(actor); gate.data.actor_query = make_rindex(query)
            gate.data.params = Container(); gate.data.params.data = {'FlagName': f'MapTower_{entry["tower"]:02}'}
            gate.data.cases = {0: make_rindex(source.main_event.v), 1: make_rindex(reward)}
            flow.events.append(gate); source.main_event = make_index(gate)
    return _write(document)


def _write(document):
    out = io.BytesIO()
    if not document.write(out): raise ValueError('Could not serialize patched completion flow')
    return out.getvalue()


def event_replacements(dump, locations):
    shrines = [e for e in locations if e.get('kind') == 'shrine']
    towers = [e for e in locations if e.get('kind') == 'tower']
    replacements = {}
    for source in catalog()['events']:
        entries = shrines if source['flow'] in {'Npc_DungeonPriest001', 'Demo033_0'} else towers
        if not entries: continue
        raw = dump.read(source['resource'])
        if hashlib.sha256(raw).hexdigest() != source['sha256']:
            raise ValueError(f'Game version/completion event mismatch: {source["resource"]}')
        patched = (patch_shrine_flow if source['flow'] in {'Npc_DungeonPriest001', 'Demo033_0'} else patch_tower_flow)(raw, entries)
        outer, _, member = source['resource'].partition('!')
        replacements.setdefault(outer, {})[member] = patched
    return replacements


def patch_tower_map(data, entries):
    expected = {e['hash_id'] for e in entries}
    found = set()
    for obj in data.get('Objs', []):
        if int(obj['HashId']) in expected:
            if obj['UnitConfigName'] != TOWER_TEMPLATE or not str(obj.get('UniqueName', '')).startswith('TowerTerminal'):
                raise ValueError('Tower terminal binding does not identify a physical tower')
            obj['UnitConfigName'] = TOWER_ACTOR; found.add(int(obj['HashId']))
    if found != expected: raise ValueError('A tower terminal is missing from its source map')


def build_tower_actor(dump, actor_info):
    oead, _ = binary_modules()
    original = dump.read(f'content/Actor/Pack/{TOWER_TEMPLATE}.sbactorpack')
    archive = oead.Sarc(decompress(original)); members = {f.name: f for f in archive.get_files()}
    writer = oead.SarcWriter.from_sarc(archive)
    old_link = f'Actor/ActorLink/{TOWER_TEMPLATE}.bxml'
    link = oead.aamp.ParameterIO.from_binary(members[old_link].data)
    link.objects['LinkTarget'].params['AIProgramUser'] = oead.aamp.Parameter(TOWER_ACTOR)
    writer.files[f'Actor/ActorLink/{TOWER_ACTOR}.bxml'] = bytes(link.to_binary()); del writer.files[old_link]
    ai = oead.aamp.ParameterIO.from_binary(members['Actor/AIProgram/DownloadTerminal.baiprog'].data)
    count = 0
    for node in ai.lists['AI'].lists.values():
        if str(node.objects['Def'].params['ClassName'].v) == 'WarpActivateTerminal':
            node.objects['SInst'].params['IsAbleToReboot'] = oead.aamp.Parameter(True); count += 1
    if count != 1: raise ValueError('Expected one tower activation controller in the actor template')
    writer.files[f'Actor/AIProgram/{TOWER_ACTOR}.baiprog'] = bytes(ai.to_binary())
    del writer.files['Actor/AIProgram/DownloadTerminal.baiprog']
    info = decode_byml(actor_info)
    entries = {int(h): a for h, a in zip(info['Hashes'], info['Actors'])}
    clone = oead.byml.from_text(oead.byml.to_text(next(a for a in info['Actors'] if a['name'] == TOWER_TEMPLATE)))
    clone['name'] = TOWER_ACTOR
    crc = binascii.crc32(TOWER_ACTOR.encode())
    if crc in entries: raise ValueError('Tower actor CRC collision')
    entries[crc] = clone
    info['Hashes'] = oead.byml.Array([oead.U32(h) if h > 0x7FFFFFFF else oead.S32(h) for h in sorted(entries)])
    info['Actors'] = oead.byml.Array([entries[h] for h in sorted(entries)])
    return {f'content/Actor/Pack/{TOWER_ACTOR}.sbactorpack': rewrap(bytes(writer.write()[1]), original),
            'content/Actor/ActorInfo.product.sbyml': encode_byml(info, actor_info)}
