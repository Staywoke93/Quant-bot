# Quant Bot — UTC Market Analysis & Notifications

**Repository:** [Staywoke93/Quant-bot](https://github.com/Staywoke93/Quant-bot)

GitHub Actions-based hourly market-analysis and notification system for major FX pairs, crypto and a gold-futures proxy. It analyses market-data feeds (which may be delayed or incomplete) and generates research signals, illustrative risk estimates, three-hour forecast evaluations, session alerts, volatility alerts, an EOD report and an illustrative CSV backtest. **Paper positions and simulated trade tracking have been removed. This repository still does not connect to a broker or place real orders.**

## Scope and limitations

- Python 3.10+ compatible; GitHub Actions uses Python 3.11.
- All persisted timestamps use UTC/GMT. Session clocks use DST-aware IANA timezones.
- Market data: Yahoo Finance via `yfinance`, hourly bars, best-effort and potentially delayed/incomplete. GitHub scheduled jobs can be delayed or skipped.
- Assets: EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, USD/CHF, NZD/USD, BTC/USD, ETH/USD, SOL/USD and `GC=F` as a **gold futures proxy**, not spot XAU/USD.
- News sentiment is a small word-list heuristic applied to public Google News RSS headlines, not a trained model.
- Signals combine moving-average structure, RSI, three-hour momentum and headline heuristic. STRONG BUY/SELL/HOLD are classifications, not reliable predictions or advice.
- ATR stops and risk budgets are illustrations. Estimated units omit contract multipliers, pip values, currency conversion, margin, spread and slippage.
- Three-hour directional forecasts are evaluated against later market data; this is signal evaluation, not simulated or broker-executed trading. It does not model spreads, fills, slippage or financing.
- CSV backtest is a close-only SMA example with one-bar lag and a simple fee assumption; it does not prove an edge.

## GitHub Actions schedule (UTC)

`.github/workflows/trading_bot.yml` runs hourly at minute 7 from 00:07 through 22:07 UTC, and at 23:00 UTC for a final analysis/session check plus EOD review. GitHub Actions schedules are best-effort, not tick-level or guaranteed instant delivery. Session-open notifications are checked hourly and are approximate.

Hosted runners are ephemeral, so the workflow persists `data/state.json` by committing updates to the default branch. Concurrency is enabled to reduce state races.

## Setup

1. Ensure repository Actions are enabled.
2. The GitHub Actions workflow sends notifications to the ntfy topic `Quantz-bot`. The workflow topic is explicitly set in `.github/workflows/trading_bot.yml`.
3. Optional repository variables: `REFERENCE_EQUITY_USD` (default 10000, used only for illustrative risk estimates) and `RISK_FRACTION` (default 0.005, clamped to 0.1%–2%).
4. Go to **Actions → Quant Bot market monitor → Run workflow** to test manually.
5. Inspect Actions logs and your ntfy app; the first run can take several minutes.

### ntfy topic safety

A topic on public `ntfy.sh` is not a private mailbox: anyone who knows the topic may be able to publish to or subscribe to it unless access controls are configured. The requested `Quantz-bot` topic is configured for the workflow, but this repository is public, so the topic name is visible. Consider a hard-to-guess topic or authenticated/private ntfy setup if privacy matters. Never commit auth tokens.

### Local install

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python bot.py --mode hourly
```

For a local backtest, use a CSV with a numeric `close` column and enough rows:

```bash
python bot.py --mode backtest --csv prices.csv --short-window 20 --long-window 50 --fee-bps 5
```

## Files

- `bot.py` — data collection, indicators, session monitor, ntfy delivery, risk estimates, three-hour forecast tracking, EOD summary and CSV backtest.
- `requirements.txt` — dependencies.
- `.github/workflows/trading_bot.yml` — UTC schedule and state persistence.
- `tests/test_trading_bot.py` — unit tests.
- `data/state.json` — persistent forecast/performance state.
- `.env.example` — local configuration template.

## Troubleshooting

- **No signals:** data provider may rate-limit or return too few hourly bars; check Actions logs.
- **No ntfy message:** check that your ntfy app is subscribed to `Quantz-bot`, service availability and the HTTP outcome in workflow logs. Avoid logging private topics or tokens.
- **Missed session alert:** checks run hourly and cron timing is not guaranteed.
- **State commit fails:** confirm Actions has contents write permission and repository rules allow workflow commits.

## Risk disclaimer

Financial markets are risky. Historical results do not guarantee future results. This is a research and notification tool, not investment advice, and does not place orders. Do not treat its signals or risk estimates as instructions to trade. Validate out of sample before making financial decisions.
