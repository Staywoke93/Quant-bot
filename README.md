# Quant Bot

A conservative, **signals-only** quantitative research project for FX, gold, and major crypto markets, using a three-hour review horizon.

> **Safety first:** This project is for research and education. It does not place trades or connect to a broker. Signals are not financial advice, returns are not guaranteed, and strategies must be backtested with realistic fees and slippage before any real-money use.

## Quick start

Requires Python 3.11 or newer.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` if configuring notifications. Never commit `.env`, API keys, passwords, broker credentials, or private notification topics.

## Try the starter signal

Prepare a CSV with a numeric `close` column, then run:

```bash
PYTHONPATH=src python bot.py path/to/prices.csv
```

The starter strategy reports moving-average crossover signals only; it does not execute trades.

## Project layout

- `bot.py` — command-line entry point
- `src/quant_bot/signals.py` — pure signal logic
- `tests/` — automated tests
- `.github/workflows/tests.yml` — CI test workflow
- `.env.example` — optional notification settings template, no secrets

## Roadmap

1. Confirm data sources, instruments, and the three-hour schedule.
2. Add OHLCV ingestion and data-quality checks.
3. Add backtesting with fees, spread, slippage, and out-of-sample evaluation.
4. Add risk limits and position-sizing analysis.
5. Configure and test ntfy delivery independently.
6. Review paper-trading results before considering any broker integration.

**Disclaimer:** Quantitative strategies can lose money. Historical performance does not guarantee future results. This repository is public, so assume all committed content can be read by anyone.
