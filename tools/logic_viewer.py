"""Interactive explorer for the dependency export, using Python's Tk GUI."""
import json
import shlex
import subprocess
import tkinter as tk
from tkinter import ttk


def open_viewer(data, initial='goal:Victory'):
    nodes = {node['id']: node for node in data['nodes']}
    root = tk.Tk()
    root.title('BotW Archipelago logic explorer')
    root.geometry('1200x760')
    search = tk.StringVar()
    status = tk.StringVar(value='Select a node. Expand arrows to explore its prerequisites.')
    top = ttk.Frame(root, padding=8)
    top.pack(fill='x')
    ttk.Label(top, text='Search all logic:').pack(side='left')
    ttk.Entry(top, textvariable=search).pack(side='left', fill='x', expand=True, padx=8)
    pane = ttk.Panedwindow(root, orient='horizontal')
    pane.pack(fill='both', expand=True, padx=8)
    left = ttk.Frame(pane)
    right = ttk.Frame(pane)
    pane.add(left, weight=1)
    pane.add(right, weight=3)
    listing = tk.Listbox(left, exportselection=False)
    list_scroll = ttk.Scrollbar(left, orient='vertical', command=listing.yview)
    listing.configure(yscrollcommand=list_scroll.set)
    list_scroll.pack(side='right', fill='y')
    listing.pack(fill='both', expand=True)
    tabs = ttk.Notebook(right)
    tabs.pack(fill='both', expand=True)
    tree_frame = ttk.Frame(tabs)
    graph_frame = ttk.Frame(tabs)
    tabs.add(tree_frame, text='Tree')
    tabs.add(graph_frame, text='Graph')
    tree = ttk.Treeview(tree_frame, show='tree')
    tree_scroll = ttk.Scrollbar(tree_frame, orient='vertical', command=tree.yview)
    tree.configure(yscrollcommand=tree_scroll.set)
    tree_scroll.pack(side='right', fill='y')
    tree.pack(fill='both', expand=True)
    graph_toolbar = ttk.Frame(graph_frame)
    graph_toolbar.pack(fill='x')
    ttk.Label(graph_toolbar, text='Depth:').pack(side='left')
    graph_depth = tk.IntVar(value=2)
    depth_control = ttk.Spinbox(graph_toolbar, from_=0, to=8, width=4, textvariable=graph_depth)
    depth_control.pack(side='left', padx=4)
    canvas_frame = ttk.Frame(graph_frame)
    canvas_frame.pack(fill='both', expand=True)
    canvas = tk.Canvas(canvas_frame, background='white')
    xscroll = ttk.Scrollbar(canvas_frame, orient='horizontal', command=canvas.xview)
    yscroll = ttk.Scrollbar(canvas_frame, orient='vertical', command=canvas.yview)
    canvas.configure(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
    xscroll.pack(side='bottom', fill='x')
    yscroll.pack(side='right', fill='y')
    canvas.pack(fill='both', expand=True)
    ttk.Label(root, textvariable=status, padding=8).pack(fill='x')
    matches = []
    pending = {}
    current = [None]
    zoom = [1.0]

    def add(parent, label, value=None, ancestors=frozenset()):
        row = tree.insert(parent, 'end', text=label)
        if value is not None:
            pending[row] = (value, ancestors)
            tree.insert(row, 'end', text='Expand to load')
        return row

    def populate(row, value, ancestors):
        if isinstance(value, bool):
            add(row, 'Always' if value else 'Never')
        elif 'ref' in value:
            key = value['ref']
            label = key + (f" (at least {value['count']})" if 'count' in value else '')
            if key in ancestors:
                add(row, label + ' (cycle)')
            else:
                node = nodes.get(key)
                add(row, label, node, ancestors | {key}) if node else add(row, label + ' (missing)')
        elif 'id' in value:
            if 'requires' in value:
                populate(row, value['requires'], ancestors)
            if value.get('members'):
                members = add(row, 'Category members')
                for member in value['members']:
                    populate(members, member, ancestors)
            if 'requires' not in value and not value.get('members'):
                add(row, 'No further prerequisites in export')
        else:
            if 'not' in value:
                label, children = 'NOT', [value['not']]
            elif 'of' in value:
                label, children = f"At least {value['count']} of", value['of']
            else:
                label, children = value['gate'], value['inputs']
            gate = add(row, label)
            tree.item(gate, open=True)
            for child in children:
                populate(gate, child, ancestors)

    def expand(_event):
        row = tree.focus()
        if row not in pending:
            return
        value, ancestors = pending.pop(row)
        tree.delete(*tree.get_children(row))
        populate(row, value, ancestors)

    def show_key(key):
        if key not in matches:
            search.set('')
        index = matches.index(key)
        listing.selection_clear(0, 'end')
        listing.selection_set(index)
        listing.see(index)
        select()

    def draw_graph():
        key = current[0]
        if not key:
            return
        try:
            depth = max(0, min(8, graph_depth.get()))
        except tk.TclError:
            status.set('Graph depth must be a number from 0 to 8')
            return
        lines = ['digraph G {', 'rankdir=LR;', 'node [shape=box, fontname="Helvetica"];']
        labels, links, seen = {}, {}, set()
        counter = [0]
        def make(label, ref=None, gate=False):
            counter[0] += 1
            name = 'n' + str(counter[0])
            labels[name] = label
            if ref:
                links[name] = ref
            lines.append(f'{name} [label={json.dumps(label, ensure_ascii=False)}, shape={"diamond" if gate else "box"}];')
            return name
        def expr(value, remaining, ancestors):
            if isinstance(value, bool):
                return make('Always' if value else 'Never')
            if 'ref' in value:
                ref = value['ref']
                if 'count' in value:
                    gate = make('At least ' + str(value['count']), gate=True)
                    child = named(ref, remaining, ancestors)
                    lines.append(f'{gate} -> {child};')
                    return gate
                return named(ref, remaining, ancestors)
            if 'not' in value:
                label, children = 'NOT', [value['not']]
            elif 'of' in value:
                label, children = 'At least ' + str(value['count']), value['of']
            else:
                label, children = value['gate'], value['inputs']
            parent = make(label, gate=True)
            for child in children:
                lines.append(f'{parent} -> {expr(child, remaining, ancestors)};')
            return parent
        def named(ref, remaining, ancestors):
            node = nodes.get(ref, {})
            suffix = ' (cycle)' if ref in ancestors else (' …' if remaining == 0 and (node.get('requires') or node.get('members')) else '')
            parent = make(ref + suffix, ref if ref in nodes else None)
            if remaining and ref not in ancestors:
                if 'requires' in node:
                    lines.append(f'{parent} -> {expr(node["requires"], remaining - 1, ancestors | {ref})};')
                if node.get('members'):
                    group = make('Category members', gate=True)
                    lines.append(f'{parent} -> {group} [style=dashed];')
                    for member in node['members']:
                        lines.append(f'{group} -> {expr(member, remaining - 1, ancestors | {ref})} [style=dashed];')
            return parent
        named(key, depth, set())
        lines.append('}')
        try:
            result = subprocess.run(['dot', '-Tplain'], input='\n'.join(lines), text=True,
                                    capture_output=True, check=True, timeout=20)
        except (FileNotFoundError, subprocess.SubprocessError) as error:
            canvas.delete('all')
            canvas.create_text(15, 15, anchor='nw', text=f'Graph needs Graphviz dot: {error}')
            return
        rows = [shlex.split(line) for line in result.stdout.splitlines()]
        graph = next(row for row in rows if row[0] == 'graph')
        height = float(graph[3])
        factor = 72 * zoom[0]
        canvas.delete('all')
        for row in rows:
            if row[0] != 'edge':
                continue
            count = int(row[3])
            coords = []
            for i in range(count):
                coords.extend((float(row[4 + 2*i]) * factor + 20,
                               (height - float(row[5 + 2*i])) * factor + 20))
            if len(coords) >= 4:
                canvas.create_line(*coords, smooth=True, arrow='last', fill='#647b83', dash=(4, 3) if row[-2] == 'dashed' else ())
        for row in rows:
            if row[0] != 'node':
                continue
            name = row[1]
            x, y, w, h = map(float, row[2:6])
            x, y, w, h = x * factor + 20, (height - y) * factor + 20, w * factor, h * factor
            tag = 'node_' + name
            canvas.create_rectangle(x-w/2, y-h/2, x+w/2, y+h/2, fill='#fff1d6' if row[8] == 'diamond' else '#e8f1f4', outline='#647b83', tags=(tag,))
            canvas.create_text(x, y, text=labels[name], font=('Helvetica', max(6, int(10 * zoom[0]))), tags=(tag,))
            if name in links:
                canvas.tag_bind(tag, '<Button-1>', lambda event, ref=links[name]: show_key(ref))
        canvas.configure(scrollregion=(0, 0, float(graph[2])*factor+40, height*factor+40))
        status.set('Graph: click a named node to explore it; arrows point to prerequisites.')

    def change_zoom(multiplier):
        zoom[0] = max(0.3, min(2.5, zoom[0] * multiplier))
        draw_graph()

    ttk.Button(graph_toolbar, text='Refresh', command=draw_graph).pack(side='left', padx=4)
    ttk.Button(graph_toolbar, text='−', command=lambda: change_zoom(0.8)).pack(side='left')
    ttk.Button(graph_toolbar, text='+', command=lambda: change_zoom(1.25)).pack(side='left')
    ttk.Label(graph_toolbar, text='Click a node to navigate; use scrollbars to pan').pack(side='left', padx=8)
    tabs.bind('<<NotebookTabChanged>>', lambda event: draw_graph() if tabs.select() == str(graph_frame) else None)

    def select(_event=None):
        selection = listing.curselection()
        if not selection:
            return
        key = matches[selection[0]]
        current[0] = key
        tree.delete(*tree.get_children())
        pending.clear()
        row = add('', key, nodes[key], frozenset({key}))
        tree.focus(row)
        expand(None)
        tree.item(row, open=True)
        status.set('Prerequisites for ' + key + ' · Expand arrows for more detail')
        if tabs.select() == str(graph_frame):
            draw_graph()

    def filter_nodes(*_args):
        query = search.get().casefold()
        matches[:] = sorted(key for key in nodes if query in key.casefold())
        listing.delete(0, 'end')
        for key in matches:
            listing.insert('end', key)
        if initial in matches and not query:
            index = matches.index(initial)
            listing.selection_set(index)
            listing.see(index)
            select()

    search.trace_add('write', filter_nodes)
    listing.bind('<<ListboxSelect>>', select)
    tree.bind('<<TreeviewOpen>>', expand)
    filter_nodes()
    root.mainloop()
