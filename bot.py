#!/usr/bin/env python3
"""UTC-first market analysis, ntfy alerts, three-hour forecast tracking and CSV backtesting."""
from __future__ import annotations
import argparse, json, logging, os, sys, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import requests
import yfinance as yf

UTC = timezone.utc
ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "data" / "state.json"
LOG = logging.getLogger("quant-bot")
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "Quantz-pro").strip()
REFERENCE_EQUITY = max(0.0, float(os.getenv("REFERENCE_EQUITY_USD", "10000")))
RISK_FRACTION = min(0.02, max(0.001, float(os.getenv("RISK_FRACTION", "0.005"))))
TIMEOUT = 18
UA = "Quant-bot/1.0 (research; GitHub Actions)"

ASSETS = [
    {"name":"EUR/USD","ticker":"EURUSD=X","kind":"fx","threshold":0.45},
    {"name":"GBP/USD","ticker":"GBPUSD=X","kind":"fx","threshold":0.55},
    {"name":"USD/JPY","ticker":"USDJPY=X","kind":"fx","threshold":0.45},
    {"name":"AUD/USD","ticker":"AUDUSD=X","kind":"fx","threshold":0.50},
    {"name":"USD/CAD","ticker":"USDCAD=X","kind":"fx","threshold":0.45},
    {"name":"USD/CHF","ticker":"USDCHF=X","kind":"fx","threshold":0.45},
    {"name":"NZD/USD","ticker":"NZDUSD=X","kind":"fx","threshold":0.50},
    {"name":"BTC/USD","ticker":"BTC-USD","kind":"crypto","threshold":2.0},
    {"name":"ETH/USD","ticker":"ETH-USD","kind":"crypto","threshold":2.2},
    {"name":"SOL/USD","ticker":"SOL-USD","kind":"crypto","threshold":3.0},
    {"name":"Gold (GC futures proxy)","ticker":"GC=F","kind":"gold","threshold":0.8},
]
SESSIONS = [("Sydney","Australia/Sydney",8),("Tokyo","Asia/Tokyo",9),("London","Europe/London",8),("New York","America/New_York",8)]
POS = {"gain","surge","rally","rise","higher","strong","growth","bullish","beat","optimism","inflow","record","support","easing"}
NEG = {"fall","drop","plunge","lower","weak","bearish","crash","selloff","sell-off","miss","outflow","inflation","crisis","hawkish","war"}

def now_utc() -> datetime:
    return datetime.now(UTC)

def utc_iso(value: datetime | None = None) -> str:
    return (value or now_utc()).astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00","Z")

def parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z","+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timestamp must include timezone information")
    return dt.astimezone(UTC)

def load_state() -> dict[str, Any]:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not STATE_PATH.exists():
        return {"version":1,"forecasts":[],"session_alerts":[],"volatility_alerts":{},"daily":{}}
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(state,dict): raise ValueError("state root is not an object")
        for key, default in (("forecasts",[]),("session_alerts",[]),("volatility_alerts",{}),("daily",{})):
            state.setdefault(key,default)
        return state
    except (OSError,json.JSONDecodeError,ValueError) as exc:
        raise RuntimeError(f"Refusing to overwrite unreadable state file: {type(exc).__name__}") from exc

def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    tmp.replace(STATE_PATH)

