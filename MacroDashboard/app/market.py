"""
Coleta preços históricos via yfinance (mercados) e FRED (spot sem roll) para sazonalidade.
"""
import re, json, base64, struct, time, logging
import requests
import pandas as pd
import yfinance as yf
from app.database import upsert_prices, last_price_date
from app.settings import SEASONALITY_TICKERS, BTC_TICKER, SEASONALITY_YEARS, FRED_TICKERS

log = logging.getLogger(__name__)


def _all_tickers() -> list[str]:
    tickers = []
    for group in SEASONALITY_TICKERS.values():
        tickers.extend(group.values())
    tickers.append(BTC_TICKER)
    return list(set(tickers))


def collect_ticker(ticker: str):
    last = last_price_date(ticker)
    start = last if last else f"{pd.Timestamp.now().year - SEASONALITY_YEARS}-01-01"

    try:
        df = yf.download(ticker, start=start, progress=False, auto_adjust=True, threads=False)
        if df.empty:
            log.warning("yfinance: %s retornou vazio", ticker)
            return
        close_col = "Close"
        if isinstance(df.columns, pd.MultiIndex):
            close_col = ("Close", ticker)
        rows = [
            (str(idx.date()), float(row[close_col]))
            for idx, row in df.iterrows()
            if not pd.isna(row[close_col])
        ]
        if rows:
            upsert_prices(ticker, rows)
            log.info("yfinance %s: %d registros", ticker, len(rows))
    except Exception as e:
        log.error("yfinance %s error: %s", ticker, e)


BTC_HASHRATE_TICKER = "BTC-HASHRATE"


def collect_btc_hashrate():
    """Coleta hashrate diário da rede Bitcoin (blockchain.info, TH/s) — insumo do modelo
    de custo de produção (Capriole). Busca a série inteira (~250KB) toda vez: roda só
    semanalmente, então simplicidade > economia de banda, e se autocorrige contra gaps."""
    url = "https://api.blockchain.info/charts/hash-rate?timespan=all&format=json&sampled=false"
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        values = r.json().get("values", [])
        rows = [
            (pd.Timestamp(v["x"], unit="s").strftime("%Y-%m-%d"), float(v["y"]))
            for v in values if v.get("y") is not None
        ]
        if rows:
            upsert_prices(BTC_HASHRATE_TICKER, rows)
            log.info("blockchain.info hashrate: %d registros", len(rows))
    except Exception as e:
        log.error("blockchain.info hashrate error: %s", e)


BTC_LTH_PCTPROFIT_TICKER = "BTC-LTH-PCTPROFIT"
BTC_LTH_MEAN_TICKER      = "BTC-LTH-MEAN"
BTC_LTH_MEANP1_TICKER    = "BTC-LTH-MEAN-P1SD"
BTC_LTH_MEANM1_TICKER    = "BTC-LTH-MEAN-M1SD"

_CHECKONCHAIN_LTH_URL = (
    "https://charts-cdn.checkonchain.com/btconchain/unrealised/"
    "pctsupplyinprofit_lth/pctsupplyinprofit_lth_light.html"
)
_PLOTLY_DTYPE = {"f8": ("d", 8), "f4": ("f", 4), "i1": ("b", 1), "i2": ("h", 2), "i4": ("i", 4)}


def _decode_plotly_y(y):
    """Traces do Plotly vêm como array typed (base64+dtype) quando geradas por Python/numpy."""
    if isinstance(y, dict) and "bdata" in y:
        code, size = _PLOTLY_DTYPE[y["dtype"]]
        raw = base64.b64decode(y["bdata"])
        n = len(raw) // size
        return list(struct.unpack(f"<{n}{code}", raw))
    return y


