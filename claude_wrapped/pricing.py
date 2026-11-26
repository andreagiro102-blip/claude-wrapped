"""API list prices, used to show what your usage WOULD cost on the API.

Subscription (Pro/Max) users do not pay this: it is an "API-equivalent" figure.
Prices change - override them with `--prices my_prices.json`, a JSON object of
{"model-name": [input, output, cache_read]} in USD per million tokens.
"""
from __future__ import annotations

import json
import re

# USD per million tokens: (input, output, cache read).
# Cache writes are billed on the input price: 1.25x for the 5-minute TTL,
# 2x for the 1-hour TTL (Claude Code's default for its main conversation).
PRICES_UPDATED = "2026-11"
PRICES = {
    "claude-opus-4-6": (5, 25, 0.50),
    "claude-opus-4-7": (5, 25, 0.50),
    "claude-opus-4-8": (5, 25, 0.50),
    "claude-opus-5": (5, 25, 0.50),
    "claude-opus-5-5": (4, 20, 0.20),
    "claude-fable-5": (10, 50, 1.00),
    "claude-fable-5-1": (10, 50, 0.25),
    "claude-sonnet-4-5": (3, 15, 0.30),
    "claude-sonnet-4-6": (3, 15, 0.30),
    "claude-sonnet-5": (2, 10, 0.20),
    "claude-haiku-4-5": (1, 5, 0.10),
}
CACHE_WRITE_5M, CACHE_WRITE_1H = 1.25, 2.0


def load_prices(path: str | None = None) -> dict:
    table = dict(PRICES)
    if path:
        with open(path, encoding="utf-8") as fh:
            table.update({k: tuple(v) for k, v in json.load(fh).items()})
    return table


def price_for(model: str, table: dict):
    """Exact match, then without a date suffix (-20251001).

    No prefix matching on purpose: "claude-sonnet-5-5" must NOT silently get the
    price of "claude-sonnet-5". Unknown models are reported as unpriced instead.
    """
    if model in table:
        return table[model]
    return table.get(re.sub(r"-\d{8}$", "", model))


def message_cost(msg, table: dict):
    """(cost in USD, saved by cache reads) for one message, or (None, 0) if unpriced."""
    p = price_for(msg.model, table)
    if p is None:
        return None, 0.0
    pin, pout, pread = p
    t = msg.tokens
    cw5 = min(msg.cache_write_5m, t["cache_write"])
    cw1h = t["cache_write"] - cw5
    usd = (t["input"] * pin + t["output"] * pout + t["cache_read"] * pread
           + cw5 * pin * CACHE_WRITE_5M + cw1h * pin * CACHE_WRITE_1H) / 1e6
    saved = t["cache_read"] * (pin - pread) / 1e6
    return usd, saved
