"""Journal du signal breakout : la clôture de la bougie de cassure est enregistrée.

Ajouté par la revue du 2026-11-23 (collecte seule, aucune décision modifiée)."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from bot import db, paper
from bot.config import Risk
from bot.strategies import breakout

NOW = datetime(2026, 11, 23, 12, tzinfo=timezone.utc)


def _candles(n=24 + 2):
    rows = [[1000 - i, 1, 1.0, 0.9, 0.95, 100.0] for i in range(n)]
    rows[1] = [999, 1, 1.6, 0.9, 1.6, 1000.0]   # bougie close : cassure + volume
    return rows


def test_signal_journal_keeps_candle_close(tmp_path, monkeypatch):
    conn = db.connect(str(tmp_path / "j.db"))
    p = {"pool": "P", "mint": "M", "name": "X / SOL", "age_h": 48,
         "liq": 200_000, "vol24": 500_000, "price": 0.5}
    monkeypatch.setattr(breakout, "_collect", lambda now, log: ([p], True))
    monkeypatch.setattr(breakout, "_deep_check", lambda pool: None)
    monkeypatch.setattr(breakout.logic, "cheap_filter", lambda pool: None)
    monkeypatch.setattr(breakout.clients, "ohlcv_hourly", lambda pool, limit: _candles())

    def make_desk(feed_ok=True):
        return paper.Desk(conn, strategy="breakout", version=2,
                          risk=Risk(max_position_fraction=0.02), run_id=1, now=NOW,
                          feed_ok=feed_ok)

    stats = breakout.step(SimpleNamespace(conn=conn, now=NOW, run_id=1, desk=make_desk,
                                          log=lambda msg: None))
    assert stats["signals"] == 1
    price, prior_high, detail = conn.execute(
        "SELECT price, prior_high, detail FROM signals").fetchone()
    assert (price, prior_high) == (0.5, 1.0)
    assert json.loads(detail) == {"candle_close": 1.6}
    conn.close()
