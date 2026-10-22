from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from bot import indicators, utc_iso, parse_utc, session_events, update_paper_trade

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

def test_virtual_paper_trade_opens_and_expires_without_broker_access():
    now=datetime(2026,1,5,8,0,tzinfo=timezone.utc)
    state={"paper_positions":{},"paper_trades":[]}
    result={"asset":"EUR/USD","price":1.1,"action":"STRONG BUY","stop_distance":0.01,
            "bar_time_utc":"2026-01-05T08:00:00Z","risk_budget_usd":50.0,
            "position_units_estimate":5000.0}
    update_paper_trade(state,result,now)
    assert state["paper_positions"]["EUR/USD"]["side"]=="LONG"
    later=dict(result,price=1.105,action="HOLD")
    update_paper_trade(state,later,now.replace(hour=12))
    assert "EUR/USD" not in state["paper_positions"]
    assert state["paper_trades"][0]["exit_reason"]=="three-hour time exit"
    assert state["paper_trades"][0]["pnl_pct"]>0
