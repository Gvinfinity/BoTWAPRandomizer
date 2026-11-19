#!/usr/bin/env python3
"""Render a focused diagram from export_logic_graph.py's verified JSON output."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', nargs='?', default='goal:Victory', help='Node ID or a unique name fragment')
    parser.add_argument('--graph', type=Path, default=ROOT / 'docs/logic_dependency_research.json')
    parser.add_argument('--yaml', type=Path, help='Player YAML with fixed BotW options')
    parser.add_argument('--archipelago', type=Path, help='Archipelago checkout (required with --yaml)')
    parser.add_argument('--depth', type=int, default=3, help='Maximum named dependency levels (default: 3)')
    parser.add_argument('--output', type=Path, default=Path('logic_diagram.svg'))
    parser.add_argument('--list', action='store_true', help='List matching nodes instead of rendering')
    parser.add_argument('--full', action='store_true', help='Render all exported nodes and dependencies')
    parser.add_argument('--interactive', action='store_true', help='Open the searchable interactive Python viewer')
    args = parser.parse_args()
    if args.depth < 0:
        parser.error('--depth must be nonnegative')
    if args.yaml:
        if not args.archipelago:
            parser.error('--yaml requires --archipelago pointing to an Archipelago checkout')
        with tempfile.TemporaryDirectory(prefix='botw-logic-') as directory:
            generated = Path(directory) / 'logic.json'
            command = [sys.executable, str(ROOT / 'tools/export_logic_graph.py'),
                       '--archipelago', str(args.archipelago.resolve()), '--yaml',
                       str(args.yaml.resolve()), '--output', str(generated)]
            try:
                subprocess.run(command, check=True)
            except subprocess.CalledProcessError as error:
                parser.exit(error.returncode, 'Could not generate logic from the player YAML.\n')
            data = json.loads(generated.read_text())
    else:
        data = json.loads(args.graph.read_text())
    nodes = {n['id']: n for n in data['nodes']}
    matches = [key for key in nodes if args.target.casefold() in key.casefold()]
    if args.list:
        print('\n'.join(matches))
        return
    target = args.target if args.target in nodes else (matches[0] if len(matches) == 1 else None)
    if target is None and not args.full:
        parser.error('Target must match one node. Use --list to see matches.')
    sources = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted((ROOT / 'worlds/botw').rglob('*')) if p.is_file()
               and p.suffix in ('.py', '.json') and 'test' not in p.parts}
    digest = hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()
    if digest != data.get('source_digest'):
        print('Warning: graph is stale; regenerate it with tools/export_logic_graph.py.', file=sys.stderr)
    if args.interactive:
        from logic_viewer import open_viewer
        open_viewer(data, target or 'goal:Victory')
        return
    lines = ['digraph logic {', 'rankdir=LR;', 'graph [bgcolor="white", pad="0.3"];',
             'node [shape=box, style="rounded,filled", fillcolor="#e8f1f4", fontname="Helvetica"];',
             'edge [color="#647b83"];']
    counter = [0]
    def new(label, attrs=''):
        counter[0] += 1
        key = 'n' + str(counter[0])
        lines.append(f'{key} [label={json.dumps(label, ensure_ascii=False)} {attrs}];')
        return key
    def named(key, depth, ancestors):
        node = nodes.get(key, {})
        label = key.replace(':', ': ', 1)
        if key in ancestors:
            return new(label + '\n(cycle)', 'fillcolor="#fff1d6"')
        requires = node.get('requires')
        truncated = requires is not None and depth == 0
        parent = new(label + ('\n…' if truncated else ''))
        if requires is not None and depth > 0:
            child = expression(requires, depth - 1, ancestors | {key})
            lines.append(f'{parent} -> {child};')
        return parent
    def expression(value, depth, ancestors):
        if isinstance(value, bool):
            return new('Always' if value else 'Never')
        if 'ref' in value:
            child = named(value['ref'], depth, ancestors)
            if 'count' in value:
                gate = new('At least ' + str(value['count']), 'shape=diamond fillcolor="#fff1d6"')
                lines.append(f'{gate} -> {child};')
                return gate
            return child
        if 'not' in value:
            gate, children = 'NOT', [value['not']]
        elif 'of' in value:
            gate, children = 'At least ' + str(value['count']), value['of']
        else:
            gate, children = value['gate'], value['inputs']
        parent = new(gate, 'shape=diamond fillcolor="#fff1d6"')
        for part in children:
            child = expression(part, depth, ancestors)
            lines.append(f'{parent} -> {child};')
        return parent
    if args.full:
        # Reuse named nodes, keeping the complete graph bounded even when
        # dependencies are shared or cyclic.
        ids = {key: new(key.replace(':', ': ', 1)) for key in nodes}
        def full_expression(value):
            if isinstance(value, bool):
                return new('Always' if value else 'Never')
            if 'ref' in value:
                child = ids[value['ref']]
                if 'count' not in value:
                    return child
                parent = new('At least ' + str(value['count']), 'shape=diamond fillcolor="#fff1d6"')
                lines.append(f'{parent} -> {child};')
                return parent
            if 'not' in value:
                label, children = 'NOT', [value['not']]
            elif 'of' in value:
                label, children = 'At least ' + str(value['count']), value['of']
            else:
                label, children = value['gate'], value['inputs']
            parent = new(label, 'shape=diamond fillcolor="#fff1d6"')
            for part in children:
                lines.append(f'{parent} -> {full_expression(part)};')
            return parent
        for key, node in nodes.items():
            if 'requires' in node:
                lines.append(f'{ids[key]} -> {full_expression(node["requires"])};')
            for member in node.get('members', []):
                lines.append(f'{ids[key]} -> {full_expression(member)} [style=dashed];')
    else:
        named(target, args.depth, set())
    lines.append('}')
    try:
        subprocess.run(['dot', '-Tsvg', '-o', str(args.output)], input='\n'.join(lines),
                       text=True, check=True)
    except FileNotFoundError:
        parser.error('Graphviz dot is required to render SVG; install Graphviz.')
    print(f'Wrote {args.output} (arrows point from a requirement to its prerequisites).')
    if args.full:
        print('Dashed arrows show category members. The export options determine which checks are included.')
    else:
        print('Ellipses indicate more dependencies; increase --depth to expand them.')


if __name__ == '__main__':
    main()
