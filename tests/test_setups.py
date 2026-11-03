"""Stratégie setups : règles de clôture hebdomadaire, référence ETF, fichier des setups."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from bot import db, paper
from bot.strategies import setups as S

PARIS = S.PARIS


def bars_from(closes, start=date(2026, 9, 28), opens=None):
    """Weekday bars from `start` (a Monday) with the given closes."""
    out, d, i = [], start, 0
    while i < len(closes):
        if d.weekday() < 5:
            o = opens[i] if opens else closes[i]
            out.append(S.Bar(d, o, closes[i]))
            i += 1
        d += timedelta(days=1)
    return out


def yahoo_payload(bars):
    return {"chart": {"result": [{
        "meta": {"gmtoffset": 3600},
        "timestamp": [int(datetime(b.date.year, b.date.month, b.date.day, 8,
                                   tzinfo=timezone.utc).timestamp()) for b in bars],
        "indicators": {"quote": [{"open": [b.open for b in bars],
                                  "close": [b.close for b in bars]}]}}]}}


THALES = {"entry_date": "2026-09-30", "stop_close": 216.0, "stop_exit": 210.0,
          "target_close": 265.0, "target_exit": "close"}
ESSILOR = {"entry_date": "2026-10-16", "stop_close": 139.0, "stop_exit": "open",
           "target_close": 170.0, "target_exit": "close"}
SAT = datetime(2026, 10, 10, 10, tzinfo=PARIS)   # samedi : les semaines du 28/09 et du 05/10 sont closes


# ---- données ----------------------------------------------------------------------

def test_parse_yahoo_roundtrip_and_fails_closed():
    bars = bars_from([1.0, None, 3.0])
    assert S.parse_yahoo(yahoo_payload(bars)) == bars
    with pytest.raises(ValueError):
        S.parse_yahoo({"chart": {"result": None}})


def test_weekly_close_is_last_session_and_only_once_the_week_is_over():
    bars = bars_from([220, 221, 222, 223, 224, 230, 231, 232, 233, 234])
    assert S.weekly_closes(bars, SAT) == [(date(2026, 10, 2), 224), (date(2026, 10, 9), 234)]
    friday_4pm = datetime(2026, 10, 9, 16, tzinfo=PARIS)
    assert S.weekly_closes(bars, friday_4pm) == [(date(2026, 10, 2), 224)]


# ---- règles -------------------------------------------------------------------------

def test_intraday_dip_below_stop_does_not_count_only_weekly_close():
    bars = bars_from([226, 210, 205, 220, 225, 226, 226, 226, 226, 226])
    assert S.evaluate(THALES, bars, SAT) is None


def test_weekly_close_below_stop_exits_at_the_fixed_price():
    bars = bars_from([226, 225, 224, 220, 215, 226, 226, 226, 226, 226])
    assert S.evaluate(THALES, bars, SAT) == {"reason": "stop", "date": "2026-10-02",
                                             "price": 210.0, "week_close": 215}


def test_stop_at_next_open_waits_for_the_open():
    closes = [150] * 14 + [138]                      # vendredi 16/10 = entrée, 23/10 sous 139
    bars = bars_from(closes + [150] * 5, start=date(2026, 10, 5))
    sat = datetime(2026, 10, 24, 10, tzinfo=PARIS)
    assert S.evaluate(ESSILOR, bars[:15], sat) is None   # lundi pas encore coté
    monday = bars_from([150] * 20, start=date(2026, 10, 5))[15].date
    bars[15] = S.Bar(monday, 136.5, 137.0)
    assert S.evaluate(ESSILOR, bars, sat + timedelta(days=3)) == {
        "reason": "stop", "date": "2026-10-26", "price": 136.5, "week_close": 138}


def test_target_on_weekly_close():
    bars = bars_from([226, 230, 240, 250, 266, 226, 226, 226, 226, 226])
    assert S.evaluate(THALES, bars, SAT)["reason"] == "target"


def test_weeks_before_or_at_entry_are_ignored():
    bars = bars_from([150] * 4 + [100], start=date(2026, 10, 12))   # vendredi 16/10 = entrée
    assert S.evaluate(ESSILOR, bars, datetime(2026, 10, 17, 10, tzinfo=PARIS)) is None


def test_bench_return_uses_closes_on_or_before_dates():
    bench = bars_from([100, 101, 102, 103, 110])
    assert S.bench_return(bench, date(2026, 9, 30), date(2026, 10, 4)) == pytest.approx(0.0784,
                                                                                      abs=1e-3)


# ---- fichier des setups -----------------------------------------------------------------

def test_setups_file_of_the_repo_is_valid():
    found, errors = S.load_setups()
    assert errors == [] and {s["symbol"] for s in found} >= {"HO.PA", "EL.PA"}


def test_bad_lines_are_reported_not_guessed(tmp_path):
    f = tmp_path / "s.csv"
    f.write_text("symbol,name,entry_date,entry_px,stop_close,stop_exit,target_close\n"
                 "AAA,A,2026-10-01,10,12,open,11\n"
                 "BBB,B,pas-une-date,10,9,open,11\n"
                 "CCC,C,2026-10-01,10,9,open,11\n", encoding="utf-8")
    found, errors = S.load_setups(str(f))
    assert [s["symbol"] for s in found] == ["CCC"] and len(errors) == 2


# ---- intégration : step + manage ---------------------------------------------------------

@pytest.fixture
def conn(tmp_path):
    c = db.connect(str(tmp_path / "j.db"))
    yield c
    c.close()


def ctx_for(conn, now, notes):
    from types import SimpleNamespace
    return SimpleNamespace(conn=conn, now=now, run_id=1, log=notes.append,
                           desk=lambda feed_ok=True: paper.Desk(
                               conn, strategy=S.NAME, version=S.ACTIVE,
                               risk=S.VERSIONS[S.ACTIVE].risk, run_id=1, now=now,
                               feed_ok=feed_ok))


def test_step_opens_each_setup_once_at_its_own_date_and_price(conn):
    now = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
    for _ in range(3):
        S.step(ctx_for(conn, now, []))
    rows = conn.execute("SELECT mint, entry_px, opened_ts, size_usd FROM positions").fetchall()
    assert sorted((r["mint"], r["entry_px"]) for r in rows) == [("EL.PA", 153.2),
                                                                 ("HO.PA", 226.4)]
    assert {r["opened_ts"][:10] for r in rows} == {"2026-09-30", "2026-10-16"}
    assert all(r["size_usd"] == pytest.approx(20.0) for r in rows)    # 2 % de 1 000
    assert conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == 2  # pas de spam


def test_manage_closes_on_weekly_stop_and_records_benchmark(conn):
    now = datetime(2026, 10, 10, 10, tzinfo=PARIS)
    S.step(ctx_for(conn, now, []))
    thales = bars_from([226, 225, 224, 220, 215, 226, 226, 226, 226, 226])
    flat = bars_from([150] * 10)
    bench = bars_from([100, 100, 100, 100, 101, 101, 101, 101, 101, 101])
    feeds = {"HO.PA": thales, "EL.PA": flat, S.BENCHMARK: bench}
    rows = conn.execute("SELECT * FROM positions WHERE closed_ts IS NULL").fetchall()
    S.manage(conn, now, rows, print, fetch=lambda sym, start: yahoo_payload(feeds[sym]))
    t = conn.execute("SELECT * FROM positions WHERE mint='HO.PA'").fetchone()
    assert t["exit_reason"] == "stop" and t["exit_price"] == 210.0
    assert t["closed_ts"].startswith("2026-10-02")
    assert t["pnl_usd"] == pytest.approx(20 * (210 / 226.4 - 1) - 20 * 0.002 * 2)
    d = json.loads(t["detail"])
    assert d["bench_ret"] == pytest.approx(0.01) and d["week_close"] == 215
    assert conn.execute("SELECT closed_ts FROM positions WHERE mint='EL.PA'").fetchone()[0] is None


def test_manage_never_closes_when_prices_are_unavailable(conn):
    now = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
    S.step(ctx_for(conn, now, []))
    rows = conn.execute("SELECT * FROM positions").fetchall()

    def down(sym, start):
        raise RuntimeError("yahoo 429")
    notes = []
    for i in range(5):
        conn.execute("DELETE FROM kv WHERE k='setups:last_eval'")
        S.manage(conn, now + timedelta(hours=i), rows, notes.append, fetch=down)
    assert conn.execute("SELECT COUNT(*) FROM positions WHERE closed_ts IS NULL").fetchone()[0] == 2
    assert any("indisponible" in n for n in notes)


def test_manage_runs_at_most_once_per_hour(conn):
    now = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
    S.step(ctx_for(conn, now, []))
    rows = conn.execute("SELECT * FROM positions").fetchall()
    calls = []

    def fetch(sym, start):
        calls.append(sym)
        return yahoo_payload(bars_from([226] * 30))
    S.manage(conn, now, rows, print, fetch=fetch)
    S.manage(conn, now + timedelta(minutes=15), rows, print, fetch=fetch)
    assert len(calls) == 3      # benchmark + 2 titres, une seule fois
