"""Testes do modulo downloader."""
import pytest
from unittest.mock import patch, MagicMock
from app.downloader.ibov_components import _FALLBACK, fetch_ibov_components


def test_fallback_has_tickers():
    assert len(_FALLBACK) > 50

def test_fallback_tickers_format():
    for t in _FALLBACK:
        assert isinstance(t, str)
        assert len(t) >= 4
        assert not t.endswith(".SA")

def test_fetch_uses_fallback_on_api_error():
    with patch("app.downloader.ibov_components._fetch_from_b3", return_value=None):
        result = fetch_ibov_components()
    assert len(result) == len(_FALLBACK)
    assert all("ticker" in r for r in result)