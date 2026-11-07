"""Compile item requirements and retain the effective tree used by each predicate."""
from __future__ import annotations

from .static.requirements import parse_requirement


def compile_requirement(expression: str, player: int, items: dict, categories: dict,
                        ignored_items: frozenset[str] = frozenset()):
    def compile_node(node):
        operator = node[0]
        if operator == 'true' or (operator == 'item' and node[1] in ignored_items):
            return (lambda state: True), ('true',)
        if operator == 'item':
            if node[1] not in items:
                raise ValueError(f'Unknown logic item: {node[1]}')
            return (lambda state: state.has(node[1], player, node[2])), node
        if operator == 'category':
            if node[1] not in categories:
                raise ValueError(f'Unknown logic category: {node[1]}')
            names = tuple(sorted(categories[node[1]]))
            return (lambda state: sum(state.count(name, player) for name in names) >= node[2]), ('sum', names, node[2])
        compiled = tuple(compile_node(child) for child in node[1])
        predicates = tuple(pair[0] for pair in compiled)
        tree = (operator, tuple(pair[1] for pair in compiled))
        if operator == 'all':
            return (lambda state: all(child(state) for child in predicates)), tree
        return (lambda state: any(child(state) for child in predicates)), tree

    predicate, tree = compile_node(parse_requirement(expression))
    # Generated from the same compilation steps as the callable, including
    # ignored predicates and the actual category members. Exporters can retain
    # the original AND/OR structure rather than reconstructing a truth table.
    predicate.requirement_tree = tree
    return predicate
