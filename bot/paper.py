"""Paper broker shared by every strategy: sizing, breakers, fills, exits, books.

PAPER ONLY: nothing here can sign or send a transaction. A strategy decides *what*
it would trade; this module decides *whether* the risk rules allow it and journals it.
"""
import json
from datetime import datetime

from . import config as C
from . import db, logic


def iso(dt):
    return dt.isoformat(timespec="seconds")


def hours_between(a_iso, b):
    return (b - datetime.fromisoformat(a_iso)).total_seconds() / 3600


class Desk:
    """The trading desk of ONE strategy version, for ONE run."""

    def __init__(self, conn, *, strategy, version, risk, run_id, now, feed_ok=True):
        self.conn, self.strategy, self.version, self.risk = conn, strategy, version, risk
        self.run_id, self.now, self.feed_ok = run_id, now, feed_ok

    # ---- state ------------------------------------------------------------------
    @property
    def book(self):
        return db.get_book(self.conn, self.strategy, self.version)

    def _mine(self):
        return "strategy=? AND version=?", (self.strategy, self.version)

    def state(self):
        where, args = self._mine()
        today = self.now.date().isoformat()
        day_pnl = self.conn.execute(
            f"SELECT COALESCE(SUM(pnl_usd),0) FROM positions WHERE {where} "
            "AND substr(closed_ts,1,10)=?", (*args, today)).fetchone()[0]
        closed = self.conn.execute(
            f"SELECT pnl_usd, closed_ts FROM positions WHERE {where} AND closed_ts IS NOT NULL "
            "ORDER BY closed_ts DESC LIMIT 50", args).fetchall()
        streak = 0
        for c in closed:
            if c["pnl_usd"] < 0:
                streak += 1
            else:
                break
        last_loss = next((c["closed_ts"] for c in closed if c["pnl_usd"] < 0), None)
        opened = self.conn.execute(
            f"SELECT COUNT(*), COALESCE(SUM(size_usd),0) FROM positions WHERE {where} "
            "AND closed_ts IS NULL", args).fetchone()
        return {
            "day_pnl": day_pnl, "loss_streak": streak,
            "hours_since_last_loss": hours_between(last_loss, self.now) if last_loss else None,
            "open_count": opened[0], "open_exposure": opened[1],
        }

    # ---- decisions ----------------------------------------------------------------
    def decide(self, mint, signal_ts):
        """'paper_entry' if the rules allow a new position, else the reason why not."""
        where, args = self._mine()
        if self.conn.execute(f"SELECT 1 FROM positions WHERE {where} AND mint=? "
                             "AND closed_ts IS NULL", (*args, mint)).fetchone():
            return "already_held"
        if signal_ts is not None and self.conn.execute(
                f"SELECT 1 FROM positions WHERE {where} AND mint=? AND signal_ts=?",
                (*args, mint, signal_ts)).fetchone():
            return "same_signal"  # this exact signal was already traded (even if closed since)
        return logic.entry_block(self.risk, feed_ok=self.feed_ok, book=self.book,
                                 **self.state()) or "paper_entry"

    def open(self, *, mint, pool, name, price, signal_ts):
        r = self.risk
        size = logic.position_size(self.book, r)
        self.conn.execute(
            "INSERT INTO positions (mint, pool, name, opened_ts, entry_px, size_usd, last_px, "
            "strategy, version, signal_ts, stop_pct, target_pct, max_hold_h, slippage_pct, fee_pct) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (mint, pool, name, iso(self.now), logic.entry_fill(price, r.slippage_pct), size, price,
             self.strategy, self.version, signal_ts, r.stop_pct, r.target_pct, r.max_hold_h,
             r.slippage_pct, r.fee_pct))
        return size

    def consider(self, *, mint, pool, name, price, signal_ts, prior_high=None, vol=None,
                 median_vol=None, detail=None):
        """decide + open + journal the signal. Returns the action taken."""
        action = self.decide(mint, signal_ts)
        if action == "paper_entry":
            self.open(mint=mint, pool=pool, name=name, price=price, signal_ts=signal_ts)
        self.conn.execute(
            "INSERT INTO signals (run_id, ts, mint, pool, name, price, prior_high, vol, median_vol, "
            "action, strategy, version, signal_ts, detail) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.run_id, iso(self.now), mint, pool, name, price, prior_high, vol, median_vol,
             action, self.strategy, self.version, signal_ts,
             json.dumps(detail) if detail is not None else None))
        return action

    def seen(self, p, verdict):
        self.conn.execute(
            "INSERT INTO seen (run_id, mint, pool, name, age_h, liq, vol24, price, verdict, "
            "strategy, version) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (self.run_id, p.get("mint"), p.get("pool"), p.get("name"), p.get("age_h"),
             p.get("liq"), p.get("vol24"), p.get("price"), verdict, self.strategy, self.version))


# ---- exits (all strategies, all versions, active or retired) --------------------------

def close(conn, r, now, price, reason):
    pnl = logic.realised_pnl(r["size_usd"], r["entry_px"], price,
                             slippage_pct=r["slippage_pct"], fee_pct=r["fee_pct"])
    conn.execute("UPDATE positions SET closed_ts=?, exit_price=?, pnl_usd=?, exit_reason=? "
                 "WHERE id=?", (iso(now), price, pnl, reason, r["id"]))
    db.add_to_book(conn, r["strategy"], r["version"], pnl)
    return pnl


def manage_open_positions(conn, now, price_fns, log):
    """price_fns: {strategy_name: f(list_of_mints) -> {mint: price}}.
    Each position is closed with the exit rules it was opened with."""
    rows = conn.execute("SELECT * FROM positions WHERE closed_ts IS NULL").fetchall()
    by_strategy = {}
    for r in rows:
        by_strategy.setdefault(r["strategy"], []).append(r)
    for strategy, positions in by_strategy.items():
        fn = price_fns.get(strategy)
        if fn is None:
            log(f"no price source for strategy {strategy!r}: {len(positions)} position(s) untouched")
            continue
        try:
            prices = fn([r["mint"] for r in positions])
        except Exception as e:
            log(f"{strategy}: price update failed: {e!r}")
            continue
        for r in positions:
            px = prices.get(r["mint"])
            held = hours_between(r["opened_ts"], now)
            if px is None or px <= 0:
                misses = r["misses"] + 1
                if misses >= C.MISSES_BEFORE_ASSUMED_RUG:
                    close(conn, r, now, 0.0, "price_missing_assumed_rug")
                else:
                    conn.execute("UPDATE positions SET misses=? WHERE id=?", (misses, r["id"]))
                continue
            conn.execute("UPDATE positions SET last_px=?, misses=0 WHERE id=?", (px, r["id"]))
            reason = logic.exit_reason(r["entry_px"], px, held, stop_pct=r["stop_pct"],
                                       target_pct=r["target_pct"], max_hold_h=r["max_hold_h"],
                                       slippage_pct=r["slippage_pct"])
            if reason:
                close(conn, r, now, px, reason)
