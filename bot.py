"""Run a research signal scan against a CSV file containing a 'close' column."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

from quant_bot.signals import generate_sma_signals


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path, help="CSV file with a numeric 'close' column")
    parser.add_argument("--short-window", type=int, default=10)
    parser.add_argument("--long-window", type=int, default=30)
    args = parser.parse_args()

    if not args.csv_file.is_file():
        print(f"Input file not found: {args.csv_file}", file=sys.stderr)
        return 2

    try:
        data = pd.read_csv(args.csv_file)
        if "close" not in data.columns:
            raise ValueError("CSV must include a 'close' column.")
        signals = generate_sma_signals(
            data["close"], short_window=args.short_window, long_window=args.long_window
        )
    except (ValueError, OSError, pd.errors.ParserError) as exc:
        print(f"Could not generate signals: {exc}", file=sys.stderr)
        return 2

    print(signals.tail(10).to_string(index=False))
    print("\\nResearch output only: no trades have been placed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
