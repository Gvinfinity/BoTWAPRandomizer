"""Export effective BotW APWorld dependencies using an Archipelago checkout.

Example (use the checkout's Python environment):
  python tools/export_logic_graph.py --archipelago /path/to/Archipelago --all-locations
  python tools/export_logic_graph.py --archipelago /path/to/Archipelago --options options.json

Imports the actual World and AP classes, calls generate_early/create_regions/set_rules,
then retains compiler-produced requirement trees and traces wrapper rules. No game rules
are reimplemented here. Compiler calls expose their own effective trees during tracing; Location.can_reach
is intercepted to retain references instead of recursively expanding the world.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'worlds/botw'


class Branch(Exception):
    def __init__(self, predicate):
        self.predicate = predicate


class Count:
    def __init__(self, state, names):
        self.state, self.names = state, names

    def __radd__(self, other):
        if other == 0:
            return self
        return NotImplemented

    def __add__(self, other):
        return Count(self.state, self.names + other.names)

    def __ge__(self, minimum):
        return self.state.ask(('count', tuple(sorted(self.names)), minimum))


class TraceState:
    def __init__(self, choices):
        self.choices = choices

    def ask(self, predicate):
        if predicate not in self.choices:
            raise Branch(predicate)
        return self.choices[predicate]

    def has(self, name, player, count=1):
        return self.ask(('item', name, count))

    def count(self, name, player):
        return Count(self, (name,))


class Graph:
    def __init__(self):
        self.nodes, self.edges, self.gates = {}, set(), {}

    def node(self, kind, name, **attributes):
        key = f'{kind}:{name}'
        self.nodes.setdefault(key, dict(id=key, type=kind))
        self.nodes[key].update(attributes)
        return key

    def gate(self, kind, children):
        children = set(children)
        if kind == 'and':
            if False in children:
                return False
            children.discard(True)
        else:
            if True in children:
                return True
            children.discard(False)
        if not children:
            return kind == 'and'
        if len(children) == 1:
            return next(iter(children))
        signature = (kind, tuple(sorted(children)))
        if signature in self.gates:
            return self.gates[signature]
        key = self.node(kind, str(len(self.gates) + 1))
        self.gates[signature] = key
        self.edges.update((key, child) for child in children)
        return key

    def requirement(self, tree):
        operator = tree[0]
        if operator == 'true':
            return True
        if operator in ('all', 'any'):
            return self.gate('and' if operator == 'all' else 'or',
                             (self.requirement(child) for child in tree[1]))
        if operator == 'sum':
            return self.predicate(('count', tree[1], tree[2]))
        if operator == 'item':
            return self.predicate(tree)
        raise ValueError(tree)

    def predicate(self, p):
        if p[0] == 'compiled':
            return self.requirement(p[1])
        if p[0] == 'location':
            return self.node('location', p[1])
        if p[0] == 'item' and p[2] == 1:
            return self.node('item', p[1])
        names = (p[1],) if p[0] == 'item' else p[1]
        key = self.node('count', json.dumps([names, p[2]]), minimum=p[2])
        # Keep multiplicities if a future category contains the same name twice.
        for name, weight in Counter(names).items():
            if weight != 1:
                raise ValueError('Repeated category member: ' + name)
            self.edges.add((key, self.node('item', name)))
        return key

    def trace(self, rule, choices=None):
        choices = choices or {}
        try:
            return bool(rule(TraceState(choices)))
        except Branch as branch:
            p = branch.predicate
            low = self.trace(rule, choices | {p: False})
            high = self.trace(rule, choices | {p: True})
            if low == high:
                return low
            condition = self.predicate(p)
            if low is False:
                return self.gate('and', (condition, high))
            if high is True:
                return self.gate('or', (condition, low))
            negated = self.node('not', condition)
            self.edges.add((negated, condition))
            return self.gate('or', (self.gate('and', (condition, high)),
                                    self.gate('and', (negated, low))))

    def attach(self, owner, dependency):
        if dependency is not True:
            self.edges.add((owner, dependency if dependency is not False
                            else self.node('false', 'unreachable')))

    def export(self, world):
        """Named dependencies with explicit inline AND/OR gates."""
        from worlds.botw.reference import item_data, item_groups
        category_names = {tuple(sorted(names)): name for name, names in sorted(item_groups.items(), reverse=True)}
        used_categories = {}
        adjacency = {}
        for owner, dependency in sorted(self.edges):
            adjacency.setdefault(owner, []).append(dependency)

        def group(operator, children):
            gate_type = 'AND' if operator == 'all' else 'OR'
            result = []
            for child in children:
                values = (child['inputs'] if isinstance(child, dict) and
                          child.get('gate') == gate_type else [child])
                for value in values:
                    if value not in result:
                        result.append(value)
            if not result:
                return operator == 'all'
            return result[0] if len(result) == 1 else {'gate': gate_type, 'inputs': result}

        def expression(key):
            kind = self.nodes[key]['type']
            children = adjacency.get(key, [])
            if kind in ('and', 'or'):
                return group('all' if kind == 'and' else 'any', map(expression, children))
            if kind == 'not':
                return {'not': expression(children[0])}
            if kind == 'false':
                return False
            if kind == 'count':
                names = tuple(sorted(child.removeprefix('item:') for child in children))
                if names in category_names:
                    name = category_names[names]
                    used_categories[name] = children
                    return {'ref': 'category:' + name, 'count': self.nodes[key]['minimum']}
                if len(children) == 1:
                    return {'ref': children[0], 'count': self.nodes[key]['minimum']}
                return {'count': self.nodes[key]['minimum'], 'of': [{'ref': child} for child in children]}
            if kind == 'entrance':
                return group('all', map(expression, children))
            return {'ref': key}

        result = []
        for key, value in sorted(self.nodes.items()):
            kind = value['type']
            if kind not in ('region', 'location', 'item', 'goal'):
                continue
            row = dict(value)
            children = adjacency.get(key, [])
            if kind == 'item' and not children:
                name = key.removeprefix('item:')
                row['acquisition'] = ('received' if name in item_data and
                                      world.category_enabled(item_data[name]) else 'unavailable')
            else:
                row['requires'] = group('all', map(expression, children))
            result.append(row)
        result.extend({'id': 'category:' + name, 'type': 'category',
                       'members': [{'ref': child} for child in children]}
                      for name, children in sorted(used_categories.items()))
        # All references resolve to named nodes; no anonymous gate IDs remain.
        ids = {row['id'] for row in result}
        def check(value):
            if isinstance(value, dict):
                if 'ref' in value:
                    assert value['ref'] in ids, value
                for child in value.values():
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)
        check(result)
        return {'nodes': result}


def load_world(checkout, overrides):
    sys.path.insert(0, str(checkout))
    # Avoid AP's unrelated all-world discovery. All imported framework classes
    # and BotW modules are the real files, not substitutes or AST copies.
    package = ModuleType('worlds')
    package.__path__ = [str(checkout / 'worlds')]
    sys.modules['worlds'] = package
    spec = importlib.util.spec_from_file_location(
        'worlds.botw', BASE / '__init__.py', submodule_search_locations=[str(BASE)])
    botw = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = botw
    package.botw = botw
    spec.loader.exec_module(botw)
    from BaseClasses import MultiWorld, CollectionState
    hints = botw.BotWOptions.type_hints
    unknown = overrides.keys() - hints.keys()
    if unknown:
        raise ValueError(f'Unknown options: {sorted(unknown)}')
    multiworld = MultiWorld(1)
    multiworld.game[1] = botw.BotWWorld.game
    multiworld.player_name = {1: 'Logic Export'}
    multiworld.set_seed(0)
    args = SimpleNamespace(**{name: {1: option.from_any(overrides.get(name, option.default))}
                              for name, option in hints.items()})
    multiworld.set_options(args)
    multiworld.state = CollectionState(multiworld)
    world = multiworld.worlds[1]
    assert Path(sys.modules[world.__module__].__file__).resolve() == BASE / '__init__.py'
    world.generate_early()
    world.create_regions()
    from worlds.botw import Rules
    compile_original = Rules.compile_requirement

    def compile_traced(*args, **kwargs):
        predicate = compile_original(*args, **kwargs)

        def evaluate(state):
            if isinstance(state, TraceState):
                return state.ask(('compiled', predicate.requirement_tree))
            return predicate(state)
        return evaluate

    with patch.object(Rules, 'compile_requirement', compile_traced):
        world.set_rules()
    return world


def build_graph(world):
    from BaseClasses import Location
    graph = Graph()
    traced = []
    check_kinds = {entry['id']: entry.get('kind', 'chest') for entry in world.active_locations}
    with patch.object(Location, 'can_reach', lambda location, state: state.ask(('location', location.name))):
        for region in world.multiworld.regions:
            owner = graph.node('region', region.name)
            if region.name != 'Menu':
                routes = []
                for entrance in region.entrances:
                    route = graph.node('entrance', entrance.name)
                    graph.attach(route, graph.node('region', entrance.parent_region.name))
                    root = graph.trace(entrance.access_rule)
                    traced.append((entrance.access_rule, root))
                    graph.attach(route, root)
                    routes.append(route)
                graph.attach(owner, graph.gate('or', routes))
            for location in region.locations:
                target = graph.node('location', location.name, check_kind=check_kinds.get(location.address, 'event'), **(
                    {'check_id': location.address} if location.address is not None else {}))
                graph.attach(target, owner)
                root = graph.trace(location.access_rule)
                traced.append((location.access_rule, root))
                graph.attach(target, root)
                if location.item:
                    graph.attach(graph.node('item', location.item.name), target)
        rule = world.multiworld.completion_condition[1]
        root = graph.trace(rule)
        traced.append((rule, root))
        graph.attach(graph.node('goal', 'Victory'), root)
    return graph, traced


def verify(world, graph, traced):
    """Compare callable rules, then whole graph reachability with actual AP state."""
    from BaseClasses import CollectionState, Location
    from worlds.botw.reference import item_data
    adjacency = {}
    for a, b in graph.edges:
        adjacency.setdefault(a, []).append(b)
    exported = graph.export(world)['nodes']
    category_members = {row['id']: row['members'] for row in exported if row['type'] == 'category'}
    locations = world.multiworld.get_locations(1)
    rng = random.Random(0)

    def evaluate(key, inventory, reachable):
        if isinstance(key, bool):
            return key
        kind = graph.nodes[key]['type']
        children = adjacency.get(key, [])
        if kind == 'item':
            return inventory[key.removeprefix('item:')] > 0
        if kind == 'count':
            return sum(inventory[c.removeprefix('item:')] for c in children) >= graph.nodes[key]['minimum']
        if kind == 'location':
            return reachable[key.removeprefix('location:')]
        if kind == 'and':
            return all(evaluate(c, inventory, reachable) for c in children)
        if kind == 'or':
            return any(evaluate(c, inventory, reachable) for c in children)
        if kind == 'not':
            return not evaluate(children[0], inventory, reachable)
        if kind == 'false':
            return False
        raise ValueError(kind)

    with patch.object(Location, 'can_reach', lambda location, state: state.reachable[location.name]):
        class SampleState:
            def has(self, name, player, count=1):
                return self.inventory[name] >= count

            def count(self, name, player):
                return self.inventory[name]

        for rule, root in traced:
            for _ in range(16):
                state = SampleState()
                names = set(item_data) | {l.item.name for l in locations if l.item}
                state.inventory = Counter({name: rng.randrange(5) for name in sorted(names)})
                state.reachable = {l.name: bool(rng.randrange(2)) for l in locations}
                assert evaluate(root, state.inventory, state.reachable) == bool(rule(state)), 'Rule differs from exported graph'

    # Whole graph: repeatedly recompute reachability and sweep event items.
    # This also checks parent-region and entrance wiring, counts and event cycles.
    for sample in range(24):
        state = CollectionState(world.multiworld)
        inventory = Counter(world.starting_state['logical_inventory'])
        for name in sorted(item_data):
            if not world.category_enabled(item_data[name]):
                continue
            count = (0 if sample == 0 else 4 if sample == 1 else
                     rng.randrange(5) if rng.random() < 0.45 else 0)
            for _ in range(count):
                state.collect(world.create_item(name), prevent_sweep=True)
                inventory[name] += 1
        state.sweep_for_advancements()
        values = dict.fromkeys(graph.nodes, False)
        for _ in range(len(graph.nodes) + 1):
            previous = values.copy()
            for key, node in graph.nodes.items():
                kind = node['type']
                children = adjacency.get(key, [])
                if kind == 'item':
                    values[key] = inventory[key.removeprefix('item:')] > 0 or any(previous[c] for c in children)
                elif kind == 'count':
                    values[key] = sum(max(inventory[c.removeprefix('item:')], int(previous[c])) for c in children) >= node['minimum']
                elif kind == 'or':
                    values[key] = any(previous[c] for c in children)
                elif kind == 'not':
                    values[key] = not previous[children[0]]
                elif kind == 'false':
                    values[key] = False
                else:
                    values[key] = all(previous[c] for c in children)
            if values == previous:
                break
        else:
            raise AssertionError('Graph reachability did not converge')
        def evaluate_export(expression):
            if isinstance(expression, bool):
                return expression
            if 'ref' in expression:
                if 'count' in expression:
                    members = category_members.get(expression['ref'], [{'ref': expression['ref']}])
                    return sum(max(inventory[c['ref'].removeprefix('item:')], int(values[c['ref']]))
                               for c in members) >= expression['count']
                return values[expression['ref']]
            if 'count' in expression:
                return sum(max(inventory[c['ref'].removeprefix('item:')], int(values[c['ref']]))
                           for c in expression['of']) >= expression['count']
            if expression.get('gate') == 'AND':
                return all(map(evaluate_export, expression['inputs']))
            if expression.get('gate') == 'OR':
                return any(map(evaluate_export, expression['inputs']))
            if 'not' in expression:
                return not evaluate_export(expression['not'])
            raise ValueError(expression)
        for row in exported:
            if 'requires' in row:
                assert evaluate_export(row['requires']) == values[row['id']], row['id']
        for region in world.multiworld.regions:
            assert values['region:' + region.name] == region.can_reach(state), (sample, region.name)
        for location in locations:
            assert values['location:' + location.name] == location.can_reach(state), (sample, location.name)
        assert values['goal:Victory'] == world.multiworld.completion_condition[1](state)
    return len(traced)


def resolve_weighted(value, name):
    """Resolve an AP weighted choice only when its outcome is deterministic."""
    if isinstance(value, dict):
        if not value:
            raise ValueError(f"YAML option {name!r} has no weighted choices")
        positive = []
        for choice, weight in value.items():
            try:
                number = int(weight)
            except (ValueError, TypeError, OverflowError):
                raise ValueError(f"YAML option {name!r} has an invalid weight for {choice!r}") from None
            if number < 0 or isinstance(weight, float) and weight != number:
                raise ValueError(f"YAML option {name!r} has an invalid weight for {choice!r}")
            if number > 0:
                positive.append(choice)
        if len(positive) != 1:
            raise ValueError(f"YAML option {name!r} must have exactly one positive-weight choice (found {len(positive)})")
        value = positive[0]
    if isinstance(value, list) or (isinstance(value, str) and value.lower().startswith('random')):
        raise ValueError(f"YAML option {name!r} must resolve to a fixed value")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archipelago', required=True, type=Path)
    parser.add_argument('--all-locations', action='store_true',
                        help='Enable every AP check and DLC and retain the Plateau tower; use the default goal')
    parser.add_argument('--options', type=Path, help='JSON object of game options; omitted values use APWorld defaults')
    parser.add_argument('--yaml', type=Path, help='Archipelago player YAML with fixed BotW options')
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/logic_dependency_research.json')
    args = parser.parse_args()
    sys.setrecursionlimit(20000)
    if args.yaml and (args.options or args.all_locations):
        parser.error('--yaml cannot be combined with --options or --all-locations')
    overrides = json.loads(args.options.read_text()) if args.options else {}
    if args.yaml:
        try:
            import yaml
        except ImportError:
            parser.error('Reading player YAML requires PyYAML (pip install PyYAML)')
        document = yaml.safe_load(args.yaml.read_text())
        if not isinstance(document, dict):
            parser.error('YAML must be a mapping')
        try:
            game = resolve_weighted(document.get('game'), 'game')
        except ValueError as error:
            parser.error(str(error))
        if game != 'Breath of the Wild':
            parser.error('YAML must specify game: Breath of the Wild')
        overrides = document.get('Breath of the Wild', {})
        if not isinstance(overrides, dict):
            parser.error('The Breath of the Wild section must be a mapping')
        # Placement, hint and inventory configuration is outside this graph's
        # logic model; these structured values are not weighted choices.
        ignored = {'local_items', 'non_local_items', 'start_inventory',
                   'start_inventory_from_pool', 'start_hints', 'start_location_hints',
                   'exclude_locations', 'priority_locations', 'item_links', 'plando_items'}
        try:
            overrides = {name: resolve_weighted(value, name)
                         for name, value in overrides.items() if name not in ignored}
        except ValueError as error:
            parser.error(str(error))

    if args.all_locations:
        if args.options:
            parser.error('--all-locations and --options are mutually exclusive')
        overrides = dict(skip_great_plateau=False, chest_sanity=True,
                         shrine_sanity=True, tower_sanity=True, miniboss_sanity=True,
                         boss_sanity=True, enable_the_master_trials_dlc=True,
                         trial_of_the_sword=True, enable_the_champions_ballad_dlc=True)
    world = load_world(args.archipelago.resolve(), overrides)
    if args.all_locations:
        from worlds.botw.Locations import botw_locations
        actual = {location.address for location in world.multiworld.get_locations(1)
                  if location.address is not None}
        assert actual == set(botw_locations.values()), 'An AP location was omitted from the full export'

    graph, traced = build_graph(world)
    verified = verify(world, graph, traced)
    # Compact provenance: hashes only, never embedded source code/catalog copies.
    sources = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(BASE.rglob('*')) if p.is_file() and p.suffix in ('.py', '.json')
               and 'test' not in p.parts}
    output = {
        'scope': 'all_generatable_ap_locations' if args.all_locations else 'selected_option_locations',
        'generated_by': 'tools/export_logic_graph.py',
        'source_digest': hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest(),
        'options': {name: getattr(world.options, name).value
                    for name in world.options.__annotations__},
        'starting_inventory': world.starting_state['logical_inventory'],
        'direction': 'dependent -> prerequisite',
        'semantics': 'Each node requires its named dependencies. Gates explicitly use AND/OR with inputs; a counted ref sums owned copies (categories expand members); count/of sums its listed items. Received items come from AP inventory; event items depend on event locations. Menu is reachable. Cycles start unreachable. Randomized item placements are excluded.',
        **graph.export(world),
    }
    locations = [node for node in output['nodes'] if node['type'] == 'location']
    gate_counts = Counter()
    def count_gates(value):
        if isinstance(value, dict):
            if 'gate' in value:
                gate_counts[value['gate']] += 1
            for child in value.values():
                count_gates(child)
        elif isinstance(value, list):
            for child in value:
                count_gates(child)
    count_gates(output['nodes'])
    output['coverage'] = dict(checks=sum('check_id' in node for node in locations),
                              events=sum('check_id' not in node for node in locations),
                              AND_gates=gate_counts['AND'], OR_gates=gate_counts['OR'])
    ids = {n['id'] for n in output['nodes']}
    assert len(ids) == len(output['nodes'])
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False, default=lambda value: sorted(value) if isinstance(value, set) else (_ for _ in ()).throw(TypeError(f'Cannot serialize {type(value).__name__}'))) + '\n')
    print(f'Coverage: {output["coverage"]}')
    print(f'Exported {len(ids)} named dependency nodes. Verified {verified} rules and 24 complete reachability scenarios against Archipelago.')


if __name__ == '__main__':
    main()
