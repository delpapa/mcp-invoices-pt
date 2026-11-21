import datetime as dt
import json

import pytest

from invoices_pt import fx


def test_weekend_fallback_is_cached(tmp_path, monkeypatch):
    saturday = dt.date(2026, 1, 10)
    calls = []

    def fetch(currency, year):
        calls.append((currency, year))
        return {"2026-01-09": 1.16}

    monkeypatch.setattr(fx, "_fetch", fetch)
    assert fx.rate("usd", saturday, tmp_path) == 1.16
    assert fx.rate("USD", saturday, tmp_path) == 1.16
    assert calls == [("USD", 2026)]


def test_publication_after_cached_fallback(tmp_path, monkeypatch):
    monday = dt.date(2026, 1, 12)
    initial = dt.datetime(2026, 1, 12, 9, tzinfo=dt.UTC)
    now = initial.timestamp()
    monkeypatch.setattr(fx.time, "time", lambda: now)
    cache = tmp_path / "ecb_USD_2026.json"
    cache.write_text('{"2026-01-09": 1.16}')  # old cache format
    snapshots = iter([{"2026-01-09": 1.16}, {"2026-01-09": 1.16, "2026-01-12": 1.20}])
    monkeypatch.setattr(fx, "_fetch", lambda currency, year: next(snapshots))

    assert fx.rate("USD", dt.date(2026, 1, 9), tmp_path) == 1.16
    assert fx.rate("USD", monday, tmp_path) == 1.16
    now += 60
    assert fx.rate("USD", monday, tmp_path) == 1.16
    now += 3600
    assert fx.rate("USD", monday, tmp_path) == 1.20


def test_failed_cache_write_preserves_previous_snapshot(tmp_path, monkeypatch):
    cache = tmp_path / "ecb_USD_2026.json"
    original = {"2026-01-09": 1.16}
    cache.write_text(json.dumps(original))
    monkeypatch.setattr(fx, "_fetch", lambda currency, year: {"2026-01-12": 1.20})

    def fail_after_partial_write(snapshot, stream):
        stream.write("{")
        raise OSError("disk full")

    monkeypatch.setattr(fx.json, "dump", fail_after_partial_write)
    with pytest.raises(OSError, match="disk full"):
        fx.rate("USD", dt.date(2026, 1, 12), tmp_path)
    assert json.loads(cache.read_text()) == original
    assert list(tmp_path.iterdir()) == [cache]


def test_past_holiday_stays_cached(tmp_path, monkeypatch):
    day = dt.date(2026, 1, 1)
    now = dt.datetime(2026, 1, 3, tzinfo=dt.UTC).timestamp()
    monkeypatch.setattr(fx.time, "time", lambda: now)
    snapshots = iter([{"2025-12-31": 1.22}])
    monkeypatch.setattr(fx, "_fetch", lambda currency, year: next(snapshots))

    assert fx.rate("USD", day, tmp_path) == 1.22
    now += 24 * 3600
    assert fx.rate("USD", day, tmp_path) == 1.22
