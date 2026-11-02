"""Prints a Markdown report of the lab: does any strategy have an edge yet?

Usage : python -m bot.report [--days N]   (N = fenêtre des sections "récentes", 7 par défaut)
"""
import argparse
from datetime import datetime, timedelta, timezone

from . import config as C
from . import db
from .strategies import REGISTRY

MIN_TRADES = 100


def _pct(x):
    return f"{x * 100:+.1f} %"


def _sol_return(conn, since_iso):
    """Return of simply holding SOL since `since_iso`, from prices logged by the runs."""
    first = conn.execute("SELECT ts, sol_px FROM runs WHERE sol_px IS NOT NULL AND ts>=? "
                         "ORDER BY ts LIMIT 1", (since_iso,)).fetchone()
    last = conn.execute("SELECT ts, sol_px FROM runs WHERE sol_px IS NOT NULL "
                        "ORDER BY ts DESC LIMIT 1").fetchone()
    if not first or not last or first["ts"] == last["ts"]:
        return None, None
    return last["sol_px"] / first["sol_px"] - 1, first["ts"]


def strategy_section(conn, name, version, v, active):
    rows = conn.execute("SELECT * FROM positions WHERE strategy=? AND version=? "
                        "ORDER BY COALESCE(closed_ts, opened_ts)", (name, version)).fetchall()
    closed = [r for r in rows if r["closed_ts"]]
    open_n = len(rows) - len(closed)
    book = db.get_book(conn, name, version)
    status = "active" if active else "retirée (gère seulement ses positions ouvertes)"
    out = [f"## {name} v{version} — {status}\n",
           f"- Depuis {v.since} · {v.note} · fiche : `{v.hypothesis}`",
           f"- Capital fictif : ${book:,.2f} (départ ${C.PAPER_START_BOOK:,.0f}, "
           f"{_pct(book / C.PAPER_START_BOOK - 1)})",
           f"- Positions ouvertes : {open_n}, trades clos : {len(closed)}/{MIN_TRADES}"]
    if not closed:
        out.append("- Aucun trade clos pour l'instant.\n")
        return "\n".join(out)

    pnl = [r["pnl_usd"] for r in closed]
    ret = [r["pnl_usd"] / r["size_usd"] for r in closed if r["size_usd"]]
    wins = [x for x in pnl if x > 0]
    losses = [x for x in pnl if x <= 0]
    equity = peak = C.PAPER_START_BOOK
    max_dd = 0.0
    for x in pnl:
        equity += x
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak)
    out += [f"- Taux de réussite : {len(wins) / len(closed) * 100:.0f} %",
            f"- Gain moyen : ${sum(wins) / len(wins) if wins else 0:,.2f} · "
            f"perte moyenne : ${sum(losses) / len(losses) if losses else 0:,.2f}",
            f"- **Espérance par trade : ${sum(pnl) / len(pnl):,.2f}, soit "
            f"{_pct(sum(ret) / len(ret))} de la position**",
            f"- Pire trade : {_pct(min(ret))} de la position · drawdown max : {max_dd * 100:.1f} %"]
    sol, sol_since = _sol_return(conn, rows[0]["opened_ts"])
    if sol is not None:
        out.append(f"- Référence, garder du SOL depuis {sol_since[:10]} : {_pct(sol)} "
                   f"(stratégie : {_pct(book / C.PAPER_START_BOOK - 1)})")
    else:
        out.append("- Référence SOL : pas encore de prix enregistré sur la période.")
    if len(closed) < MIN_TRADES:
        out.append(f"- Échantillon trop petit pour conclure ({len(closed)}/{MIN_TRADES} trades).")
    out.append("\n| Sortie | Trades | P&L |\n|---|---|---|")
    for r in conn.execute("SELECT exit_reason, COUNT(*), SUM(pnl_usd) FROM positions "
                          "WHERE strategy=? AND version=? AND closed_ts IS NOT NULL "
                          "GROUP BY exit_reason ORDER BY 2 DESC", (name, version)):
        out.append(f"| {r[0]} | {r[1]} | ${r[2]:,.2f} |")
    return "\n".join(out) + "\n"


def main(argv=None):
    args = _args(argv)
    conn = db.connect()
    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat(timespec="seconds")

    runs = conn.execute("SELECT COUNT(*), SUM(status='ok'), MIN(ts), MAX(ts) FROM runs").fetchone()
    recent = conn.execute("SELECT COUNT(*), SUM(status='degraded') FROM runs WHERE ts>=?",
                          (since,)).fetchone()
    print("# Labo memebot — paper trading\n")
    print(f"- Runs : {runs[0]} ({runs[1] or 0} complets), du {runs[2]} au {runs[3]}")
    print(f"- {args.days} derniers jours : {recent[0]} runs, {recent[1] or 0} dégradés\n")

    for name, module in REGISTRY.items():
        for version in sorted(module.VERSIONS, reverse=True):
            print(strategy_section(conn, name, version, module.VERSIONS[version],
                                   version == module.ACTIVE))

    print(f"## Pourquoi les tokens sont rejetés ({args.days} derniers jours)\n")
    print("| Stratégie | Verdict | Nombre |\n|---|---|---|")
    for r in conn.execute("SELECT s.strategy || ' v' || s.version, s.verdict, COUNT(*) "
                          "FROM seen s JOIN runs r ON r.id=s.run_id WHERE r.ts>=? "
                          "GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 20", (since,)):
        print(f"| {r[0]} | {r[1]} | {r[2]} |")

    blocked = conn.execute("SELECT strategy || ' v' || version, action, COUNT(*) FROM signals "
                           "WHERE ts>=? GROUP BY 1, 2 ORDER BY 1, 3 DESC", (since,)).fetchall()
    if blocked:
        print(f"\n## Signaux et décision du module de risque ({args.days} derniers jours)\n")
        print("| Stratégie | Décision | Nombre |\n|---|---|---|")
        for r in blocked:
            print(f"| {r[0]} | {r[1]} | {r[2]} |")


def _args(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=7)
    return ap.parse_args(argv)


if __name__ == "__main__":
    main()
