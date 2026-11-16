"""Signaux fantômes (fiche 005) : mesure en lecture seule, règles de sortie de breakout v2."""
from datetime import datetime, timedelta, timezone

import pytest

from bot import db, ghost

T0 = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(str(tmp_path / "j.db"))
    yield c
    c.close()


def add_runs(conn, n, degraded=()):
    for i in range(1, n + 1):
        ts = (T0 + timedelta(minutes=15 * (i - 1))).isoformat(timespec="seconds")
        conn.execute("INSERT INTO runs (id, ts, status) VALUES (?,?,?)",
                     (i, ts, "degraded" if i in degraded else "ok"))


def ts(run_id):
    return (T0 + timedelta(minutes=15 * (run_id - 1))).isoformat(timespec="seconds")


def signal(conn, run_id, mint, price, action, signal_ts=1000):
    conn.execute("INSERT INTO signals (run_id, ts, mint, name, price, action, strategy, version, "
                 "signal_ts) VALUES (?,?,?,?,?,?,?,?,?)",
                 (run_id, ts(run_id), mint, mint, price, action, "breakout", 2, signal_ts))


def seen(conn, run_id, mint, price):
    conn.execute("INSERT INTO seen (run_id, mint, price, verdict, strategy, version) "
                 "VALUES (?,?,?,?,?,?)", (run_id, mint, price, "too_old", "breakout", 2))


def results(conn):
    risk = ghost._risk()
    return {s["first"]["mint"]: (s, ghost.replay(conn, s, risk))
            for s in ghost.distinct_signals(conn)}


def test_target_and_stop_use_v2_rules(conn):
    add_runs(conn, 5)
    signal(conn, 1, "UP", 1.0, "breaker_loss_streak")
    signal(conn, 1, "DOWN", 1.0, "paper_entry")
    seen(conn, 2, "UP", 1.1)
    seen(conn, 3, "UP", 1.5)
    seen(conn, 2, "DOWN", 0.8)
    r = results(conn)
    assert r["UP"][1]["reason"] == "target" and r["UP"][1]["ret"] > 0.3
    assert r["DOWN"][1]["reason"] == "stop" and r["DOWN"][1]["ret"] < -0.15
    assert r["DOWN"][0]["taken"] and not r["UP"][0]["taken"]


def test_missing_three_ok_runs_counts_as_rug_but_degraded_runs_do_not(conn):
    add_runs(conn, 8, degraded={3, 4})
    signal(conn, 1, "GONE", 1.0, "breaker_loss_streak")
    seen(conn, 2, "GONE", 1.05)
    # absent des runs 3 et 4 (dégradés, ne comptent pas), puis 5, 6, 7 (ok)
    g = results(conn)["GONE"][1]
    assert g["reason"] == "missing" and g["ret"] == -1.0 and g["exit_ts"] == ts(7)
    assert abs(g["last_seen_ret"]) < 0.05  # sortie au dernier prix vu, pas -100 %


def test_repeated_occurrences_of_one_signal_count_once_and_taken_if_any_entry(conn):
    add_runs(conn, 3)
    signal(conn, 1, "X", 1.0, "breaker_loss_streak")
    signal(conn, 2, "X", 1.1, "paper_entry")
    signal(conn, 2, "X", 1.1, "already_held", signal_ts=1000)
    [s] = ghost.distinct_signals(conn)
    assert s["taken"] and s["first"]["price"] == 1.0


def test_section_is_read_only(conn):
    add_runs(conn, 4)
    signal(conn, 1, "A", 1.0, "breaker_loss_streak")
    seen(conn, 2, "A", 2.0)
    before = conn.total_changes
    text = ghost.section(conn)
    assert conn.total_changes == before
    assert "bloqués" in text
    assert conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 0
