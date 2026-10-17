"""A small, closed expression language for the checks a compiled pack carries.

The compiler asks Bedrock to write checks such as

    args.nightly_rate > tables.hotel_cap[args.city_tier]

Those strings come from a model, so they are never handed to Python's `eval`. We parse them
with `ast` and walk a whitelist of node types ourselves. Anything outside the whitelist is an
`ExprError` at compile time. At run time a missing field or a type mismatch is not an error and
not a pass: `evaluate` returns None ("unknown"), and the decision table treats that as uncertain.
"""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable, Mapping
from datetime import date
from typing import Any

ROOTS = frozenset({"args", "ctx", "tables"})


class ExprError(ValueError):
    """The expression uses something outside the language."""


class _Unknown(Exception):
    """A value the expression needs is missing or has the wrong type."""


def _days_between(a: Any, b: Any) -> int:
    if not isinstance(a, str) or not isinstance(b, str):
        raise _Unknown
    try:
        return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days
    except ValueError as exc:
        raise _Unknown from exc


def _num(x: Any) -> float:
    if isinstance(x, bool):
        raise _Unknown
    if isinstance(x, int | float):
        return float(x)
    if isinstance(x, str):
        try:
            return float(x.strip())
        except ValueError as exc:
            raise _Unknown from exc
    raise _Unknown


def _len(x: Any) -> int:
    try:
        return len(x)
    except TypeError as exc:
        raise _Unknown from exc


def _lower(s: Any) -> str:
    if not isinstance(s, str):
        raise _Unknown
    return s.lower()


def _count_where(items: Any, key: Any, value: Any) -> int:
    if not isinstance(items, list):
        raise _Unknown
    return sum(1 for item in items if isinstance(item, dict) and item.get(key) == value)


FUNCS: dict[str, Callable[..., Any]] = {
    "days_between": _days_between,
    "num": _num,
    "len": _len,
    "lower": _lower,
    "count_where": _count_where,
    # present() and or_else() take an expression that may be missing; _eval handles them specially.
    "present": lambda x: x,
    "or_else": lambda x, d: x,
}
LAZY = {"present", "or_else"}

_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_CMPOPS = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le,
    ast.Gt: operator.gt, ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b,
}


def _parse(expr: str) -> ast.Expression:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ExprError(f"not a valid expression: {expr!r}") from exc
    _check(tree.body)
    return tree


def _check(node: ast.AST) -> None:
    match node:
        case ast.Constant(value=v) if v is None or isinstance(v, bool | int | float | str):
            return
        case ast.Name(id=name) if name in ROOTS:
            return
        case ast.Attribute(value=value, attr=attr) if not attr.startswith("_"):
            _check(value)
        case ast.Subscript(value=value, slice=index) if not isinstance(index, ast.Slice):
            _check(value)
            _check(index)
        case ast.BoolOp(values=values):
            for v in values:
                _check(v)
        case ast.UnaryOp(op=ast.Not() | ast.USub(), operand=operand):
            _check(operand)
        case ast.BinOp(op=op, left=left, right=right) if type(op) in _BINOPS:
            _check(left)
            _check(right)
        case ast.Compare(left=left, ops=ops, comparators=comps) if all(type(o) in _CMPOPS for o in ops):
            _check(left)
            for c in comps:
                _check(c)
        case ast.List(elts=elts) | ast.Tuple(elts=elts):
            for e in elts:
                _check(e)
        case ast.Call(func=ast.Name(id=name), args=args, keywords=[]) if name in FUNCS:
            for a in args:
                _check(a)
        case _:
            raise ExprError(f"not allowed in a check: {ast.dump(node)[:80]}")


def validate(expr: str) -> None:
    """Raise ExprError unless `expr` stays inside the language."""
    _parse(expr)


def _key(container: Any, key: Any) -> Any:
    try:
        return container[key]
    except (KeyError, IndexError, TypeError) as exc:
        raise _Unknown from exc


def _eval(node: ast.AST, env: Mapping[str, Any]) -> Any:
    match node:
        case ast.Constant(value=v):
            return v
        case ast.Name(id=name):
            return _key(env, name)
        case ast.Attribute(value=value, attr=attr):
            return _key(_eval(value, env), attr)
        case ast.Subscript(value=value, slice=index):
            return _key(_eval(value, env), _eval(index, env))
        case ast.BoolOp(op=op, values=values):
            return _bool_op(isinstance(op, ast.And), values, env)
        case ast.UnaryOp(op=ast.Not(), operand=operand):
            return not _eval(operand, env)
        case ast.UnaryOp(op=ast.USub(), operand=operand):
            return _apply(operator.neg, _eval(operand, env))
        case ast.BinOp(op=op, left=left, right=right):
            return _apply(_BINOPS[type(op)], _eval(left, env), _eval(right, env))
        case ast.Compare(left=left, ops=ops, comparators=comps):
            current = _eval(left, env)
            for op, comp in zip(ops, comps, strict=True):
                nxt = _eval(comp, env)
                if not _apply(_CMPOPS[type(op)], current, nxt):
                    return False
                current = nxt
            return True
        case ast.List(elts=elts) | ast.Tuple(elts=elts):
            return [_eval(e, env) for e in elts]
        case ast.Call(func=ast.Name(id="present"), args=[arg]):
            try:
                value = _eval(arg, env)
            except _Unknown:
                return False
            return value is not None and value != "" and value != []
        case ast.Call(func=ast.Name(id="or_else"), args=[arg, fallback]):
            try:
                value = _eval(arg, env)
            except _Unknown:
                value = None
            return _eval(fallback, env) if value is None or value == "" else value
        case ast.Call(func=ast.Name(id=name), args=args) if name not in LAZY:
            return FUNCS[name](*[_eval(a, env) for a in args])
    raise ExprError(f"unexpected node {type(node).__name__}")  # unreachable after _check


def _apply(fn: Callable[..., Any], *values: Any) -> Any:
    try:
        return fn(*values)
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise _Unknown from exc


def _bool_op(is_and: bool, values: list[ast.expr], env: Mapping[str, Any]) -> bool:
    """Three-valued logic: a decisive operand wins even if another one is unknown."""
    unknown = False
    for v in values:
        try:
            truth = bool(_eval(v, env))
        except _Unknown:
            unknown = True
            continue
        if is_and and not truth:
            return False
        if not is_and and truth:
            return True
    if unknown:
        raise _Unknown
    return is_and


def evaluate(expr: str, env: Mapping[str, Any]) -> bool | None:
    """True or False when the expression can be decided, None when a value is missing or mistyped."""
    tree = _parse(expr)
    try:
        return bool(_eval(tree.body, env))
    except _Unknown:
        return None
