"""Pure decision logic: no network, no database. Everything here is unit-tested.

Convention: a gate returns None when the token passes, or a short rejection
reason string when it fails. Unknown or unreadable data always fails (fail closed).
"""
from datetime import datetime
from statistics import median

from . import config as C


# ---------- parsing ----------------------------------------------------------

def parse_pools(payload, now):
    """GeckoTerminal pools payload -> list of flat dicts."""
    out = []
    for p in (payload or {}).get("data", []):
        a = p.get("attributes", {})
        base_id = p.get("relationships", {}).get("base_token", {}).get("data", {}).get("id", "")
        mint = base_id.split("_", 1)[1] if "_" in base_id else ""
        try:
            created = datetime.fromisoformat(a["pool_created_at"].replace("Z", "+00:00"))
            out.append({
                "pool": a["address"],
                "mint": mint,
                "name": a.get("name", ""),
                "age_h": (now - created).total_seconds() / 3600,
                "liq": float(a.get("reserve_in_usd") or 0),
                "vol24": float((a.get("volume_usd") or {}).get("h24") or 0),
                "price": float(a.get("base_token_price_usd") or 0),
            })
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return out


def dedupe_by_mint(pools):
    """Keep the deepest pool for each token."""
    best = {}
    for p in pools:
        if p["mint"] not in best or p["liq"] > best[p["mint"]]["liq"]:
            best[p["mint"]] = p
    return list(best.values())


# ---------- gates ------------------------------------------------------------

def cheap_filter(p):
    if not p["mint"] or p["mint"] in C.SKIP_MINTS:
        return "base_is_sol_or_stable"
    if p["price"] <= 0:
        return "no_price"
    if p["age_h"] < C.MIN_AGE_H:
        return "too_young"
    if p["age_h"] > C.MAX_AGE_H:
        return "too_old"
    if p["liq"] < C.MIN_LIQ_USD:
        return "low_liquidity"
    if p["vol24"] < C.MIN_VOL_24H_USD:
        return "low_volume"
    return None


def mint_gate(account):
    """account = RPC getAccountInfo 'value' with jsonParsed encoding."""
    if not account:
        return "mint_not_found"
    try:
        info = account["data"]["parsed"]["info"]
    except (KeyError, TypeError):
        return "mint_parse_error"
    if info.get("mintAuthority"):
        return "mint_authority_active"
    if info.get("freezeAuthority"):
        return "freeze_authority_active"
    exts = {e.get("extension") for e in (info.get("extensions") or []) if isinstance(e, dict)}
    bad = sorted(exts & C.BANNED_TOKEN2022_EXTENSIONS)
    if bad:
        return f"token2022_{bad[0]}"
    return None


def top10_pct(largest, is_program_owned, supply_raw):
    """Share of supply held by the 10 largest accounts NOT owned by a program
    (pools, lockers and other PDAs are excluded). Unknown owners count as holders."""
    supply = int(supply_raw)
    if supply <= 0:
        return 100.0
    holders = [a for a in largest if not is_program_owned.get(a["address"], False)]
    held = sum(int(a["amount"]) for a in holders[:10])
    return held / supply * 100


def holder_gate(pct):
    return f"top10_{pct:.0f}pct" if pct > C.MAX_TOP10_PCT else None


def rugcheck_gate(summary):
    if not summary or not isinstance(summary, dict):
        return "rugcheck_unavailable"
    danger = [r for r in summary.get("risks") or []
              if str(r.get("level", "")).lower() == "danger"]
    if danger:
        return "rugcheck_danger:" + str(danger[0].get("name", "unknown"))[:40]
    return None


# ---------- signal -------------------------------------------------------------

def breakout(ohlcv):
    """ohlcv: list of [ts, open, high, low, close, volume], newest first
    (GeckoTerminal order). Index 0 is the still-open candle and is ignored."""
    need = C.BREAKOUT_LOOKBACK_H + 2
    if not ohlcv or len(ohlcv) < need:
        return None
    last = ohlcv[1]
    prior = ohlcv[2:need]
    prior_high = max(float(c[2]) for c in prior)
    med_vol = median(float(c[5]) for c in prior)
    close, vol = float(last[4]), float(last[5])
    if med_vol > 0 and close > prior_high and vol >= C.VOLUME_MULT * med_vol:
        return {"close": close, "prior_high": prior_high,
                "vol": vol, "median_vol": med_vol, "candle_ts": int(last[0])}
    return None


# ---------- risk -------------------------------------------------------------

def position_size(book):
    """Fixed fraction of the CURRENT book. Never a function of the last trade."""
    if book <= 0:
        return 0.0
    by_risk = book * C.RISK_PER_TRADE / (abs(C.STOP_PCT) / 100)
    return min(by_risk, book * C.MAX_POSITION_FRACTION)


def entry_block(*, feed_ok, open_count, open_exposure, book, day_pnl,
                loss_streak, hours_since_last_loss):
    """Returns the breaker that blocks a new entry, or None."""
    if not feed_ok:
        return "breaker_stale_feed"
    if book <= 0:
        return "breaker_book_empty"
    day_start = book - day_pnl
    if day_pnl <= -C.DAILY_LOSS_CAP * day_start:
        return "breaker_daily_loss"
    if (loss_streak >= C.MAX_LOSS_STREAK and hours_since_last_loss is not None
            and hours_since_last_loss < C.LOSS_STREAK_PAUSE_H):
        return "breaker_loss_streak"
    if open_count >= C.MAX_OPEN_POSITIONS:
        return "max_positions"
    if open_exposure + position_size(book) > book * C.MAX_EXPOSURE_FRACTION:
        return "max_exposure"
    return None


def entry_fill(price):
    return price * (1 + C.SLIPPAGE_PCT / 100)


def exit_reason(entry_px, price, held_h):
    """entry_px is the (slipped) fill. Stops are checked only at each run,
    so a gap through the stop is realised at the observed price, not at the stop."""
    move = (price * (1 - C.SLIPPAGE_PCT / 100) / entry_px - 1) * 100
    if move <= C.STOP_PCT:
        return "stop"
    if move >= C.TARGET_PCT:
        return "target"
    if held_h >= C.MAX_HOLD_H:
        return "time"
    return None


def realised_pnl(size, entry_px, exit_price):
    exit_px = exit_price * (1 - C.SLIPPAGE_PCT / 100)
    gross = size * (exit_px / entry_px - 1)
    fees = size * C.FEE_PCT / 100 * 2
    return max(gross - fees, -size)