def collect_btc_lth_supply_profit():
    """Coleta a série 'Long-Term Holder % Supply in Profit' publicada pela _checkonchain
    (charts-cdn.checkonchain.com), embutida como JSON do Plotly no HTML estático — não
    requer full node nem indexação própria de UTXO. Ver [[project_btc_lth_supply_profit]]."""
    try:
        r = requests.get(_CHECKONCHAIN_LTH_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        m = re.search(r'Plotly\.newPlot\(\s*"[^"]+",\s*(\[.*?\])\s*,\s*\{', r.text, re.DOTALL)
        if not m:
            log.error("checkonchain LTH: JSON do Plotly não encontrado na página")
            return
        traces = {t.get("name"): t for t in json.loads(m.group(1))}

        # Preço BTC não é gravado por este coletor: reutiliza-se o BTC-USD já coletado via
        # yfinance (BTC_TICKER), pra não haver duas fontes de preço divergentes no dashboard.
        wanted = {
            BTC_LTH_PCTPROFIT_TICKER: "Percent Supply in Profit",
            BTC_LTH_MEAN_TICKER:      "Mean",
            BTC_LTH_MEANP1_TICKER:    "Mean +1sd",
            BTC_LTH_MEANM1_TICKER:    "Mean -1sd",
        }
        for ticker, trace_name in wanted.items():
            t = traces.get(trace_name)
            if not t:
                log.warning("checkonchain LTH: trace %r ausente", trace_name)
                continue
            dates = [d[:10] for d in t.get("x", [])]
            values = _decode_plotly_y(t.get("y"))
            rows = [(d, round(float(v) * 100, 2)) for d, v in zip(dates, values) if v is not None]
            if rows:
                upsert_prices(ticker, rows)
                log.info("checkonchain LTH %s: %d registros", ticker, len(rows))
    except Exception as e:
        log.error("checkonchain LTH error: %s", e)


def collect_btc_early_history(end_date: str = "2014-09-16"):
    """Backfill único do BTC-USD pré-yfinance (que só cobre a partir de 2014-09-17), via
    CoinMetrics Community API (gratuita, sem chave, cobre desde 2010). Sem isso, o ciclo do
    halving de 2012 no gráfico de Ciclos ficava sem base (indexado errado ao preço de 2014,
    não ao preço real do halving ~$12) — ver [[project_btc_cycle_2012_backfill]].
    Não faz parte do collect_all(): é histórico fixo, não precisa refazer diariamente."""
    url = (
        "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
        f"?assets=btc&metrics=PriceUSD&start_time=2012-11-01&end_time={end_date}"
        "&frequency=1d&page_size=10000"
    )
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json().get("data", [])
        rows = [
            (row["time"][:10], float(row["PriceUSD"]))
            for row in data if row.get("PriceUSD") is not None
        ]
        if rows:
            upsert_prices(BTC_TICKER, rows)
            log.info("CoinMetrics BTC early history: %d registros (%s a %s)", len(rows), rows[0][0], rows[-1][0])
    except Exception as e:
        log.error("CoinMetrics BTC early history error: %s", e)


def collect_fred():
    """Coleta series do FRED via CSV e armazena como precos mensais."""
    start_year = pd.Timestamp.now().year - SEASONALITY_YEARS
    cutoff = f"{start_year}-01-01"
    for series_id, label in FRED_TICKERS.items():
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            rows = []
            for line in r.text.strip().split('\n')[1:]:
                parts = line.split(',')
                if len(parts) == 2 and parts[1].strip() not in ('.', ''):
                    date_str = parts[0].strip()
                    if date_str >= cutoff:
                        rows.append((date_str, float(parts[1].strip())))
            if rows:
                upsert_prices(series_id, rows)
                log.info("FRED %s (%s): %d registros", series_id, label, len(rows))
        except Exception as e:
            log.error("FRED %s error: %s", series_id, e)


def collect_all():
    fred_ids = set(FRED_TICKERS.keys())
    yf_tickers = [t for t in _all_tickers() if t not in fred_ids]
    log.info("Coletando %d tickers via yfinance...", len(yf_tickers))
    for ticker in yf_tickers:
        collect_ticker(ticker)
        time.sleep(0.3)
    collect_fred()
    collect_btc_hashrate()
    collect_btc_lth_supply_profit()
