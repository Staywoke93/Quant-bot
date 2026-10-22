from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import bot
from bot import indicators, utc_iso, parse_utc, session_events

def sample_ohlc(n=100):
    close=pd.Series([100+i*0.15 for i in range(n)],dtype=float)
    return pd.DataFrame({"Open":close-0.05,"High":close+0.4,"Low":close-0.4,"Close":close,"Volume":[1000.0]*n})

def test_timestamps_are_utc():
    stamp=datetime(2026,1,2,3,4,tzinfo=timezone.utc)
    assert utc_iso(stamp)=="2026-01-02T03:04:00Z"
    assert parse_utc("2026-01-02T03:04:00Z").utcoffset().total_seconds()==0

def test_indicator_columns_and_atr():
    result=indicators(sample_ohlc())
    for name in ("RSI","ATR","SMA20","SMA50","momentum_3h_pct"): assert name in result
    assert result["ATR"].dropna().iloc[-1]>0
    assert len(result["SMA50"].dropna())>0

def test_session_events_returns_structured_events():
    events=session_events(datetime(2026,1,5,8,7,tzinfo=timezone.utc))
    assert isinstance(events,list)
    assert all("key" in e and "title" in e for e in events)

def test_notify_posts_to_configured_ntfy_topic(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return Response()

    monkeypatch.setattr(bot, "NTFY_SERVER", "https://ntfy.example")
    monkeypatch.setattr(bot, "NTFY_TOPIC", "Quantz-pro")
    monkeypatch.setattr(bot.requests, "post", fake_post)

    assert bot.notify("Quant Bot — Market Signals", "STRONG BUY EUR/USD")
    assert captured["url"] == "https://ntfy.example/Quantz-pro"
    assert captured["kwargs"]["data"] == b"STRONG BUY EUR/USD"
    assert captured["kwargs"]["headers"]["Title"] == "Quant Bot ? Market Signals"
    assert captured["kwargs"]["headers"]["Content-Type"] == "text/plain; charset=utf-8"
    assert "Tags" not in captured["kwargs"]["headers"]
    assert not any(key.lower() in {"attach", "filename", "markdown"} for key in captured["kwargs"]["headers"])
