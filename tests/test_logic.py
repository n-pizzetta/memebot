"""Every gate and every breaker has a test. If one stops firing, the build fails."""
from datetime import datetime, timedelta, timezone

import pytest

from bot import config as C
from bot import logic

NOW = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
MINT = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"


def pool(**kw):
    p = {"pool": "P", "mint": MINT, "name": "X / SOL", "age_h": 48,
         "liq": 200_000, "vol24": 500_000, "price": 0.01}
    p.update(kw)
    return p


def mint_acct(**info):
    base = {"mintAuthority": None, "freezeAuthority": None, "supply": "1000", "decimals": 6}
    base.update(info)
    return {"data": {"parsed": {"info": base}}}


def candles(n=C.BREAKOUT_LOOKBACK_H + 2, high=1.0, vol=100.0, last_close=1.0, last_vol=100.0):
    rows = [[1000 - i, 1, high, 0.9, 0.95, vol] for i in range(n)]
    rows[1] = [999, 1, last_close, 0.9, last_close, last_vol]
    return rows


# ---- parsing -------------------------------------------------------------------

def test_parse_pools_extracts_mint_and_age():
    payload = {"data": [{
        "attributes": {"address": "POOL", "name": "X / SOL",
                       "pool_created_at": (NOW - timedelta(hours=30)).isoformat().replace("+00:00", "Z"),
                       "reserve_in_usd": "123456.7", "volume_usd": {"h24": "999"},
                       "base_token_price_usd": "0.002"},
        "relationships": {"base_token": {"data": {"id": f"solana_{MINT}"}}}},
        {"attributes": {"broken": True}}]}
    [p] = logic.parse_pools(payload, NOW)
    assert p["mint"] == MINT and round(p["age_h"]) == 30 and p["liq"] == 123456.7


def test_dedupe_keeps_deepest_pool():
    out = logic.dedupe_by_mint([pool(pool="a", liq=1), pool(pool="b", liq=9)])
    assert [p["pool"] for p in out] == ["b"]


# ---- cheap filter ------------------------------------------------------------------

@pytest.mark.parametrize("kw,reason", [
    ({"age_h": 2}, "too_young"),
    ({"age_h": 24 * 8}, "too_old"),
    ({"liq": 1_000}, "low_liquidity"),
    ({"vol24": 1_000}, "low_volume"),
    ({"price": 0}, "no_price"),
    ({"mint": "So11111111111111111111111111111111111111112"}, "base_is_sol_or_stable"),
])
def test_cheap_filter_rejects(kw, reason):
    assert logic.cheap_filter(pool(**kw)) == reason


def test_cheap_filter_passes_survivor():
    assert logic.cheap_filter(pool()) is None


# ---- contract gates ----------------------------------------------------------------

def test_mint_gate_rejects_active_mint_authority():
    assert logic.mint_gate(mint_acct(mintAuthority="Someone")) == "mint_authority_active"


def test_mint_gate_rejects_active_freeze_authority():
    assert logic.mint_gate(mint_acct(freezeAuthority="Someone")) == "freeze_authority_active"


def test_mint_gate_rejects_dangerous_token2022_extension():
    acct = mint_acct(extensions=[{"extension": "permanentDelegate"}])
    assert logic.mint_gate(acct) == "token2022_permanentDelegate"


def test_mint_gate_fails_closed_on_missing_or_garbage():
    assert logic.mint_gate(None) == "mint_not_found"
    assert logic.mint_gate({"data": "base64junk"}) == "mint_parse_error"


def test_mint_gate_passes_clean_mint():
    assert logic.mint_gate(mint_acct(extensions=[{"extension": "metadataPointer"}])) is None


def test_top10_excludes_program_owned_accounts():
    largest = [{"address": "pool_vault", "amount": "600"},
               {"address": "w1", "amount": "100"}, {"address": "w2", "amount": "50"}]
    pct = logic.top10_pct(largest, {"pool_vault": True}, "1000")
    assert pct == pytest.approx(15.0)


def test_top10_counts_unknown_owners_as_holders():
    largest = [{"address": "unknown", "amount": "600"}]
    assert logic.top10_pct(largest, {}, "1000") == pytest.approx(60.0)


def test_holder_gate_rejects_concentration():
    assert logic.holder_gate(31.0) == "top10_31pct"
    assert logic.holder_gate(29.0) is None


def test_rugcheck_gate_rejects_danger_and_fails_closed():
    assert logic.rugcheck_gate(None) == "rugcheck_unavailable"
    assert logic.rugcheck_gate({"risks": [{"name": "LP Unlocked", "level": "danger"}]}) \
        == "rugcheck_danger:LP Unlocked"
    assert logic.rugcheck_gate({"risks": [{"name": "Low holders", "level": "warn"}]}) is None


# ---- signal -------------------------------------------------------------------------

def test_breakout_fires_on_new_high_with_volume():
    assert logic.breakout(candles(last_close=1.2, last_vol=200)) is not None


def test_breakout_needs_volume():
    assert logic.breakout(candles(last_close=1.2, last_vol=120)) is None


def test_breakout_needs_new_high():
    assert logic.breakout(candles(last_close=0.99, last_vol=500)) is None


def test_breakout_ignores_short_history():
    assert logic.breakout(candles(n=10, last_close=5, last_vol=999)) is None


# ---- sizing ----------------------------------------------------------------------

def test_size_is_fraction_of_current_book_only():
    assert logic.position_size(1000) == pytest.approx(66.67, abs=0.01)  # 1 % risk / 15 % stop
    assert logic.position_size(500) == pytest.approx(33.33, abs=0.01)
    assert logic.position_size(0) == 0


# ---- breakers ---------------------------------------------------------------------

def state(**kw):
    s = dict(feed_ok=True, open_count=0, open_exposure=0.0, book=1000.0, day_pnl=0.0,
             loss_streak=0, hours_since_last_loss=None)
    s.update(kw)
    return s


def test_entry_allowed_in_normal_conditions():
    assert logic.entry_block(**state()) is None


def test_breaker_stale_feed():
    assert logic.entry_block(**state(feed_ok=False)) == "breaker_stale_feed"


def test_breaker_daily_loss():
    assert logic.entry_block(**state(book=970.0, day_pnl=-30.0)) == "breaker_daily_loss"


def test_breaker_loss_streak_and_its_expiry():
    assert logic.entry_block(**state(loss_streak=4, hours_since_last_loss=2)) \
        == "breaker_loss_streak"
    assert logic.entry_block(**state(loss_streak=4, hours_since_last_loss=30)) is None


def test_breaker_max_positions():
    assert logic.entry_block(**state(open_count=C.MAX_OPEN_POSITIONS)) == "max_positions"


def test_breaker_max_exposure():
    assert logic.entry_block(**state(open_exposure=380.0)) == "max_exposure"


# ---- exits & pnl --------------------------------------------------------------------

def test_exit_stop_target_time():
    entry = logic.entry_fill(1.0)
    assert logic.exit_reason(entry, 0.80, 1) == "stop"
    assert logic.exit_reason(entry, 1.40, 1) == "target"
    assert logic.exit_reason(entry, 1.00, C.MAX_HOLD_H) == "time"
    assert logic.exit_reason(entry, 1.00, 1) is None


def test_round_trip_at_same_price_loses_costs():
    entry = logic.entry_fill(1.0)
    assert logic.realised_pnl(100, entry, 1.0) < 0


def test_rug_loses_whole_position_and_no_more():
    assert logic.realised_pnl(100, 1.0, 0.0) == -100
