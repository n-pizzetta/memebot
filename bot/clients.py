"""Thin network clients. Read-only: nothing here can sign or send a transaction."""
import time

import requests
from solders.pubkey import Pubkey

from . import config as C

_session = requests.Session()
_session.headers.update({"accept": "application/json", "user-agent": "memebot-paper/0.1"})
_last_gecko = 0.0


def _get(url, params=None, tries=3):
    for attempt in range(tries):
        r = _session.get(url, params=params, timeout=20)
        if r.status_code == 429:
            time.sleep(10 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"rate limited: {url}")


def _gecko(path, params=None):
    global _last_gecko
    wait = C.GECKO_MIN_INTERVAL_S - (time.monotonic() - _last_gecko)
    if wait > 0:
        time.sleep(wait)
    try:
        return _get(C.GECKO + path, params)
    finally:
        _last_gecko = time.monotonic()


def trending_pools(page):
    return _gecko("/networks/solana/trending_pools", {"page": page, "include": "base_token"})


def ohlcv_hourly(pool):
    data = _gecko(f"/networks/solana/pools/{pool}/ohlcv/hour",
                  {"aggregate": 1, "limit": C.BREAKOUT_LOOKBACK_H + 4, "currency": "usd"})
    return data.get("data", {}).get("attributes", {}).get("ohlcv_list", [])


def token_prices(mints):
    """{mint: price_usd} for up to 30 mints per call. Missing mints are absent."""
    prices = {}
    for i in range(0, len(mints), 30):
        chunk = mints[i:i + 30]
        data = _gecko("/networks/solana/tokens/multi/" + ",".join(chunk))
        for t in data.get("data", []):
            a = t.get("attributes", {})
            try:
                if a.get("price_usd"):
                    prices[a["address"]] = float(a["price_usd"])
            except (KeyError, ValueError, TypeError):
                pass
    return prices


def _rpc(method, params):
    r = _session.post(C.RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                      timeout=20)
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"rpc {method}: {body['error']}")
    return body["result"]


def mint_account(mint):
    return _rpc("getAccountInfo", [mint, {"encoding": "jsonParsed"}]).get("value")


def largest_accounts(mint):
    return _rpc("getTokenLargestAccounts", [mint]).get("value", [])


def program_owned(token_accounts):
    """{token_account: True if its owner is off-curve (a program/PDA: pool, locker...)}."""
    if not token_accounts:
        return {}
    res = _rpc("getMultipleAccounts", [token_accounts, {"encoding": "jsonParsed"}]).get("value", [])
    out = {}
    for addr, acc in zip(token_accounts, res):
        try:
            owner = acc["data"]["parsed"]["info"]["owner"]
            out[addr] = not Pubkey.from_string(owner).is_on_curve()
        except (KeyError, TypeError, ValueError):
            pass  # unknown owner => counted as a holder (conservative)
    return out


def rugcheck_summary(mint):
    try:
        return _get(f"{C.RUGCHECK}/tokens/{mint}/report/summary", tries=2)
    except Exception:
        return None
