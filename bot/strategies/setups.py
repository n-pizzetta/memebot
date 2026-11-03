"""Setups d'actions suivis à la main (paper trades du compte « Satellite fictif » de Nathan).

Ce n'est pas une stratégie qui cherche des signaux : chaque ligne de lab/setups.csv est un
trade décidé par un humain (setup publié par le compte X suivi). Le labo l'applique avec des
règles fixes de clôture hebdomadaire et le compare à l'ETF MSCI World sur la même période.

Règles d'une ligne de lab/setups.csv :
- entry_date, entry_px : l'entrée, telle qu'elle a été prise ;
- stop_close : si une CLÔTURE HEBDOMADAIRE passe sous ce niveau → sortie ;
- stop_exit : prix de sortie simulé ("open" = ouverture de la séance suivante, "close" =
  clôture de la semaine, ou un prix) ;
- target_close / target_exit : idem, au-dessus de l'objectif.
Une ligne déjà ouverte ne se modifie pas (LAB.md, règle 3) : pour changer un stop, on clôt et
on ouvre une nouvelle ligne datée.
"""
import csv
import json
from collections import namedtuple
from datetime import date, datetime, time, timedelta, timezone
from itertools import groupby
from zoneinfo import ZoneInfo

from .. import clients, paper
from ..config import Risk
from . import Version

NAME = "setups"
ACTIVE = 1
REFERENCE = "ETF"
MIN_TRADES = 20          # en dessous, on ne dit rien de l'avantage ; verdict prévu en mars 2027
SETUPS_PATH = "lab/setups.csv"
BENCHMARK = "CW8.PA"     # Amundi MSCI World (PEA), Euronext Paris — à remplacer par ton ETF
EVAL_EVERY_H = 1         # les règles sont hebdomadaires : une évaluation par heure suffit
PARIS = ZoneInfo("Europe/Paris")
WEEK_DONE_AT = time(18, 0)   # une semaine est close le vendredi à 18 h (Euronext ferme à 17 h 35)

VERSIONS = {
    1: Version(
        # Taille fixe de 2 % par setup. Pas de disjoncteurs : on mesure ce que donne le fait de
        # suivre les setups tels quels ; les entrées sont décidées par un humain, pas par le bot.
        risk=Risk(risk_per_trade=0.02, max_position_fraction=0.02, max_exposure_fraction=1.0,
                  max_open_positions=50, stop_pct=-100.0, target_pct=1e6, max_hold_h=1e6,
                  slippage_pct=0.0, fee_pct=0.2, daily_loss_cap=1.0, max_loss_streak=10**6,
                  loss_streak_pause_h=0),
        since="2026-11-03",
        hypothesis="lab/hypotheses/004-setups-compte-x.md",
        note="Règles de clôture hebdo par ligne de lab/setups.csv, frais 0,2 % par côté.",
    ),
}

Bar = namedtuple("Bar", "date open close")


# ---------- données (pur, testé) -------------------------------------------------------

def parse_yahoo(payload):
    """Yahoo chart JSON -> list of Bar sorted by date. Raises ValueError if unusable."""
    try:
        res = payload["chart"]["result"][0]
        offset = int(res["meta"].get("gmtoffset") or 0)
        q = res["indicators"]["quote"][0]
        bars = []
        for ts, o, c in zip(res["timestamp"], q["open"], q["close"]):
            d = datetime.fromtimestamp(int(ts) + offset, tz=timezone.utc).date()
            bars.append(Bar(d, float(o) if o is not None else None,
                            float(c) if c is not None else None))
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise ValueError(f"unusable yahoo payload: {e!r}") from e
    return sorted(bars, key=lambda b: b.date)


def weekly_closes(bars, now_paris):
    """[(last trading day of the week, its close)] for weeks that are over."""
    out = []
    for (y, w), grp in groupby(bars, key=lambda b: tuple(b.date.isocalendar())[:2]):
        days = [b for b in grp if b.close is not None]
        if not days:
            continue
        friday = date.fromisocalendar(y, w, 5)
        if now_paris < datetime.combine(friday, WEEK_DONE_AT, tzinfo=PARIS):
            continue
        out.append((days[-1].date, days[-1].close))
    return out


