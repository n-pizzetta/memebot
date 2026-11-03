"""Cassure de plus haut avec volume sur les memecoins Solana "survivants" (24 h – 7 j)."""
from dataclasses import replace

from .. import clients, logic
from .. import config as C
from ..config import Risk
from . import Version

NAME = "breakout"
ACTIVE = 2
REFERENCE = "SOL"   # on compare au fait de simplement garder du SOL

LOOKBACK_H = 24     # la bougie horaire close doit dépasser le plus haut des 24 h précédentes
VOLUME_MULT = 1.5   # ... avec un volume >= 1,5 x la médiane des 24 h précédentes

VERSIONS = {
    1: Version(
        risk=Risk(),
        since="2026-10-25",
        hypothesis="lab/hypotheses/001-breakout.md",
        note="Version d'origine.",
    ),
    2: Version(
        # Même signal, mêmes sorties. Position plafonnée pour qu'un rug coûte au plus 2 % du
        # capital (en v1, deux rugs ont coûté 6 % chacun malgré le stop à -15 %).
        risk=replace(Risk(), max_position_fraction=C.MAX_LOSS_ON_TOTAL_FAILURE),
        since="2026-11-03",
        hypothesis="lab/hypotheses/002-breakout-v2.md",
        note="Une bougie ne peut ouvrir qu'un trade ; position max 2 % du capital.",
    ),
}


def prices(mints):
    return clients.token_prices(mints)


def _deep_check(p):
    """On-chain and RugCheck gates. Any error rejects the token (fail closed)."""
    step = "mint"
    try:
        acct = clients.mint_account(p["mint"])
        reason = logic.mint_gate(acct)
        if reason:
            return reason
        supply = acct["data"]["parsed"]["info"]["supply"]
        step = "holders"
        largest = clients.largest_accounts(p["mint"])
        owned = clients.program_owned([a["address"] for a in largest])
        reason = logic.holder_gate(logic.top10_pct(largest, owned, supply))
        if reason:
            return reason
        if C.USE_RUGCHECK:
            return logic.rugcheck_gate(clients.rugcheck_summary(p["mint"]))
        return None
    except Exception as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        return f"check_error:{step}:{status or type(e).__name__}"


def _collect(now, log):
    """Returns (pools, feed_ok). The trending feed is critical, top-volume is not."""
    pools, failed = [], False
    for page in range(1, C.TRENDING_PAGES + 1):
        try:
            pools += logic.parse_pools(clients.trending_pools(page), now)
        except Exception as e:
            failed = True
            log(f"trending page {page} failed: {e!r}")
    feed_ok = len(pools) > 0 and not failed
    for page in range(1, C.TOP_VOLUME_PAGES + 1):
        try:
            pools += logic.parse_pools(clients.top_volume_pools(page), now)
        except Exception as e:
            log(f"top-volume page {page} failed (non-critical): {e!r}")
    return logic.dedupe_by_mint(pools), feed_ok


def step(ctx):
    pools, feed_ok = _collect(ctx.now, ctx.log)
    desk = ctx.desk(feed_ok=feed_ok)

    candidates = []
    for p in pools:
        reason = logic.cheap_filter(p)
        if reason:
            desk.seen(p, reason)
        else:
            candidates.append(p)
    candidates.sort(key=lambda p: p["vol24"], reverse=True)
    for p in candidates[C.MAX_DEEP_CHECKS:]:
        desk.seen(p, "skipped_budget")
    candidates = candidates[:C.MAX_DEEP_CHECKS]

    n_signals = 0
    for p in candidates:
        reason = _deep_check(p)
        if reason:
            desk.seen(p, reason)
            continue
        try:
            sig = logic.breakout(clients.ohlcv_hourly(p["pool"], LOOKBACK_H + 4),
                                 LOOKBACK_H, VOLUME_MULT)
        except Exception as e:
            desk.seen(p, f"ohlcv_error:{type(e).__name__}")
            continue
        if not sig:
            desk.seen(p, "passed_no_signal")
            continue
        desk.seen(p, "signal")
        n_signals += 1
        desk.consider(mint=p["mint"], pool=p["pool"], name=p["name"], price=p["price"],
                      signal_ts=sig["candle_ts"], prior_high=sig["prior_high"],
                      vol=sig["vol"], median_vol=sig["median_vol"])

    return {"feed_ok": feed_ok, "pools_seen": len(pools), "deep_checked": len(candidates),
            "signals": n_signals}
