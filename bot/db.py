"""SQLite journal: every token seen, every rejection and why, every paper trade."""
import os
import sqlite3

from . import config as C

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY, ts TEXT, finished_ts TEXT, status TEXT, note TEXT,
  pools_seen INTEGER DEFAULT 0, deep_checked INTEGER DEFAULT 0, signals INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS seen (
  run_id INTEGER, mint TEXT, pool TEXT, name TEXT, age_h REAL, liq REAL, vol24 REAL,
  price REAL, verdict TEXT);
CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY, run_id INTEGER, ts TEXT, mint TEXT, pool TEXT, name TEXT,
  price REAL, prior_high REAL, vol REAL, median_vol REAL, action TEXT);
CREATE TABLE IF NOT EXISTS positions (
  id INTEGER PRIMARY KEY, mint TEXT, pool TEXT, name TEXT, opened_ts TEXT,
  entry_px REAL, size_usd REAL, last_px REAL, misses INTEGER DEFAULT 0,
  closed_ts TEXT, exit_price REAL, pnl_usd REAL, exit_reason TEXT);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
"""


def connect(path=None):
    path = path or C.DB_PATH
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    if conn.execute("SELECT v FROM kv WHERE k='book'").fetchone() is None:
        conn.execute("INSERT INTO kv VALUES ('book', ?)", (str(C.PAPER_START_BOOK),))
    conn.commit()
    return conn


def get_book(conn):
    return float(conn.execute("SELECT v FROM kv WHERE k='book'").fetchone()[0])


def add_to_book(conn, delta):
    conn.execute("UPDATE kv SET v=? WHERE k='book'", (str(get_book(conn) + delta),))