def _exit_price(how, week_date, week_close, bars):
    """-> (date, price) or None if the price isn't known yet (next open not traded yet)."""
    if how == "close":
        return week_date, week_close
    if how == "open":
        nxt = next((b for b in bars if b.date > week_date and b.open is not None), None)
        return (nxt.date, nxt.open) if nxt else None
    return week_date, float(how)


def evaluate(rules, bars, now_paris):
    """First weekly close after the entry that breaks the stop or the target.
    -> {"reason", "date", "price", "week_close"} or None."""
    entry = date.fromisoformat(rules["entry_date"])
    for week_date, close in weekly_closes(bars, now_paris):
        if week_date <= entry:
            continue
        for reason, hit, how in (("stop", close < rules["stop_close"], rules["stop_exit"]),
                                 ("target", close > rules["target_close"], rules["target_exit"])):
            if hit:
                px = _exit_price(how, week_date, close, bars)
                if px is None:
                    return None  # stop/objectif touché, on attend l'ouverture suivante
                return {"reason": reason, "date": px[0].isoformat(), "price": px[1],
                        "week_close": close}
    return None


def price_on(bars, d):
    """Close of the last session on or before d."""
    known = [b for b in bars if b.date <= d and b.close is not None]
    return known[-1].close if known else None


def bench_return(bench, start, end):
    a, b = price_on(bench, start), price_on(bench, end)
    return b / a - 1 if a and b else None


def _exit_how(value):
    v = value.strip().lower()
    if v in ("open", "close"):
        return v
    if float(v) <= 0:
        raise ValueError("prix de sortie <= 0")
    return float(v)


def load_setups(path=SETUPS_PATH):
    """-> (setups, errors). A bad line is reported, never guessed."""
    setups, errors = [], []
    with open(path, newline="", encoding="utf-8") as f:
        for n, row in enumerate(csv.DictReader(f), start=2):
            try:
                s = {
                    "symbol": row["symbol"].strip(), "name": row["name"].strip(),
                    "entry_date": date.fromisoformat(row["entry_date"].strip()).isoformat(),
                    "entry_px": float(row["entry_px"]), "stop_close": float(row["stop_close"]),
                    "stop_exit": _exit_how(row["stop_exit"]),
                    "target_close": float(row["target_close"]),
                    "target_exit": _exit_how(row.get("target_exit") or "close"),
                    "source": (row.get("source") or "").strip(),
                    "note": (row.get("note") or "").strip(),
                }
                if not s["symbol"] or s["entry_px"] <= 0:
                    raise ValueError("symbole vide ou prix d'entrée <= 0")
                if not s["stop_close"] < s["target_close"]:
                    raise ValueError("stop_close doit être sous target_close")
                setups.append(s)
            except (KeyError, TypeError, ValueError) as e:
                errors.append(f"{path} ligne {n} : {e}")
    return setups, errors


def signal_ts(s):
    return int(s["entry_date"].replace("-", ""))


# ---------- interface du labo -------------------------------------------------------------

def prices(mints):
    out = {}
    for m in mints:
        try:
            bars = parse_yahoo(clients.yahoo_daily(m, date.today() - timedelta(days=10)))
            last = price_on(bars, date.today())
            if last:
                out[m] = last
        except Exception:
            pass
    return out


def step(ctx, path=SETUPS_PATH):
    """Opens the setups of lab/setups.csv that aren't in the journal yet."""
    desk = ctx.desk()
    setups, errors = load_setups(path)
    for e in errors:
        ctx.log(e)
    known = {(r["mint"], r["signal_ts"]) for r in ctx.conn.execute(
        "SELECT mint, signal_ts FROM positions WHERE strategy=? AND version=?",
        (NAME, ACTIVE))}
    opened = 0
    for s in setups:
        if (s["symbol"], signal_ts(s)) in known:
            continue
        entry_dt = datetime.combine(date.fromisoformat(s["entry_date"]), time(17, 35),
                                    tzinfo=PARIS)
        action = desk.consider(mint=s["symbol"], pool=s["symbol"], name=s["name"],
                               price=s["entry_px"], signal_ts=signal_ts(s),
                               opened_ts=entry_dt.isoformat(timespec="seconds"),
                               position_detail={k: s[k] for k in (
                                   "entry_date", "stop_close", "stop_exit", "target_close",
                                   "target_exit", "source", "note")},
                               detail={"source": s["source"]})
        opened += action == "paper_entry"
    return {"feed_ok": not errors, "pools_seen": len(setups), "deep_checked": 0,
            "signals": opened}