def notify(title: str, message: str, priority: int = 3, tags: str = "chart_with_upwards_trend") -> bool:
    if not NTFY_TOPIC:
        LOG.warning("NTFY_TOPIC is empty; skipped notification")
        return False
    try:
        response = requests.post(
            f"{NTFY_SERVER}/{NTFY_TOPIC}", data=message.encode("utf-8"),
            headers={"Title":title[:250],"Priority":str(max(1,min(5,priority))),"Tags":tags[:120],"Content-Type":"text/plain; charset=utf-8","User-Agent":UA},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        LOG.info("Notification delivered: %s",title)
        return True
    except requests.RequestException as exc:
        LOG.error("ntfy delivery failed (%s)",type(exc).__name__)
        return False

def fetch_news() -> list[dict[str,str]]:
    url="https://news.google.com/rss/search?q=forex+OR+gold+OR+bitcoin+OR+cryptocurrency+market&hl=en-US&gl=US&ceid=US:en"
    try:
        r=requests.get(url,headers={"User-Agent":UA},timeout=TIMEOUT); r.raise_for_status()
        root=ET.fromstring(r.content)
        return [{"title":(e.findtext("title") or "").strip(),"link":(e.findtext("link") or "").strip()} for e in root.findall(".//item")[:35] if (e.findtext("title") or "").strip()]
    except (requests.RequestException,ET.ParseError,ValueError) as exc:
        LOG.warning("News RSS unavailable (%s); neutral sentiment used",type(exc).__name__)
        return []

def sentiment(asset_name: str, headlines: list[dict[str,str]]) -> tuple[float,list[str]]:
    aliases={
      "EUR/USD":("euro","eur","europe","ecb"),"GBP/USD":("pound","sterling","gbp","boe","britain","uk"),
      "USD/JPY":("yen","jpy","boj","japan"),"AUD/USD":("australian dollar","aud","rba","australia"),
      "USD/CAD":("canadian dollar","cad","boc","canada","oil"),"USD/CHF":("swiss franc","chf","snb","switzerland"),
      "NZD/USD":("new zealand dollar","nzd","rbnz"),"BTC/USD":("bitcoin","btc","crypto"),
      "ETH/USD":("ethereum","eth","crypto"),"SOL/USD":("solana","sol","crypto"),
      "Gold (GC futures proxy)":("gold","bullion","precious metal","xau")}
    scores=[]; titles=[]
    for item in headlines:
        title=item["title"]; low=title.lower()
        if not any(a in low for a in aliases.get(asset_name,())): continue
        words=set("".join(c.lower() if c.isalnum() else " " for c in low).split())
        scores.append(float(bool(words & POS))-float(bool(words & NEG))); titles.append(title)
    return (float(np.clip(np.mean(scores),-1,1)),titles[:3]) if scores else (0.0,[])

def get_history(ticker: str) -> pd.DataFrame:
    df=yf.download(ticker,period="7d",interval="1h",auto_adjust=False,progress=False,threads=False,timeout=TIMEOUT)
    if df is None or df.empty: raise ValueError("no hourly bars returned")
    if isinstance(df.columns,pd.MultiIndex):
        fields={"Open","High","Low","Close","Volume"}
        df.columns=df.columns.get_level_values(0 if fields.intersection(set(df.columns.get_level_values(0))) else -1)
    df=df.loc[:,~df.columns.duplicated()].copy()
    if not {"High","Low","Close"}.issubset(df.columns): raise ValueError("OHLC columns missing")
    for col in ("High","Low","Close","Volume"):
        if col in df: df[col]=pd.to_numeric(df[col],errors="coerce")
    df=df.dropna(subset=["High","Low","Close"])
    if len(df)<55: raise ValueError(f"only {len(df)} hourly bars; need at least 55")
    return df

def indicators(frame: pd.DataFrame) -> pd.DataFrame:
    out=frame.copy(); close=out["Close"].astype(float); high=out["High"].astype(float); low=out["Low"].astype(float)
    delta=close.diff(); gain=delta.clip(lower=0).ewm(alpha=1/14,min_periods=14,adjust=False).mean()
    loss=(-delta.clip(upper=0)).ewm(alpha=1/14,min_periods=14,adjust=False).mean()
    rs=gain/loss.replace(0,np.nan); out["RSI"]=100-100/(1+rs)
    out.loc[loss.eq(0) & gain.gt(0),"RSI"]=100.0
    out.loc[loss.eq(0) & gain.eq(0),"RSI"]=50.0
    prev=close.shift(1)
    tr=pd.concat([(high-low),(high-prev).abs(),(low-prev).abs()],axis=1).max(axis=1)
    out["ATR"]=tr.rolling(14,min_periods=14).mean()
    out["SMA20"]=close.rolling(20,min_periods=20).mean()
    out["SMA50"]=close.rolling(50,min_periods=50).mean()
    out["momentum_3h_pct"]=close.pct_change(3)*100
    if "Volume" in out:
        out["volume_ratio"]=out["Volume"]/out["Volume"].rolling(20,min_periods=10).mean().replace(0,np.nan)
    else: out["volume_ratio"]=np.nan
    return out

def classify(row: pd.Series, news_score: float) -> tuple[str,int,list[str]]:
    score=0; why=[]; close=float(row["Close"]); s20=float(row["SMA20"]); s50=float(row["SMA50"]); rsi=float(row["RSI"]); mom=float(row["momentum_3h_pct"])
    if close>s20>s50: score+=1; why.append("price above moving-average structure")
    elif close<s20<s50: score-=1; why.append("price below moving-average structure")
    if 52<=rsi<=70: score+=1; why.append(f"positive RSI momentum ({rsi:.1f})")
    elif 30<=rsi<=48: score-=1; why.append(f"negative RSI momentum ({rsi:.1f})")
    if mom>=0.15: score+=1; why.append(f"3h momentum +{mom:.2f}%")
    elif mom<=-0.15: score-=1; why.append(f"3h momentum {mom:.2f}%")
    if news_score>=0.5: score+=1; why.append("headline heuristic positive")
    elif news_score<=-0.5: score-=1; why.append("headline heuristic negative")
    if pd.notna(row.get("volume_ratio")) and float(row["volume_ratio"])>=2: why.append(f"volume spike {float(row['volume_ratio']):.1f}x")
    action="STRONG BUY" if score>=3 else "STRONG SELL" if score<=-3 else "HOLD"
    return action,score,why or ["no strong directional agreement"]

def analyze(asset: dict[str,Any], headlines: list[dict[str,str]]) -> dict[str,Any]:
    df=indicators(get_history(asset["ticker"])).dropna(subset=["SMA50","ATR","momentum_3h_pct"])
    if df.empty: raise ValueError("not enough valid bars for indicators")
    row=df.iloc[-1]; ns, titles=sentiment(asset["name"],headlines); action,score,why=classify(row,ns)
    close=float(row["Close"]); atr=float(row["ATR"]); stop=max(1.5*atr,close*0.001)
    ts=pd.Timestamp(df.index[-1]); ts=ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    prev=float(df["Close"].iloc[-2]); move=(close/prev-1)*100 if prev else 0.0
    risk=REFERENCE_EQUITY*RISK_FRACTION
    return {"asset":asset["name"],"ticker":asset["ticker"],"price":close,"bar_time_utc":utc_iso(ts.to_pydatetime()),"action":action,"score":score,"rsi":float(row["RSI"]),"atr":atr,"momentum_3h_pct":float(row["momentum_3h_pct"]),"news_score":ns,"headlines":titles,"reasons":why,"hourly_move_pct":move,"threshold":asset["threshold"],"stop_distance":stop,"stop_loss_long":close-stop,"stop_loss_short":close+stop,"risk_budget_usd":risk,"position_units_estimate":risk/stop if stop>0 else 0}

def session_events(now: datetime) -> list[dict[str,str]]:
    now=now.astimezone(UTC); events=[]; locals_={}
    for name,zone,hour in SESSIONS:
        local=now.astimezone(ZoneInfo(zone)); locals_[name]=local
        if local.hour==hour and local.minute<=20:
            events.append({"key":f"open:{name}:{local.date()}","title":f"{name} market session opened","message":f"{name} session opening. Local: {local:%Y-%m-%d %H:%M %Z}. UTC evaluation: {utc_iso(now)}."})
    lon=locals_["London"]; ny=locals_["New York"]
    lon_start=datetime(lon.year,lon.month,lon.day,8,tzinfo=ZoneInfo("Europe/London"))
    ny_start=datetime(ny.year,ny.month,ny.day,8,tzinfo=ZoneInfo("America/New_York"))
    start=max(lon_start.astimezone(UTC),ny_start.astimezone(UTC))
    end=min((lon_start+timedelta(hours=9)).astimezone(UTC),(ny_start+timedelta(hours=9)).astimezone(UTC))
    if start<=now<start+timedelta(minutes=21) and now<end:
        events.append({"key":f"overlap:london-new-york:{utc_iso(start)}","title":"London/New York overlap starting","message":f"London and New York sessions are overlapping, often an active FX window but not a volatility guarantee. UTC: {utc_iso(now)}."})
    return events

def monitor_sessions(state: dict[str,Any], now: datetime) -> None:
    seen=set(state.get("session_alerts",[]))
    for event in session_events(now):
        if event["key"] not in seen and notify(event["title"],event["message"],4,"clock"):
            seen.add(event["key"])
    state["session_alerts"]=sorted(seen)[-100:]

def daily_bucket(state: dict[str,Any], day: str) -> dict[str,Any]:
    return state.setdefault("daily",{}).setdefault(day,{"signals":[],"alerts":[],"eod_sent":False})

def resolve_forecasts(state: dict[str,Any], latest: dict[str,dict[str,Any]], now: datetime) -> None:
    for f in state.get("forecasts",[]):
        if f.get("resolved") or parse_utc(f["expires_at"])>now: continue
        r=latest.get(f["asset"])
        if not r or parse_utc(r["bar_time_utc"]) < parse_utc(f["expires_at"]): continue
        valuation_time=parse_utc(r["bar_time_utc"])
        entry=float(f["entry_price"]); change=(float(r["price"])/entry-1)*100 if entry else 0
        action=f["action"]
        correct=(change>0 if action=="STRONG BUY" else change<0 if action=="STRONG SELL" else abs(change)<0.25)
        f.update({"resolved":True,"resolved_at":utc_iso(valuation_time),"exit_price":float(r["price"]),"realized_change_pct":change,"correct":bool(correct)})
        daily_bucket(state,f["created_at"][:10])["signals"].append({"type":"forecast_result","asset":f["asset"],"action":action,"correct":bool(correct),"realized_change_pct":change,"created_at":f["created_at"],"resolved_at":utc_iso(valuation_time)})
    state["forecasts"]=state.get("forecasts",[])[-500:]

def analyze_all(state: dict[str,Any], now: datetime) -> None:
    headlines=fetch_news(); results={}
    for asset in ASSETS:
        try:
            r=analyze(asset,headlines); results[r["asset"]]=r
            LOG.info("%s %s price=%.8g score=%+d",r["asset"],r["action"],r["price"],r["score"])
        except Exception as exc:
            LOG.warning("Could not analyse %s (%s)",asset["name"],type(exc).__name__)
    if not results:
        notify("Quant Bot data warning",f"No assets could be analysed. Inspect GitHub Actions logs. UTC: {utc_iso(now)}",4,"warning")
        return
    resolve_forecasts(state,results,now); urgent=[]
    day=now.date().isoformat()
    for name,r in results.items():
        if abs(r["hourly_move_pct"])>=r["threshold"]:
            key=f"{day}:{now.hour:02d}"
            if state.setdefault("volatility_alerts",{}).get(name)!=key:
                msg=f"Asset: {name}\nHourly move: {r['hourly_move_pct']:+.2f}%\nLast price: {r['price']:.8g}\nBar UTC: {r['bar_time_utc']}\nThreshold: ±{r['threshold']:.2f}%\nVerify data/spreads before acting; no order was placed."
                if notify(f"URGENT volatility: {name}",msg,5,"rotating_light,chart_with_upwards_trend"):
                    state["volatility_alerts"][name]=key; daily_bucket(state,day)["alerts"].append({"asset":name,"move_pct":r["hourly_move_pct"],"at":utc_iso(now)}); urgent.append(name)
        state.setdefault("forecasts",[]).append({"asset":name,"action":r["action"],"entry_price":r["price"],"created_at":utc_iso(now),"expires_at":utc_iso(now+timedelta(hours=3)),"resolved":False})
        daily_bucket(state,day)["signals"].append({"type":"signal","asset":name,"action":r["action"],"price":r["price"],"score":r["score"],"created_at":utc_iso(now)})
    lines=[f"UTC evaluation: {utc_iso(now)}","Source: Yahoo Finance hourly bars; forecast horizon: 3 hours",""]
    for r in results.values():
        lines.append(f"{r['asset']}: {r['action']} | price {r['price']:.8g} | score {r['score']:+d} | RSI {r['rsi']:.1f} | 3h momentum {r['momentum_3h_pct']:+.2f}%")
        lines.append(f"  ATR {r['atr']:.6g}; stop distance {r['stop_distance']:.6g}; risk budget USD {r['risk_budget_usd']:.2f}; theoretical units ~{r['position_units_estimate']:.5g}")
        lines.append(f"  Rationale: {'; '.join(r['reasons'])}")
        if r["headlines"]: lines.append(f"  Related headlines: {' | '.join(r['headlines'][:2])}")
    lines.extend(["","Risk sizing is illustrative and excludes contract specs, pip value, FX conversion, margin, spread and slippage.","Signals are heuristic research classifications, not advice. This bot does not connect to a broker or place orders."])
    notify("Quant Bot hourly market analysis","\n".join(lines),3,"chart_with_upwards_trend")

def eod_report(state: dict[str,Any], now: datetime) -> None:
    day=now.date().isoformat(); daily=daily_bucket(state,day)
    if daily.get("eod_sent"): LOG.info("EOD already sent for %s",day); return
    resolved=[f for f in state.get("forecasts",[]) if f.get("resolved") and f.get("created_at","").startswith(day)]
    directional=[f for f in resolved if f.get("action") in ("STRONG BUY","STRONG SELL")]
    correct=sum(bool(f.get("correct")) for f in directional)
    counts={a:sum(1 for f in daily["signals"] if f.get("type")=="signal" and f.get("action")==a) for a in ("STRONG BUY","STRONG SELL","HOLD")}
    pending=sum(1 for f in state.get("forecasts",[]) if not f.get("resolved") and f.get("created_at","").startswith(day))
    lines=[f"UTC date: {day}",f"Hourly asset signal records: {sum(counts.values())}",f"STRONG BUY: {counts['STRONG BUY']} | STRONG SELL: {counts['STRONG SELL']} | HOLD: {counts['HOLD']}",f"Resolved directional forecasts: {len(directional)}",f"Directional accuracy: {correct/len(directional)*100:.1f}%" if directional else "Directional accuracy: not enough resolved directional forecasts",f"Pending three-hour forecasts: {pending}",f"Volatility alerts: {len(daily['alerts'])}","","Forecast evaluation only; no broker connection or orders are used.",f"Generated at {utc_iso(now)}"]
    if notify(f"Quant Bot EOD review — {day}","\n".join(lines),3,"memo"): daily["eod_sent"]=True
    for old in sorted(state.get("daily",{}))[:-30]: del state["daily"][old]

def backtest_csv(path: Path, short: int, long: int, fee_bps: float) -> int:
    try:
        df=pd.read_csv(path)
        if "close" not in df: raise ValueError("CSV needs a 'close' column")
        close=pd.to_numeric(df["close"],errors="coerce")
        if close.isna().any() or (close<=0).any() or len(close)<=long+2: raise ValueError(f"Need more than {long+2} positive numeric close prices")
        fast=close.rolling(short).mean(); slow=close.rolling(long).mean()
        pos=pd.Series(np.where(fast>slow,1.0,np.where(fast<slow,-1.0,0.0)),index=close.index)
        returns=close.pct_change().fillna(0); turnover=pos.diff().abs().fillna(pos.abs())
        strat=pos.shift(1).fillna(0)*returns-turnover*(fee_bps/10000)
        equity=(1+strat).cumprod(); dd=equity/equity.cummax()-1
        active=strat[pos.shift(1).fillna(0)!=0]
        print(f"Rows: {len(close)} | SMA: {short}/{long} | fee assumption: {fee_bps:.1f} bps per position change")
        print(f"Strategy return: {(equity.iloc[-1]-1)*100:.2f}% | Max drawdown: {dd.min()*100:.2f}% | Active-bar win rate: {((active>0).mean()*100) if len(active) else 0:.1f}%")
        print("Illustrative close-only backtest; include spread, slippage, financing and out-of-sample validation.")
        return 0
    except (OSError,pd.errors.ParserError,ValueError) as exc:
        LOG.error("Backtest failed: %s",exc); return 2

def run(mode: str) -> int:
    now=now_utc(); LOG.info("Starting mode=%s at %s",mode,utc_iso(now))
    state=load_state()
    if mode in ("all","hourly","sessions","eod"): monitor_sessions(state,now)
    if mode in ("all","hourly"): analyze_all(state,now)
    if mode in ("all","eod"): eod_report(state,now)
    save_state(state); LOG.info("Finished at %s",utc_iso()); return 0

def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=("all","hourly","sessions","eod","backtest"),default="all")
    parser.add_argument("--csv",type=Path); parser.add_argument("--short-window",type=int,default=20); parser.add_argument("--long-window",type=int,default=50); parser.add_argument("--fee-bps",type=float,default=5.0)
    args=parser.parse_args(argv)
    logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"),format="%(asctime)sZ %(levelname)s %(message)s")
    if args.mode=="backtest":
        if not args.csv: parser.error("--mode backtest requires --csv path/to/file.csv")
        if args.short_window<1 or args.long_window<=args.short_window: parser.error("Require 1 <= short-window < long-window")
        return backtest_csv(args.csv,args.short_window,args.long_window,args.fee_bps)
    try: return run(args.mode)
    except Exception:
        LOG.exception("Fatal bot error"); return 1

if __name__=="__main__": sys.exit(main())
