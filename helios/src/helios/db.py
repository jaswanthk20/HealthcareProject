"""Thin SQLite access layer with timing, row limits and a read-only guard."""

import os
import re
import sqlite3
import time

DEFAULT_DB = os.path.join("data", "helios.db")

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|PRAGMA|REPLACE|VACUUM)\b",
    re.IGNORECASE,
)


class ReadOnlyViolation(Exception):
    """Raised when a generated query attempts to mutate the warehouse."""


class Warehouse:
    """Every analytic read in HELIOS goes through this object.

    Two invariants it enforces, both of which exist for audit reasons:
      1. no statement may mutate data (the agent only ever reads);
      2. every execution is timed and row-counted so telemetry is complete.
    """

    def __init__(self, path=DEFAULT_DB):
        self.path = path
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"{path} not found - run: python data/generator/generate_rwd.py"
            )
        self.con = sqlite3.connect(path)
        self.con.row_factory = sqlite3.Row
        self.stats = {"queries": 0, "rows": 0, "ms": 0.0}

    def query(self, sql, params=(), max_rows=200_000):
        if _FORBIDDEN.search(sql):
            raise ReadOnlyViolation(f"write statement blocked: {sql[:120]}")
        t0 = time.perf_counter()
        cur = self.con.execute(sql, params)
        rows = cur.fetchmany(max_rows)
        ms = (time.perf_counter() - t0) * 1000
        self.stats["queries"] += 1
        self.stats["rows"] += len(rows)
        self.stats["ms"] += ms
        return [dict(r) for r in rows], ms

    def scalar(self, sql, params=()):
        rows, _ = self.query(sql, params)
        if not rows:
            return None
        return list(rows[0].values())[0]

    def columns(self, table):
        rows, _ = self.query(f"SELECT * FROM {table} LIMIT 1")
        if rows:
            return list(rows[0].keys())
        cur = self.con.execute(f"SELECT * FROM {table} LIMIT 0")
        return [d[0] for d in cur.description]

    def tables(self):
        rows, _ = self.query(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return [r["name"] for r in rows]

    def close(self):
        self.con.close()
