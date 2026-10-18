"""Read tool arguments the way the tool will, before any check sees them.

A model can send "300" for a number or "false" for a boolean, and the tool's own validation
accepts both. If checks read the raw strings, `not "false"` is False and "NaN" compares False
against every cap, so a breach would read as clear. We coerce each argument to its schema type
and drop anything we cannot read, which leaves the field missing and the check unknown.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

_DROP = object()


def _number(value: Any) -> Any:
    if isinstance(value, bool):
        return _DROP
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return _DROP
    if isinstance(value, int | float) and math.isfinite(value):
        return value
    return _DROP


def _boolean(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return _DROP


def _coerce(value: Any, spec: Mapping[str, Any]) -> Any:
    kind = spec.get("type")
    if kind in ("number", "integer"):
        return _number(value)
    if kind == "boolean":
        return _boolean(value)
    if kind == "string":
        return value if isinstance(value, str) else _DROP
    return value


def normalize_args(args: Mapping[str, Any], schema: Mapping[str, Any] | None) -> dict[str, Any]:
    """`args` coerced to `schema`'s property types; unreadable values are dropped. No schema: unchanged."""
    if schema is None:
        return dict(args)
    props = schema.get("properties", {})
    out: dict[str, Any] = {}
    for key, value in args.items():
        coerced = _coerce(value, props.get(key, {}))
        if coerced is not _DROP:
            out[key] = coerced
    return out
