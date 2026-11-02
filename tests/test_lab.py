"""Le labo : journal par stratégie-version, garde-fous globaux, migration, cycle.

Ces tests protègent les règles de LAB.md. Si l'un échoue, le bot ne tourne pas.
"""
import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from bot import config as C
from bot import db, paper, run
from bot.config import Risk
from bot.strategies import REGISTRY

NOW = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
R = Risk(max_position_fraction=0.02)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(str(tmp_path / "j.db"))
    yield c
    c.close()


def desk(conn, version=2, now=NOW, risk=R, feed_ok=True):
    return paper.Desk(conn, strategy="breakout", version=version, risk=risk, run_id=1,
                      now=now, feed_ok=feed_ok)


def open_rows(conn):
    return conn.execute("SELECT * FROM positions WHERE closed_ts IS NULL").fetchall()


# ---- garde-fous globaux ------------------------------------------------------------

def test_every_strategy_is_well_formed():
    for name, m in REGISTRY.items():
        assert m.NAME == name
        assert m.ACTIVE is None or m.ACTIVE in m.VERSIONS
        assert callable(m.prices) and callable(m.step)
        for v in m.VERSIONS.values():
            assert v.hypothesis.startswith("lab/hypotheses/")


def test_a_rug_never_costs_more_than_the_lab_limit_on_active_versions():
    for m in REGISTRY.values():
        if m.ACTIVE is not None:
            r = m.VERSIONS[m.ACTIVE].risk
            assert r.max_position_fraction <= C.MAX_LOSS_ON_TOTAL_FAILURE


def test_no_code_path_can_sign_a_transaction():
    import pathlib
    src = " ".join(p.read_text() for p in pathlib.Path("bot").rglob("*.py"))
    for forbidden in ("Keypair", "sign_message", "send_transaction", "sendTransaction",
                      "private_key", "PRIVATE_KEY"):
        assert forbidden not in src


# ---- desk : décisions ----------------------------------------------------------------

def test_same_signal_cannot_be_traded_twice_even_after_close(conn):
    d = desk(conn)
    assert d.consider(mint="M", pool="P", name="X", price=1.0, signal_ts=100) == "paper_entry"
    assert d.consider(mint="M", pool="P", name="X", price=1.0, signal_ts=100) == "already_held"
    paper.close(conn, open_rows(conn)[0], NOW, 1.4, "target")
    assert d.consider(mint="M", pool="P", name="X", price=1.4, signal_ts=100) == "same_signal"
    assert d.consider(mint="M", pool="P", name="X", price=1.5, signal_ts=200) == "paper_entry"


def test_position_is_capped_so_a_rug_costs_at_most_2pct(conn):
    d = desk(conn)
    d.consider(mint="M", pool="P", name="X", price=1.0, signal_ts=1)
    pos = open_rows(conn)[0]
    assert pos["size_usd"] == pytest.approx(C.PAPER_START_BOOK * 0.02)
    pnl = paper.close(conn, pos, NOW, 0.0, "stop")
    assert -pnl <= C.PAPER_START_BOOK * C.MAX_LOSS_ON_TOTAL_FAILURE + 1e-9


def test_books_and_breakers_are_isolated_per_version(conn):
    v1 = desk(conn, version=1, risk=Risk())
    v2 = desk(conn, version=2)
    v1.consider(mint="A", pool="P", name="A", price=1.0, signal_ts=1)
    paper.close(conn, open_rows(conn)[0], NOW, 0.0, "stop")      # v1 loses its position
    assert db.get_book(conn, "breakout", 1) < C.PAPER_START_BOOK
    assert db.get_book(conn, "breakout", 2) == C.PAPER_START_BOOK
    assert v2.state()["day_pnl"] == 0
    # v1 holding a token doesn't stop v2 from taking its own position
    v1.consider(mint="B", pool="P", name="B", price=1.0, signal_ts=5)
    assert v2.consider(mint="B", pool="P", name="B", price=1.0, signal_ts=5) == "paper_entry"


def test_breakers_still_fire_through_the_desk(conn):
    assert desk(conn, feed_ok=False).decide("M", 1) == "breaker_stale_feed"
    d = desk(conn)
    for i in range(3):  # 3 x ~-10,6 $ > 3 % du capital sur la journée
        d.consider(mint=f"L{i}", pool="P", name="L", price=1.0, signal_ts=i)
        paper.close(conn, open_rows(conn)[0], NOW, 0.5, "stop")
    assert d.decide("NEW", 99) == "breaker_daily_loss"


def test_loss_streak_breaker_through_the_desk(conn):
    d = desk(conn, risk=Risk(max_position_fraction=0.02, daily_loss_cap=1.0))
    for i in range(d.risk.max_loss_streak):
        d.consider(mint=f"L{i}", pool="P", name="L", price=1.0, signal_ts=i)
        paper.close(conn, open_rows(conn)[0], NOW, 0.5, "stop")
    assert d.decide("NEW", 99) == "breaker_loss_streak"


def test_signals_are_journaled_with_strategy_and_version(conn):
    desk(conn).consider(mint="M", pool="P", name="X", price=1.0, signal_ts=7, prior_high=0.9)
    row = conn.execute("SELECT strategy, version, signal_ts, action FROM signals").fetchone()
    assert tuple(row) == ("breakout", 2, 7, "paper_entry")


# ---- sorties : chaque position garde ses propres règles ----------------------------------