def manage(conn, now, rows, log, fetch=None):
    """Weekly-close exits + benchmark, at most once per EVAL_EVERY_H. Network errors leave the
    positions untouched: an action that can't be priced is never counted as a rug."""
    fetch = fetch or clients.yahoo_daily
    last = conn.execute("SELECT v FROM kv WHERE k='setups:last_eval'").fetchone()
    if last and paper.hours_between(last[0], now) < EVAL_EVERY_H:
        return
    now_paris = now.astimezone(PARIS)
    details = {r["id"]: json.loads(r["detail"]) for r in rows}
    first = min(date.fromisoformat(d["entry_date"]) for d in details.values())
    try:
        bench = parse_yahoo(fetch(BENCHMARK, first))
    except Exception as e:
        bench = None
        log(f"benchmark {BENCHMARK} indisponible : {e!r}")
    for r in rows:
        d = details[r["id"]]
        entry = date.fromisoformat(d["entry_date"])
        try:
            bars = parse_yahoo(fetch(r["mint"], entry))
        except Exception as e:
            log(f"{r['mint']} : cours indisponibles ({e!r}), position inchangée")
            continue
        last_px = price_on(bars, now_paris.date())
        out = evaluate(d, bars, now_paris)
        end = date.fromisoformat(out["date"]) if out else now_paris.date()
        d["bench"] = BENCHMARK
        d["bench_ret"] = bench_return(bench, entry, end) if bench else d.get("bench_ret")
        if out:
            d.update(exit_date=out["date"], week_close=out["week_close"])
        conn.execute("UPDATE positions SET last_px=COALESCE(?, last_px), misses=0, detail=? "
                     "WHERE id=?", (last_px, json.dumps(d), r["id"]))
        if out:
            at = time(9, 0) if d.get("stop_exit" if out["reason"] == "stop" else "target_exit") \
                == "open" else time(17, 35)
            exit_dt = datetime.combine(date.fromisoformat(out["date"]), at, tzinfo=PARIS)
            paper.close(conn, r, exit_dt, out["price"], out["reason"])
    conn.execute("INSERT OR REPLACE INTO kv VALUES ('setups:last_eval', ?)", (paper.iso(now),))


def report_lines(conn, version):
    rows = conn.execute("SELECT * FROM positions WHERE strategy=? AND version=? "
                        "ORDER BY opened_ts", (NAME, version)).fetchall()
    if not rows:
        return []
    out = ["\n| Titre | Entrée | Statut | Rendement | ETF même période | Écart |",
           "|---|---|---|---|---|---|"]
    excess = []
    for r in rows:
        d = json.loads(r["detail"] or "{}")
        if r["closed_ts"]:
            ret = r["pnl_usd"] / r["size_usd"]
            status = f"{r['exit_reason']} le {d.get('exit_date', r['closed_ts'][:10])}"
        else:
            ret = r["last_px"] / r["entry_px"] - 1 if r["last_px"] else None
            status = "ouverte"
        b = d.get("bench_ret")
        gap = ret - b if ret is not None and b is not None else None
        if r["closed_ts"] and gap is not None:
            excess.append(gap)
        fmt = (lambda x: f"{x * 100:+.1f} %" if x is not None else "—")
        out.append(f"| {r['name']} ({r['mint']}) | {d.get('entry_date', '')} à {r['entry_px']:g} "
                   f"| {status} | {fmt(ret)} | {fmt(b)} | {fmt(gap)} |")
    out.append("")
    if excess:
        out.append(f"- **Écart moyen vs {BENCHMARK} sur les trades clos : "
                   f"{sum(excess) / len(excess) * 100:+.1f} points** ({len(excess)} trades)")
    out.append(f"- Référence : {BENCHMARK} sur la période de chaque trade. Rendements des positions "
               "ouvertes avant frais de sortie.")
    return out
