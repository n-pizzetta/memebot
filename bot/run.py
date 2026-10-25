"""One cycle of the pipeline. Schedule it (GitHub Actions / cron); it exits when done.

PAPER ONLY: this program holds no key and cannot place an order.
"""
from datetime import datetime, timezone

from . import clients, db, logic
from . import config as C


def iso(dt):
    return dt.isoformat(timespec="seconds")


def hours_between(a_iso, b):
    return (b - datetime.fromisoformat(a_iso)).total_seconds() / 3600


def update_positions(conn, now, log):
    rows = conn.execute("SELECT * FROM positions WHERE closed_ts IS NULL").fetchall()
    if not rows:
        return
    try:
        prices = clients.token_prices([r["mint"] for r in rows])
    except Exception as e:
        log(f"price update failed: {e!r}")
        return
    for r in rows:
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
        reason = logic.exit_reason(r["entry_px"], px, held)
        if reason:
            close(conn, r, now, px, reason)


def close(conn, r, now, price, reason):
    pnl = logic.realised_pnl(r["size_usd"], r["entry_px"], price)
    conn.execute("UPDATE positions SET closed_ts=?, exit_price=?, pnl_usd=?, exit_reason=? "
                 "WHERE id=?", (iso(now), price, pnl, reason, r["id"]))
    db.add_to_book(conn, pnl)


def risk_state(conn, now):
    today = now.date().isoformat()
    day_pnl = conn.execute("SELECT COALESCE(SUM(pnl_usd),0) FROM positions "
                           "WHERE substr(closed_ts,1,10)=?", (today,)).fetchone()[0]
    closed = conn.execute("SELECT pnl_usd, closed_ts FROM positions WHERE closed_ts IS NOT NULL "
                          "ORDER BY closed_ts DESC LIMIT 50").fetchall()
    streak = 0
    for c in closed:
        if c["pnl_usd"] < 0:
            streak += 1
        else:
            break
    last_loss = next((c["closed_ts"] for c in closed if c["pnl_usd"] < 0), None)
    opened = conn.execute("SELECT COUNT(*), COALESCE(SUM(size_usd),0) FROM positions "
                          "WHERE closed_ts IS NULL").fetchone()
    return {
        "day_pnl": day_pnl, "loss_streak": streak,
        "hours_since_last_loss": hours_between(last_loss, now) if last_loss else None,
        "open_count": opened[0], "open_exposure": opened[1],
    }


def deep_check(p):
    """On-chain and RugCheck gates. Any error rejects the token (fail closed)."""
    try:
        acct = clients.mint_account(p["mint"])
        reason = logic.mint_gate(acct)
        if reason:
            return reason
        supply = acct["data"]["parsed"]["info"]["supply"]
        largest = clients.largest_accounts(p["mint"])
        owned = clients.program_owned([a["address"] for a in largest])
        reason = logic.holder_gate(logic.top10_pct(largest, owned, supply))
        if reason:
            return reason
        if C.USE_RUGCHECK:
            return logic.rugcheck_gate(clients.rugcheck_summary(p["mint"]))
        return None
    except Exception as e:
        return f"check_error:{type(e).__name__}"


def main():
    now = datetime.now(timezone.utc)
    conn = db.connect()
    cur = conn.execute("INSERT INTO runs (ts, status) VALUES (?, 'running')", (iso(now),))
    run_id = cur.lastrowid
    notes = []
    log = notes.append

    # 1. collect -------------------------------------------------------------
    pools = []
    for page in range(1, C.TRENDING_PAGES + 1):
        try:
            pools += logic.parse_pools(clients.trending_pools(page), now)
        except Exception as e:
            log(f"trending page {page} failed: {e!r}")
    pools = logic.dedupe_by_mint(pools)
    feed_ok = len(pools) > 0 and not notes

    # 2. manage open paper positions first ----------------------------------------
    update_positions(conn, now, log)

    # 3. gates -> signal -> risk -> paper entry ---------------------------------------
    def seen(p, verdict):
        conn.execute("INSERT INTO seen VALUES (?,?,?,?,?,?,?,?,?)",
                     (run_id, p["mint"], p["pool"], p["name"], p["age_h"], p["liq"],
                      p["vol24"], p["price"], verdict))

    candidates = []
    for p in pools:
        reason = logic.cheap_filter(p)
        if reason:
            seen(p, reason)
        else:
            candidates.append(p)
    candidates.sort(key=lambda p: p["vol24"], reverse=True)
    for p in candidates[C.MAX_DEEP_CHECKS:]:
        seen(p, "skipped_budget")
    candidates = candidates[:C.MAX_DEEP_CHECKS]

    held = {r[0] for r in conn.execute("SELECT mint FROM positions WHERE closed_ts IS NULL")}
    n_signals = 0
    for p in candidates:
        reason = deep_check(p)
        if reason:
            seen(p, reason)
            continue
        try:
            sig = logic.breakout(clients.ohlcv_hourly(p["pool"]))
        except Exception as e:
            seen(p, f"ohlcv_error:{type(e).__name__}")
            continue
        if not sig:
            seen(p, "passed_no_signal")
            continue
        seen(p, "signal")
        n_signals += 1

        if p["mint"] in held:
            action = "already_held"
        else:
            state = risk_state(conn, now)
            book = db.get_book(conn)
            action = logic.entry_block(feed_ok=feed_ok, book=book, **state) or "paper_entry"
            if action == "paper_entry":
                conn.execute("INSERT INTO positions (mint, pool, name, opened_ts, entry_px, "
                             "size_usd, last_px) VALUES (?,?,?,?,?,?,?)",
                             (p["mint"], p["pool"], p["name"], iso(now),
                              logic.entry_fill(p["price"]), logic.position_size(book), p["price"]))
                held.add(p["mint"])
        conn.execute("INSERT INTO signals (run_id, ts, mint, pool, name, price, prior_high, vol, "
                     "median_vol, action) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (run_id, iso(now), p["mint"], p["pool"], p["name"], p["price"],
                      sig["prior_high"], sig["vol"], sig["median_vol"], action))

    conn.execute("UPDATE runs SET finished_ts=?, status=?, note=?, pools_seen=?, deep_checked=?, "
                 "signals=? WHERE id=?",
                 (iso(datetime.now(timezone.utc)), "ok" if feed_ok else "degraded",
                  " | ".join(notes)[:1000], len(pools), len(candidates), n_signals, run_id))
    conn.commit()
    print(f"run {run_id}: {len(pools)} pools, {len(candidates)} deep-checked, "
          f"{n_signals} signals, book ${db.get_book(conn):,.2f}"
          + (f" | {' | '.join(notes)}" if notes else ""))


if __name__ == "__main__":
    main()
