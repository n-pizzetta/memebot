"""One cycle of the lab. Schedule it (GitHub Actions / cron); it exits when done.

PAPER ONLY: this program holds no key and cannot place an order.

Un cycle : 1) prix de référence (SOL), 2) gestion des positions ouvertes de toutes les
stratégies et versions, 3) un pas de chaque stratégie active. Une stratégie qui plante
n'empêche pas les autres de tourner ; le run est alors marqué "degraded".
"""
from datetime import datetime, timezone
from types import SimpleNamespace

from . import clients, db, paper
from . import config as C
from .strategies import REGISTRY


def cycle(conn, now, registry, sol_price=None):
    cur = conn.execute("INSERT INTO runs (ts, status) VALUES (?, 'running')", (paper.iso(now),))
    run_id = cur.lastrowid
    notes = []
    log = notes.append

    sol_px = None
    if sol_price is not None:
        try:
            sol_px = sol_price()
        except Exception as e:
            log(f"sol price failed (non-critical): {e!r}")

    paper.manage_open_positions(conn, now, {name: m.prices for name, m in registry.items()}, log)

    totals = {"pools_seen": 0, "deep_checked": 0, "signals": 0}
    ok = True
    for name, module in registry.items():
        if module.ACTIVE is None:
            continue
        version = module.VERSIONS[module.ACTIVE]

        def make_desk(feed_ok=True, _name=name, _v=module.ACTIVE, _risk=version.risk):
            return paper.Desk(conn, strategy=_name, version=_v, risk=_risk, run_id=run_id,
                              now=now, feed_ok=feed_ok)

        ctx = SimpleNamespace(conn=conn, now=now, run_id=run_id, desk=make_desk,
                              log=lambda msg, _n=name: log(f"{_n}: {msg}"))
        try:
            stats = module.step(ctx) or {}
        except Exception as e:
            ok = False
            log(f"{name}: step crashed: {e!r}")
            continue
        ok = ok and stats.get("feed_ok", True)
        for k in totals:
            totals[k] += int(stats.get(k, 0))

    conn.execute("UPDATE runs SET finished_ts=?, status=?, note=?, pools_seen=?, deep_checked=?, "
                 "signals=?, sol_px=? WHERE id=?",
                 (paper.iso(datetime.now(timezone.utc)), "ok" if ok else "degraded",
                  " | ".join(notes)[:1000], totals["pools_seen"], totals["deep_checked"],
                  totals["signals"], sol_px, run_id))
    conn.commit()
    return run_id, ok, totals, notes


def main():
    now = datetime.now(timezone.utc)
    conn = db.connect()
    run_id, ok, totals, notes = cycle(conn, now, REGISTRY,
                                      sol_price=lambda: clients.token_prices([C.WSOL])[C.WSOL])
    books = ", ".join(f"{n}@{m.ACTIVE} ${db.get_book(conn, n, m.ACTIVE):,.2f}"
                      for n, m in REGISTRY.items() if m.ACTIVE is not None)
    print(f"run {run_id}: {totals['pools_seen']} pools, {totals['deep_checked']} deep-checked, "
          f"{totals['signals']} signals, {books}" + (f" | {' | '.join(notes)}" if notes else ""))


if __name__ == "__main__":
    main()
