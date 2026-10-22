import pandas as pd
import pytest

from quant_bot.signals import generate_sma_signals


def test_returns_hold_until_long_window_is_ready():
    result = generate_sma_signals(pd.Series([100, 101, 102, 103]), 2, 3)
    assert result.iloc[0]["signal"] == "HOLD"
    assert pd.isna(result.iloc[0]["sma_long"])


def test_rejects_invalid_windows():
    with pytest.raises(ValueError):
        generate_sma_signals(pd.Series([1, 2, 3]), 3, 3)


def test_rejects_nonpositive_prices():
    with pytest.raises(ValueError):
        generate_sma_signals(pd.Series([1, 0, 2]), 1, 2)


def test_rejects_non_numeric_prices():
    with pytest.raises(ValueError):
        generate_sma_signals(pd.Series([1, "bad", 2]), 1, 2)
