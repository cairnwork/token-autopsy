"""Price table loading and per-call cost computation."""
from __future__ import annotations

import json
import os
from importlib import resources

USER_PRICES = os.path.expanduser("~/.config/token-autopsy/prices.json")
KEYS = ("input", "cache_write", "cache_read", "output")


def load_prices(path: str | None = None) -> dict:
    """Load the price table: explicit path > user config > packaged default."""
    if path is None and os.path.exists(USER_PRICES):
        path = USER_PRICES
    if path:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.loads(resources.files("token_autopsy").joinpath("default_prices.json").read_text("utf-8"))
    data.setdefault("models", [])
    data.setdefault("fallback", {"input": 15.0, "cache_write": 18.75, "cache_read": 1.5, "output": 75.0})
    for e in data["models"] + [data["fallback"]]:
        for k in KEYS:
            e.setdefault(k, 0.0)
        e.setdefault("cache_write_1h", 2 * e["input"])
    return data


class Pricer:
    def __init__(self, table: dict):
        self.table = table
        self._cache: dict[str, tuple[dict, bool]] = {}

    def lookup(self, model: str) -> tuple[dict, bool]:
        """Return (price entry, is_fallback)."""
        r = self._cache.get(model)
        if r is None:
            low = (model or "").lower()
            r = (self.table["fallback"], True)
            for e in self.table["models"]:
                if e["match"].lower() in low:
                    r = (e, False)
                    break
            self._cache[model] = r
        return r

    def cost(self, model: str, inp: int, cw: int, cr: int, out: int,
             cw1h: int = 0) -> tuple[float, float, float, float]:
        """cw is all cache-write tokens; cw1h is the part written with the 1-hour TTL (2x input)."""
        p, _ = self.lookup(model)
        cw1h = min(max(cw1h, 0), cw)
        return (inp * p["input"] / 1e6,
                ((cw - cw1h) * p["cache_write"] + cw1h * p["cache_write_1h"]) / 1e6,
                cr * p["cache_read"] / 1e6, out * p["output"] / 1e6)
