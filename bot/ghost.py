"""Signaux fantômes de breakout v2 (fiche lab/hypotheses/005-signaux-fantomes-breakout.md).

Mesure seule : rejoue chaque signal distinct (mint + signal_ts) de breakout v2, pris ou bloqué,
avec les prix déjà collectés dans `seen` et les règles de sortie de v2. Lecture seule du journal :
rien n'est écrit dans `positions`, aucun effet sur le capital fictif ni sur les disjoncteurs.

Conventions (fiche 005) :
- entrée au prix de la première occurrence du signal + slippage de v2 ;
- sortie par stop / objectif / durée max, vérifiés à chaque run (`logic.exit_reason`) ;
- token absent de `seen` pendant MISSES_BEFORE_ASSUMED_RUG runs de suite : compté à -100 %.
  Seuls les runs `ok` comptent comme ratés (un run dégradé est une panne de collecte, comme une
  panne de prix pour une vraie position, qui ne compte pas de raté).
- Le rapport donne aussi, à titre d'information, l'espérance si ces tokens disparus étaient
  sortis à leur dernier prix vu : un token peut quitter l'univers (volume en baisse) sans rug.
"""
from datetime import datetime

from . import config as C
from . import logic

STRATEGY = "breakout"
VERSION = 2


def _risk():
    from .strategies import REGISTRY
    return REGISTRY[STRATEGY].VERSIONS[VERSION].risk


def _hours(a_iso, b_iso):
    return (datetime.fromisoformat(b_iso) - datetime.fromisoformat(a_iso)).total_seconds() / 3600


def distinct_signals(conn, strategy=STRATEGY, version=VERSION):
    """Une ligne par (mint, signal_ts) : première occurrence, et si une occurrence a été prise."""
    rows = conn.execute(
        "SELECT * FROM signals WHERE strategy=? AND version=? AND signal_ts IS NOT NULL "
        "ORDER BY id", (strategy, version)).fetchall()
    out = {}
    for r in rows:
        key = (r["mint"], r["signal_ts"])
        if key not in out:
            out[key] = {"first": r, "taken": False, "first_action": r["action"]}
        if r["action"] == "paper_entry":
            out[key]["taken"] = True
    return list(out.values())


def replay(conn, sig, risk, strategy=STRATEGY, version=VERSION):
    """Résultat fantôme d'un signal : dict(reason, ret, last_seen_ret, exit_ts) ; reason None si
    le trade fantôme est encore ouvert. ret est en fraction de la position, après coûts."""
    first = sig["first"]
    entry = logic.entry_fill(first["price"], risk.slippage_pct)
    prices = dict(conn.execute(
        "SELECT run_id, MAX(price) FROM seen WHERE mint=? AND strategy=? AND version=? "
        "AND run_id>? AND price>0 GROUP BY run_id", (first["mint"], strategy, version,
                                                     first["run_id"])).fetchall())
    runs = conn.execute("SELECT id, ts, status FROM runs WHERE id>? ORDER BY id",
                        (first["run_id"],)).fetchall()

    def pnl(px):
        return logic.realised_pnl(1.0, entry, px, slippage_pct=risk.slippage_pct,
                                  fee_pct=risk.fee_pct)

    misses, last_px = 0, None
    for r in runs:
        px = prices.get(r["id"])
        if px is None:
            if r["status"] == "ok":
                misses += 1
            if misses >= C.MISSES_BEFORE_ASSUMED_RUG:
                return {"reason": "missing", "ret": pnl(0.0), "exit_ts": r["ts"],
                        "last_seen_ret": pnl(last_px) if last_px else pnl(0.0)}
            continue
        misses, last_px = 0, px
        reason = logic.exit_reason(entry, px, _hours(first["ts"], r["ts"]),
                                   stop_pct=risk.stop_pct, target_pct=risk.target_pct,
                                   max_hold_h=risk.max_hold_h, slippage_pct=risk.slippage_pct)
        if reason:
            return {"reason": reason, "ret": pnl(px), "last_seen_ret": pnl(px), "exit_ts": r["ts"]}
    return {"reason": None, "ret": None, "last_seen_ret": None, "exit_ts": None}


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _fmt(x):
    return "—" if x is None else f"{x * 100:+.1f} %"


def section(conn, strategy=STRATEGY, version=VERSION):
    risk = _risk()
    sigs = distinct_signals(conn, strategy, version)
    out = [f"## Signaux fantômes — {strategy} v{version} (mesure seule, fiche 005)\n"]
    if not sigs:
        return "\n".join(out + ["- Aucun signal pour l'instant."]) + "\n"
    results = [(s, replay(conn, s, risk, strategy, version)) for s in sigs]
    done = [(s, g) for s, g in results if g["reason"]]

    def stats(group):
        rets = [g["ret"] for _, g in group]
        tokens = {s["first"]["mint"] for s, _ in group}
        targets = sum(g["reason"] == "target" for _, g in group)
        missing = sum(g["reason"] == "missing" for _, g in group)
        return len(group), len(tokens), targets, missing, _mean(rets)

    out.append("| Signaux | Distincts | Tokens | Clos | Objectifs | Disparus (-100 %) | "
               "Espérance (% position) |\n|---|---|---|---|---|---|---|")
    for label, keep in (("pris", True), ("bloqués", False)):
        group = [(s, g) for s, g in done if s["taken"] is keep]
        n_all = sum(s["taken"] is keep for s in sigs)
        n, tok, tg, miss, exp = stats(group)
        out.append(f"| {label} | {n_all} | {tok} | {n} | {tg} | {miss} | {_fmt(exp)} |")
    n, tok, tg, miss, exp = stats(done)
    out.append(f"| total | {len(sigs)} | {len({s['first']['mint'] for s in sigs})} | {n} | {tg} "
               f"| {miss} | {_fmt(exp)} |")
    if miss:
        alt = _mean([g["last_seen_ret"] for _, g in done])
        out.append(f"\n- Si les {miss} tokens disparus étaient sortis à leur dernier prix vu "
                   f"(au lieu de -100 %) : espérance totale {_fmt(alt)}.")

    # Critère d'échec de la fiche 005 : fantôme vs réel sur les signaux pris.
    gaps = []
    for s, g in done:
        if not s["taken"]:
            continue
        real = conn.execute(
            "SELECT pnl_usd, size_usd FROM positions WHERE strategy=? AND version=? AND mint=? "
            "AND signal_ts=? AND closed_ts IS NOT NULL", (strategy, version, s["first"]["mint"],
                                                          s["first"]["signal_ts"])).fetchone()
        if real and real["size_usd"]:
            gaps.append(g["ret"] - real["pnl_usd"] / real["size_usd"])
    if gaps:
        out.append(f"- Fantôme moins réel sur les signaux pris : écart moyen {_mean(gaps) * 100:+.1f} points, "
                   f"écart absolu moyen {_mean([abs(x) for x in gaps]) * 100:.1f} points "
                   f"({len(gaps)} trades réels clos ; critère d'échec : > 10 points après 20).")
    out.append("- Les bougies successives d'un même token sont corrélées : compter en tokens. "
               "Aucun effet sur le capital fictif ni sur le verdict de la fiche 002.")
    return "\n".join(out) + "\n"
