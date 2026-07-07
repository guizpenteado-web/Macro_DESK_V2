"""Testes do modulo de indicadores."""
import pandas as pd
import pytest
from app.indicators.moving_averages import sma, calculate_all_smas


def test_sma_basic():
    s = pd.Series(range(1, 11), dtype=float)
    result = sma(s, 3)
    assert result.isna().sum() == 2
    assert abs(result.iloc[2] - 2.0) < 0.001

def test_sma_not_enough_data():
    s = pd.Series([1.0, 2.0])
    assert sma(s, 5).isna().all()

def test_calculate_all_smas_keys():
    s = pd.Series(range(1, 250), dtype=float)
    result = calculate_all_smas(s)
    assert set(result.keys()) == {"sma21", "sma50", "sma200"}

def test_sma200_needs_200_points():
    s = pd.Series(range(1, 201), dtype=float)
    result = calculate_all_smas(s)
    assert result["sma200"].notna().sum() == 1