"""SQLite journal: every token seen, every rejection and why, every paper trade.

Chaque ligne de seen / signals / positions porte la stratégie et sa version, et chaque
stratégie-version a son propre capital fictif (kv 'book:<strategie>@<version>').
"""
import os
import sqlite3

from . import config as C

SCHEMA_VERSION = "3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY, ts TEXT, finished_ts TEXT, status TEXT, note TEXT,
  pools_seen INTEGER DEFAULT 0, deep_checked INTEGER DEFAULT 0, signals INTEGER DEFAULT 0,
  sol_px REAL);
CREATE TABLE IF NOT EXISTS seen (
  run_id INTEGER, mint TEXT, pool TEXT, name TEXT, age_h REAL, liq REAL, vol24 REAL,
  price REAL, verdict TEXT, strategy TEXT, version INTEGER);
CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY, run_id INTEGER, ts TEXT, mint TEXT, pool TEXT, name TEXT,
  price REAL, prior_high REAL, vol REAL, median_vol REAL, action TEXT,
  strategy TEXT, version INTEGER, signal_ts INTEGER, detail TEXT);
CREATE TABLE IF NOT EXISTS positions (
  id INTEGER PRIMARY KEY, mint TEXT, pool TEXT, name TEXT, opened_ts TEXT,
  entry_px REAL, size_usd REAL, last_px REAL, misses INTEGER DEFAULT 0,
  closed_ts TEXT, exit_price REAL, pnl_usd REAL, exit_reason TEXT,
  strategy TEXT, version INTEGER, signal_ts INTEGER,
  stop_pct REAL, target_pct REAL, max_hold_h REAL, slippage_pct REAL, fee_pct REAL,
  detail TEXT);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
"""

# Colonnes ajoutées par le schéma 2, et la valeur des lignes écrites avant (breakout v1).
_V1 = {"strategy": "'breakout'", "version": "1"}
_MIGRATION = {
    "runs": {"sol_px": ("REAL", None)},
    "seen": {"strategy": ("TEXT", _V1["strategy"]), "version": ("INTEGER", _V1["version"])},
    "signals": {"strategy": ("TEXT", _V1["strategy"]), "version": ("INTEGER", _V1["version"]),
                "signal_ts": ("INTEGER", None), "detail": ("TEXT", None)},
    "positions": {"strategy": ("TEXT", _V1["strategy"]), "version": ("INTEGER", _V1["version"]),
                  "signal_ts": ("INTEGER", None),
                  "stop_pct": ("REAL", "-15.0"), "target_pct": ("REAL", "30.0"),
                  "max_hold_h": ("REAL", "48"), "slippage_pct": ("REAL", "1.5"),
                  "fee_pct": ("REAL", "0.3"),
                  "detail": ("TEXT", None)},  # schéma 3 : règles propres à une stratégie (JSON)
}


def book_key(strategy, version):
    return f"book:{strategy}@{version}"


def _migrate(conn):
    """Brings an older journal (schéma 1 = memebot avant le labo, 2 = labo) up to date, once."""
    row = conn.execute("SELECT v FROM kv WHERE k='schema'").fetchone()
    if row and row[0] == SCHEMA_VERSION:
        return
    for table, cols in _MIGRATION.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, (typ, old_value) in cols.items():
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
                if old_value is not None:
                    conn.execute(f"UPDATE {table} SET {col}={old_value} WHERE {col} IS NULL")
    old_book = conn.execute("SELECT v FROM kv WHERE k='book'").fetchone()
    if old_book is not None:
        conn.execute("INSERT OR REPLACE INTO kv VALUES (?, ?)",
                     (book_key("breakout", 1), old_book[0]))
        conn.execute("DELETE FROM kv WHERE k='book'")
    conn.execute("INSERT OR REPLACE INTO kv VALUES ('schema', ?)", (SCHEMA_VERSION,))


def connect(path=None):
    path = path or C.DB_PATH
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


def get_book(conn, strategy, version):
    row = conn.execute("SELECT v FROM kv WHERE k=?", (book_key(strategy, version),)).fetchone()
    return float(row[0]) if row else C.PAPER_START_BOOK


def add_to_book(conn, strategy, version, delta):
    conn.execute("INSERT OR REPLACE INTO kv VALUES (?, ?)",
                 (book_key(strategy, version), str(get_book(conn, strategy, version) + delta)))
