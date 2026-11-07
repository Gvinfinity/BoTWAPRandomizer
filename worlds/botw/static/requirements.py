"""Shared safe parser for catalog and APWorld item requirements."""
from __future__ import annotations

import re

_TOKEN = re.compile(r"\s*(\|[^|]+\||\(|\)|AND\b|OR\b)", re.IGNORECASE)


def parse_requirement(expression: str):
    if not expression.strip():
        return ("true",)
    tokens, offset = [], 0
    while offset < len(expression.rstrip()):
        match = _TOKEN.match(expression, offset)
        if not match:
            raise ValueError(f"Unsupported Manual rule near {expression[offset:]!r}")
        tokens.append(match[1])
        offset = match.end()
    position = 0

    def atom():
        nonlocal position
        if position >= len(tokens):
            raise ValueError(f"Incomplete requirement: {expression}")
        token = tokens[position]
        position += 1
        if token == "(":
            child = disjunction()
            if position >= len(tokens) or tokens[position] != ")":
                raise ValueError(f"Missing closing parenthesis: {expression}")
            position += 1
            return child
        if not token.startswith("|"):
            raise ValueError(f"Expected item/category requirement: {token}")
        value = token[1:-1]
        name, separator, count = value.rpartition(":")
        if not separator:
            name, count = value, "1"
        if not count.isdecimal() or int(count) < 1:
            raise ValueError(f"Unsupported count in requirement: {token}")
        return ("category" if name.startswith("@") else "item", name.removeprefix("@"), int(count))

    def conjunction():
        nonlocal position
        children = [atom()]
        while position < len(tokens) and tokens[position].upper() == "AND":
            position += 1
            children.append(atom())
        return children[0] if len(children) == 1 else ("all", tuple(children))

    def disjunction():
        nonlocal position
        children = [conjunction()]
        while position < len(tokens) and tokens[position].upper() == "OR":
            position += 1
            children.append(conjunction())
        return children[0] if len(children) == 1 else ("any", tuple(children))

    tree = disjunction()
    if position != len(tokens):
        raise ValueError(f"Unexpected trailing requirement: {tokens[position:]}")
    return tree

