"""Prints a Markdown report of the journal: does the strategy have an edge yet?"""
from . import db
from . import config as C


def main():
    conn = db.connect()
    runs = conn.execute("SELECT COUNT(*), SUM(status='ok'), MIN(ts), MAX(ts) FROM runs").fetchone()
    book = db.get_book(conn)
    closed = [r["pnl_usd"] for r in conn.execute(
        "SELECT pnl_usd FROM positions WHERE closed_ts IS NOT NULL ORDER BY closed_ts")]
    open_n = conn.execute("SELECT COUNT(*) FROM positions WHERE closed_ts IS NULL").fetchone()[0]

    print("# Journal paper trading\n")
    print(f"- Runs : {runs[0]} ({runs[1] or 0} complets), du {runs[2]} au {runs[3]}")
    print(f"- Capital fictif : ${book:,.2f} (départ ${C.PAPER_START_BOOK:,.0f}, "
          f"{(book / C.PAPER_START_BOOK - 1) * 100:+.1f} %)")
    print(f"- Positions ouvertes : {open_n}, trades clos : {len(closed)}\n")

    if closed:
        wins = [x for x in closed if x > 0]
        losses = [x for x in closed if x <= 0]
        equity, peak, max_dd = C.PAPER_START_BOOK, C.PAPER_START_BOOK, 0.0
        for x in closed:
            equity += x
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak)
        print("## Résultats\n")
        print(f"- Taux de réussite : {len(wins) / len(closed) * 100:.0f} %")
        print(f"- Gain moyen : ${sum(wins) / len(wins) if wins else 0:,.2f} · "
              f"perte moyenne : ${sum(losses) / len(losses) if losses else 0:,.2f}")
        print(f"- **Espérance par trade : ${sum(closed) / len(closed):,.2f}**")
        print(f"- Drawdown max : {max_dd * 100:.1f} %")
        if len(closed) < 100:
            print(f"- Échantillon trop petit pour conclure ({len(closed)}/100 trades).")
        print()
        print("| Sortie | Trades | P&L |\n|---|---|---|")
        for r in conn.execute("SELECT exit_reason, COUNT(*), SUM(pnl_usd) FROM positions "
                              "WHERE closed_ts IS NOT NULL GROUP BY exit_reason ORDER BY 2 DESC"):
            print(f"| {r[0]} | {r[1]} | ${r[2]:,.2f} |")
        print()

    print("## Pourquoi les tokens sont rejetés (tous runs)\n")
    print("| Verdict | Nombre |\n|---|---|")
    for r in conn.execute("SELECT verdict, COUNT(*) FROM seen GROUP BY verdict "
                          "ORDER BY 2 DESC LIMIT 20"):
        print(f"| {r[0]} | {r[1]} |")

    blocked = conn.execute("SELECT action, COUNT(*) FROM signals GROUP BY action").fetchall()
    if blocked:
        print("\n## Signaux et décision du module de risque\n")
        print("| Décision | Nombre |\n|---|---|")
        for r in blocked:
            print(f"| {r[0]} | {r[1]} |")


if __name__ == "__main__":
    main()
