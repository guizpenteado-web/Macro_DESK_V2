"""
Calculos de Medias Moveis Simples (SMA).
Modulo exclusivo de indicadores — expansivel com RSI, ATR, ADX, etc.
"""
import pandas as pd

def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average. Retorna NaN ate ter dados suficientes."""
    return series.rolling(window=period, min_periods=period).mean()

def calculate_all_smas(close: pd.Series) -> dict[str, pd.Series]:
    """Calcula SMA21, SMA50 e SMA200 para uma serie de fechamentos."""
    return {
        "sma21":  sma(close, 21),
        "sma50":  sma(close, 50),
        "sma200": sma(close, 200),
    }


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI de Wilder. Retorna NaN ate ter dados suficientes (period+1 candles)."""
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    # Wilder: EWM com alpha=1/period (com=period-1)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))