# SPDX-FileCopyrightText: 2026 ParticleTroned
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import re
from typing import Any, Iterator

_WORLDSPACE_EQUALS_VALUE_RE = re.compile(r"(?:==|=)\s*([01])(?:\.0+)?\b", re.IGNORECASE)
_WORLDSPACE_VALUE_EQUALS_RE = re.compile(r"\b([01])(?:\.0+)?\s*(?:==|=)", re.IGNORECASE)
_WORLDSPACE_TOKEN_RE = re.compile(r"getinworldspace", re.IGNORECASE)
_EQUALITY_OPERATOR_TOKENS = {"=", "==", "eq", "equal", "equals"}
_OPERATOR_KEY_TOKENS = {"operator", "op", "comparison", "compare", "comparator"}
_VALUE_KEY_HINTS = {
    "value",
    "rhs",
    "result",
    "arg2",
    "second",
    "param2",
    "operand2",
    "comparisonvalue",
    "comparevalue",
}


def _normalized_token(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _normalized_operator(value: str) -> str:
    text = value.strip().lower()
    if text in {"==", "=", "!=", "<=", ">=", "<", ">"}:
        return text
    return _normalized_token(text)


def _iter_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        text = value.strip()
        if text:
            yield text
        return
    if isinstance(value, dict):
        for nested in value.values():
            yield from _iter_strings(nested)
        return
    if isinstance(value, (list, tuple, set)):
        for nested in value:
            yield from _iter_strings(nested)


def _iter_condition_nodes(value: Any) -> Iterator[Any]:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_token = _normalized_token(str(key))
            if key_token in {"condition", "conditions"}:
                if isinstance(nested, (list, tuple, set)):
                    for item in nested:
                        yield item
                else:
                    yield nested
            yield from _iter_condition_nodes(nested)
        return
    if isinstance(value, (list, tuple, set)):
        for nested in value:
            yield from _iter_condition_nodes(nested)


def _is_get_in_worldspace_text(value: str) -> bool:
    return _WORLDSPACE_TOKEN_RE.search(value) is not None


def _state_from_condition_string(value: str) -> bool | None:
    text = value.strip()
    if not text or not _is_get_in_worldspace_text(text):
        return None
    match = _WORLDSPACE_EQUALS_VALUE_RE.search(text)
    if match is None:
        match = _WORLDSPACE_VALUE_EQUALS_RE.search(text)
    if match is None:
        return None
    return match.group(1) == "1"


def _parse_numeric_flag(value: Any) -> bool | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if abs(float(value) - 1.0) <= 1e-6:
            return True
        if abs(float(value) - 0.0) <= 1e-6:
            return False
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            numeric = float(text)
        except ValueError:
            return None
        if abs(numeric - 1.0) <= 1e-6:
            return True
        if abs(numeric - 0.0) <= 1e-6:
            return False
    return None


def _iter_keyed_values(value: Any) -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, nested in value.items():
            yield _normalized_token(str(key)), nested
            yield from _iter_keyed_values(nested)
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            yield from _iter_keyed_values(nested)


def _state_from_condition_mapping(value: dict[str, Any]) -> bool | None:
    if not any(_is_get_in_worldspace_text(text) for text in _iter_strings(value)):
        return None

    operators: list[str] = []
    for key_token, nested in _iter_keyed_values(value):
        if key_token in _OPERATOR_KEY_TOKENS and isinstance(nested, str):
            operators.append(_normalized_operator(nested))

    if operators and not any(op in _EQUALITY_OPERATOR_TOKENS for op in operators):
        return None

    numeric_candidates: list[bool] = []
    fallback_numeric_candidates: list[bool] = []
    for key_token, nested in _iter_keyed_values(value):
        parsed = _parse_numeric_flag(nested)
        if parsed is None:
            continue
        if any(hint in key_token for hint in _VALUE_KEY_HINTS):
            numeric_candidates.append(parsed)
        else:
            fallback_numeric_candidates.append(parsed)

    if numeric_candidates:
        return numeric_candidates[0]
    if fallback_numeric_candidates:
        return fallback_numeric_candidates[0]
    return None


def iter_get_in_worldspace_states(value: Any) -> Iterator[bool]:
    """Yield `False` for interior (`== 0`) and `True` for exterior (`== 1`) conditions."""

    for condition in _iter_condition_nodes(value):
        if isinstance(condition, str):
            state = _state_from_condition_string(condition)
            if state is not None:
                yield state
            continue
        if isinstance(condition, dict):
            state = _state_from_condition_mapping(condition)
            if state is not None:
                yield state
