"""Simple, transparent signal logic. This module never places trades."""

from __future__ import annotations

import pandas as pd


def generate_sma_signals(
    close: pd.Series,
    short_window: int = 10,
    long_window: int = 30,
) -> pd.DataFrame:
    """Return moving averages and crossover labels for a close-price series.

    Labels are BUY/SELL only on a fresh crossover; otherwise HOLD. These are
    research signals, not instructions to place orders.
    """
    if short_window < 1 or long_window < 2:
        raise ValueError("Windows must be positive; long_window must be at least 2.")
    if short_window >= long_window:
        raise ValueError("short_window must be smaller than long_window.")
    if not isinstance(close, pd.Series):
        raise TypeError("close must be a pandas Series.")

    prices = pd.to_numeric(close, errors="coerce")
    if prices.isna().any():
        raise ValueError("close prices must contain only valid numeric values.")
    if (prices <= 0).any():
        raise ValueError("close prices must be positive.")

    result = pd.DataFrame(index=prices.index)
    result["close"] = prices.astype(float)
    result["sma_short"] = prices.rolling(short_window, min_periods=short_window).mean()
    result["sma_long"] = prices.rolling(long_window, min_periods=long_window).mean()
    result["signal"] = "HOLD"

    ready = result["sma_short"].notna() & result["sma_long"].notna()
    previous_short = result["sma_short"].shift(1)
    previous_long = result["sma_long"].shift(1)
    cross_up = ready & (previous_short <= previous_long) & (result["sma_short"] > result["sma_long"])
    cross_down = ready & (previous_short >= previous_long) & (result["sma_short"] < result["sma_long"])
    result.loc[cross_up, "signal"] = "BUY"
    result.loc[cross_down, "signal"] = "SELL"
    return result
