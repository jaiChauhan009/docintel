"""Produce a redacted copy of an extraction for less-trusted consumers."""
from __future__ import annotations

import copy
import re

_ACCOUNT_KEYS = {"account_number", "account_number_masked", "iban", "card_number", "routing_number"}


def _mask_number(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) <= 4:
        return "****"
    return "****" + digits[-4:]


def mask_extraction(data: dict) -> dict:
    out = copy.deepcopy(data)

    def walk(node: object) -> object:
        if isinstance(node, dict):
            for key, val in list(node.items()):
                if key.lower() in _ACCOUNT_KEYS and isinstance(val, str) and val:
                    node[key] = _mask_number(val)
                else:
                    node[key] = walk(val)
            return node
        if isinstance(node, list):
            return [walk(item) for item in node]
        return node

    return walk(out)  # type: ignore[return-value]