def test_retired_version_exits_with_its_own_rules(conn):
    desk(conn, version=1, risk=Risk(stop_pct=-15.0)).consider(
        mint="OLD", pool="P", name="O", price=1.0, signal_ts=1)
    desk(conn, version=2, risk=Risk(stop_pct=-50.0, max_position_fraction=0.02)).consider(
        mint="NEW", pool="P", name="N", price=1.0, signal_ts=1)
    paper.manage_open_positions(conn, NOW + timedelta(hours=1),
                                {"breakout": lambda mints: {m: 0.75 for m in mints}}, print)
    still_open = {r["mint"] for r in open_rows(conn)}
    assert still_open == {"NEW"}  # -25 % : stop v1 (-15 %) touché, pas celui à -50 %


def test_missing_price_three_times_is_counted_as_rug(conn):
    desk(conn).consider(mint="M", pool="P", name="X", price=1.0, signal_ts=1)
    for _ in range(C.MISSES_BEFORE_ASSUMED_RUG):
        paper.manage_open_positions(conn, NOW, {"breakout": lambda mints: {}}, print)
    row = conn.execute("SELECT exit_reason, pnl_usd, size_usd FROM positions").fetchone()
    assert row["exit_reason"] == "price_missing_assumed_rug"
    assert row["pnl_usd"] == -row["size_usd"]


# ---- migration du journal d'avant le labo ---------------------------------------------------

OLD_SCHEMA = """
CREATE TABLE runs (id INTEGER PRIMARY KEY, ts TEXT, finished_ts TEXT, status TEXT, note TEXT,
  pools_seen INTEGER DEFAULT 0, deep_checked INTEGER DEFAULT 0, signals INTEGER DEFAULT 0);
CREATE TABLE seen (run_id INTEGER, mint TEXT, pool TEXT, name TEXT, age_h REAL, liq REAL,
  vol24 REAL, price REAL, verdict TEXT);
CREATE TABLE signals (id INTEGER PRIMARY KEY, run_id INTEGER, ts TEXT, mint TEXT, pool TEXT,
  name TEXT, price REAL, prior_high REAL, vol REAL, median_vol REAL, action TEXT);
CREATE TABLE positions (id INTEGER PRIMARY KEY, mint TEXT, pool TEXT, name TEXT, opened_ts TEXT,
  entry_px REAL, size_usd REAL, last_px REAL, misses INTEGER DEFAULT 0, closed_ts TEXT,
  exit_price REAL, pnl_usd REAL, exit_reason TEXT);
CREATE TABLE kv (k TEXT PRIMARY KEY, v TEXT);
INSERT INTO kv VALUES ('book', '814.34');
INSERT INTO positions (mint, opened_ts, entry_px, size_usd, last_px)
  VALUES ('FLOAT', '2026-11-02T21:01:01+00:00', 1.0, 54.29, 1.0);
INSERT INTO seen VALUES (1, 'M', 'P', 'X', 30, 1, 1, 1, 'too_young');
"""


def test_old_journal_is_migrated_to_breakout_v1(tmp_path):
    path = str(tmp_path / "old.db")
    raw = sqlite3.connect(path)
    raw.executescript(OLD_SCHEMA)
    raw.commit()
    raw.close()
    conn = db.connect(path)
    assert db.get_book(conn, "breakout", 1) == pytest.approx(814.34)
    assert conn.execute("SELECT v FROM kv WHERE k='book'").fetchone() is None
    pos = conn.execute("SELECT * FROM positions").fetchone()
    assert (pos["strategy"], pos["version"], pos["stop_pct"], pos["slippage_pct"]) == \
        ("breakout", 1, -15.0, 1.5)
    assert tuple(conn.execute("SELECT strategy, version FROM seen").fetchone()) == ("breakout", 1)
    conn.close()
    db.connect(path).close()  # a second connect is a no-op


# ---- cycle complet -------------------------------------------------------------------

def fake_strategy(name, crash=False):
    def step(ctx):
        if crash:
            raise RuntimeError("boom")
        ctx.desk().consider(mint=f"{name}-M", pool="P", name="X", price=1.0, signal_ts=1)
        return {"feed_ok": True, "pools_seen": 3, "deep_checked": 1, "signals": 1}
    return SimpleNamespace(NAME=name, ACTIVE=1, prices=lambda mints: {m: 1.0 for m in mints},
                           VERSIONS={1: SimpleNamespace(risk=R)}, step=step)


def test_a_crashing_strategy_degrades_the_run_but_not_the_others(conn):
    reg = {"bad": fake_strategy("bad", crash=True), "good": fake_strategy("good")}
    run_id, ok, totals, notes = run.cycle(conn, NOW, reg, sol_price=lambda: 150.0)
    assert not ok and totals["signals"] == 1
    assert [r["strategy"] for r in open_rows(conn)] == ["good"]
    status, sol = conn.execute("SELECT status, sol_px FROM runs WHERE id=?", (run_id,)).fetchone()
    assert (status, sol) == ("degraded", 150.0)
    assert any("bad: step crashed" in n for n in notes)


def test_sol_price_failure_is_not_critical(conn):
    def boom():
        raise RuntimeError("api down")
    _, ok, _, _ = run.cycle(conn, NOW, {"good": fake_strategy("good")}, sol_price=boom)
    assert ok


# ---- rapport : la référence SOL ne compare que des périodes identiques ------------------------

def test_sol_reference_needs_prices_from_the_start_of_the_period(conn):
    from bot import report
    for ts, px in (("2026-11-03T12:00:00+00:00", 100.0), ("2026-11-10T12:00:00+00:00", 110.0)):
        conn.execute("INSERT INTO runs (ts, status, sol_px) VALUES (?, 'ok', ?)", (ts, px))
    assert report._sol_return(conn, "2026-11-03T11:30:00+00:00") == pytest.approx(0.10)
    assert report._sol_return(conn, "2026-10-25T13:00:00+00:00") is None  # v1 : trop tôt
