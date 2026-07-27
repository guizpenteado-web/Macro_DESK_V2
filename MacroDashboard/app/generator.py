"""
Gera dashboard/index.html com todos os dados embutidos (Plotly JS).
Estilo: Private Banking — dark navy, gold accents.
"""
import json, logging
from pathlib import Path
from app.settings import DASHBOARD_PATH, BANK_DATA_PATH, SEASONALITY_TICKERS, BTC_TICKER, BTC_HALVINGS, COT_CONTRACTS, COT_CONTRACTS_TFF, FRED_TICKERS
from app.database import get_macro, get_prices, get_cot
from app.seasonality import (
    calc_seasonality_returns, calc_seasonality_level,
    calc_btc_seasonality, calc_btc_cycle, get_cycle_stats,
)
from app.btc_cost_model import compute_prodcost_series
from app.market import BTC_HASHRATE_TICKER

log = logging.getLogger(__name__)

MONTHS_PT = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]

# Mapeamento contrato COT → ticker de preço correspondente
COT_PRICE_MAP = {
    "ouro":   "GC=F",        "prata":  "SI=F",
    "cobre":  "PCOPPUSDM",   "wti":    "CL=F",
    "gasnat": "MHHNGSP",     "dxy":    "DX-Y.NYB",
    "sp500":  "^GSPC",       "vix":    "^VIX",
    "btc":    "BTC-USD",     "milho":  "ZC=F",
    "trigo":  "PWHEAMTUSDM", "soja":   "ZS=F",
    "bcom":   "^BCOM",
}
_FRED_SET = set(FRED_TICKERS.keys())


def _load_bank_data() -> dict:
    try:
        return json.loads(BANK_DATA_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.error("bank_projections.json error: %s", e)
        return {}


def _macro_series_to_json(series_id: str) -> str:
    rows = get_macro(series_id)
    if not rows:
        return "null"
    dates = [r[0] for r in rows]
    vals  = [r[1] for r in rows]
    return json.dumps({"dates": dates, "values": vals})


def _cpi_yoy_series() -> str:
    rows = get_macro("CPI")
    if not rows or len(rows) < 13:
        return "null"
    import pandas as pd
    idx  = pd.to_datetime([r[0] for r in rows])
    vals = [r[1] for r in rows]
    s = pd.Series(vals, index=idx).sort_index()
    yoy = s.pct_change(12) * 100
    yoy = yoy.dropna()
    return json.dumps({"dates": [str(d.date()) for d in yoy.index], "values": [round(float(v),2) for v in yoy.values]})


def _nfp_mom_series() -> str:
    rows = get_macro("NFP")
    if not rows or len(rows) < 2:
        return "null"
    import pandas as pd
    idx  = pd.to_datetime([r[0] for r in rows])
    vals = [r[1] for r in rows]
    s = pd.Series(vals, index=idx).sort_index()
    mom = s.diff() / 1000  # thousands
    mom = mom.dropna()
    return json.dumps({"dates": [str(d.date()) for d in mom.index], "values": [round(float(v),1) for v in mom.values]})


def _core_cpi_yoy_series() -> str:
    rows = get_macro("CORE_CPI")
    if not rows or len(rows) < 13:
        return "null"
    import pandas as pd
    idx  = pd.to_datetime([r[0] for r in rows])
    vals = [r[1] for r in rows]
    s = pd.Series(vals, index=idx).sort_index()
    yoy = s.pct_change(12) * 100
    yoy = yoy.dropna()
    return json.dumps({"dates": [str(d.date()) for d in yoy.index], "values": [round(float(v),2) for v in yoy.values]})


def _ipca_yoy_series() -> str:
    """IPCA YoY: compound 12 monthly pct changes (BCB série 433)."""
    rows = get_macro("IPCA")
    if not rows or len(rows) < 13:
        return "null"
    import pandas as pd
    idx  = pd.to_datetime([r[0] for r in rows])
    vals = [r[1] for r in rows]
    s = pd.Series(vals, index=idx).sort_index()
    factor = s / 100 + 1
    yoy = factor.rolling(12).apply(lambda x: (x.prod() - 1) * 100, raw=True).dropna()
    return json.dumps({"dates": [str(d.date()) for d in yoy.index], "values": [round(float(v),2) for v in yoy.values]})


def _seasonality_chart_data(ticker: str, is_vix: bool = False) -> str:
    if is_vix:
        d = calc_seasonality_level(ticker)
    else:
        # NG=F: filtro +-60% para excluir roll artifact de Set/2009 (+62.6%)
        outlier_pct = 60.0 if ticker == "NG=F" else 100.0
        d = calc_seasonality_returns(ticker, outlier_pct=outlier_pct)
    if not d:
        return "null"
    vals = [d.get(m, 0) for m in MONTHS_PT]
    colors = ["#10b981" if v >= 0 else "#f43f5e" for v in vals]
    return json.dumps({"months": MONTHS_PT, "values": vals, "colors": colors})


def _btc_cycle_data() -> str:
    cycles = calc_btc_cycle(BTC_HALVINGS)
    if not cycles:
        return "null"
    return json.dumps(cycles)


def _btc_stats_data() -> str:
    stats = get_cycle_stats(BTC_HALVINGS)
    return json.dumps(stats) if stats else "null"


def _btc_prodcost_data() -> str:
    """Bitcoin Production Cost (modelo Capriole) — ver app/btc_cost_model.py."""
    price_rows = get_prices(BTC_TICKER)
    hash_rows = get_prices(BTC_HASHRATE_TICKER)
    series = compute_prodcost_series(price_rows, hash_rows)
    return json.dumps(series) if series else "null"


COT_START = "2019-01-01"   # data de início igual ao Sharketo

def _cot_chart_data(contract_key: str) -> str:
    rows = get_cot(contract_key)
    if not rows or len(rows) < 4:
        return "null"
    rows   = [r for r in rows if r[0] >= COT_START]
    if len(rows) < 4:
        return "null"
    dates    = [r[0] for r in rows]
    mm_net   = [round(r[1]) for r in rows]
    am_net   = [round(r[2]) for r in rows]
    mm_long  = [round(r[4]) if r[4] is not None else None for r in rows]
    mm_short = [round(r[5]) if r[5] is not None else None for r in rows]
    am_long  = [round(r[6]) if r[6] is not None else None for r in rows]
    am_short = [round(r[7]) if r[7] is not None else None for r in rows]

    p_dates: list[str] = []
    p_vals:  list[float] = []
    ticker = COT_PRICE_MAP.get(contract_key)
    if ticker:
        pr = get_prices(ticker)   # FRED tickers tambem salvos em prices via upsert_prices
        if pr:
            pr = [(d, v) for d, v in pr if d >= "2018-01-01" and v is not None]
            if len(pr) > 400:          # diário → resample semanal
                import pandas as pd
                # W-TUE: semana fecha na terça, igual à data de referência do COT
                # (CFTC reporta posição de terça, publica sexta) — sem isso o preço
                # cai no domingo (default de "W") e desalinha do COT no tooltip.
                s = pd.Series(
                    [float(v) for _, v in pr],
                    index=pd.DatetimeIndex([d for d, _ in pr])
                ).sort_index().resample("W-TUE").last().dropna()
                p_dates = [str(d.date()) for d in s.index]
                p_vals  = [round(float(v), 4) for v in s.values]
            else:                      # mensal (FRED) — usar direto
                p_dates = [d for d, _ in pr]
                p_vals  = [round(float(v), 4) for _, v in pr]

    return json.dumps({"dates": dates, "mm_net": mm_net, "am_net": am_net,
                       "mm_long": mm_long, "mm_short": mm_short,
                       "am_long": am_long, "am_short": am_short,
                       "p_dates": p_dates, "p_vals": p_vals})


def generate():
    DASHBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)

    bank   = _load_bank_data()
    macro  = bank.get("macro_snapshot", {})

    # Try to get latest macro from DB, fall back to JSON snapshot
    def _latest_db(series_id):
        rows = get_macro(series_id)
        return rows[-1] if rows else None

    fed    = macro.get("fed_rate", {})
    cpi    = macro.get("cpi", {})
    ccpi   = macro.get("core_cpi", {})
    nfp    = macro.get("nfp", {})

    # Override from DB if available
    db_fed = _latest_db("FED_RATE")
    if db_fed:
        fed = {**fed, "value": f"{db_fed[1]:.2f}%", "low": db_fed[1], "high": db_fed[1], "decision_date": db_fed[0]}

    db_cpi = _latest_db("CPI")
    db_cpi_prev = get_macro("CPI")
    if db_cpi and len(db_cpi_prev) >= 13:
        import pandas as pd
        rows = db_cpi_prev
        idx  = pd.to_datetime([r[0] for r in rows])
        vals = [r[1] for r in rows]
        s = pd.Series(vals, index=idx).sort_index()
        yoy = float(s.pct_change(12).iloc[-1]) * 100
        mom = float(s.pct_change(1).iloc[-1]) * 100
        cpi = {**cpi, "yoy": round(yoy,1), "mom": round(mom,1), "period": str(s.index[-1].strftime("%b/%Y"))}

    # Build all chart data as JSON strings to embed in HTML
    cpi_hist      = _cpi_yoy_series()
    ccpi_hist     = _core_cpi_yoy_series()
    ipca_hist     = _ipca_yoy_series()
    nfp_hist      = _nfp_mom_series()
    fed_hist      = _macro_series_to_json("FED_RATE")

    saz = {}
    for group, tickers in SEASONALITY_TICKERS.items():
        saz[group] = {}
        for name, ticker in tickers.items():
            saz[group][name] = _seasonality_chart_data(ticker)

    btc_saz   = _seasonality_chart_data(BTC_TICKER)
    btc_cycle = _btc_cycle_data()
    btc_stats = _btc_stats_data()
    btc_prodcost = _btc_prodcost_data()

    cot_data = {key: _cot_chart_data(key) for key in {**COT_CONTRACTS, **COT_CONTRACTS_TFF}}

    sp500_targets = bank.get("sp500_targets", [])
    fed_views     = bank.get("fed_rate_views", [])
    brazil        = bank.get("brazil_macro", {})
    copom_views   = brazil.get("copom_views", [])
    eleicoes_html = _eleicoes_html(bank.get("pesquisas_eleitorais_2026", {}))

    current_spx  = _fetch_spx_price()
    current_ibov = _fetch_ibov_price()
    nfp_table    = _nfp_history_html()
    nfp_fp_json  = _nfp_firstprint_json()
    wage_json    = _wage_growth_json()
    ibov_targets = bank.get("ibov_targets_2026", [])
    ibov_rows         = _ibov_table_rows(ibov_targets, current_ibov)
    ibov_compact_cards = _ibov_compact_cards(ibov_targets, current_ibov)
    commodity_html    = _commodity_cards_html(bank.get("commodity_targets", {}))

    html = _render_html(
        fed=fed, cpi=cpi, ccpi=ccpi, nfp=nfp,
        cpi_hist=cpi_hist, ccpi_hist=ccpi_hist, ipca_hist=ipca_hist,
        nfp_hist=nfp_hist, fed_hist=fed_hist,
        sp500_targets=sp500_targets, fed_views=fed_views,
        brazil=brazil, copom_views=copom_views,
        saz=saz, btc_saz=btc_saz, btc_cycle=btc_cycle, btc_stats=btc_stats, btc_prodcost=btc_prodcost,
        last_updated=bank.get("last_updated","—"),
        current_spx=current_spx, nfp_table=nfp_table, nfp_fp_json=nfp_fp_json, wage_json=wage_json,
        cot_data=cot_data,
        ibov_rows=ibov_rows, ibov_compact_cards=ibov_compact_cards, current_ibov=current_ibov,
        commodity_html=commodity_html,
        eleicoes_html=eleicoes_html,
    )

    DASHBOARD_PATH.write_text(html, encoding="utf-8")
    log.info("Dashboard gerado: %s (%d KB)", DASHBOARD_PATH, len(html) // 1024)


# ─── HTML TEMPLATE ────────────────────────────────────────────────────────────

def _badge_view(view: str) -> str:
    m = {"BULL": ("#10b981","BULLISH"), "DOVE": ("#10b981","DOVISH"),
         "NEUTRAL": ("#f59e0b","NEUTRO"), "HAWK": ("#f43f5e","HAWKISH"),
         "N/D": ("#64748b","N/D")}
    for k, (color, label) in m.items():
        if view and view.upper().startswith(k):
            return f'<span class="badge" style="background:{color}22;color:{color};border:1px solid {color}44">{label}</span>'
    return ""


PRICE_CACHE_PATH = BANK_DATA_PATH.parent / "price_cache.json"


def _load_price_cache() -> dict:
    try:
        return json.loads(PRICE_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_price_cache(cache: dict) -> None:
    try:
        PRICE_CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning("price_cache.json nao pode ser salvo: %s", e)


def _fetch_price_cached(ticker: str, round_digits: int, hardcoded_fallback: float) -> float:
    """yfinance na VPS bate em YFRateLimitError com frequencia (achado
    15/jul/2026 — IP compartilhado do Hub, varios modulos chamando yfinance)
    e o fallback antigo (constante hardcoded, ex: Ibov=130000) ficava
    silenciosamente parado no HTML por dias sem ninguem notar — usuario
    reportou "upside nao corresponde com a realidade" no Ibovespa, current
    price real na hora ~176k vs os 130k travados. Fix: cache em disco por
    ticker com a ULTIMA cotacao que funcionou de verdade — se o fetch ao
    vivo falhar, cai pro cache (pode ter 1-2 dias, ainda MUITO mais preciso
    que uma constante escrita uma vez no codigo-fonte), so' caindo pra
    constante hardcoded se nao existir cache nenhum ainda."""
    cache = _load_price_cache()
    try:
        import yfinance as yf
        h = yf.Ticker(ticker).history(period="5d")
        closes = h["Close"].dropna()
        if not closes.empty:
            price = round(float(closes.iloc[-1]), round_digits)
            cache[ticker] = {"price": price, "date": str(closes.index[-1].date())}
            _save_price_cache(cache)
            return price
    except Exception as e:
        log.warning("fetch ao vivo de %s falhou (%s) — usando cache", ticker, e)
    cached = cache.get(ticker)
    if cached:
        return cached["price"]
    return hardcoded_fallback


def _fetch_spx_price() -> float:
    return _fetch_price_cached("^GSPC", 2, 7543.59)


def _fetch_ibov_price() -> float:
    return _fetch_price_cached("^BVSP", 0, 176641.0)


def _nfp_history_html() -> str:
    # First-print: valores da primeira divulgação do BLS, antes de revisões.
    # Fontes: BLS press releases, CNBC, FXStreet — pesquisado 02/jul/2026.
    FIRST_PRINT = {
        2020: {1:225,  2:273,   3:-701,   4:-20537, 5:2509, 6:4800, 7:1763, 8:1371, 9:661,  10:638,  11:245, 12:-140},
        2021: {1:49,   2:379,   3:916,    4:266,    5:559,  6:850,  7:943,  8:235,  9:194,  10:531,  11:210, 12:199},
        2022: {1:467,  2:678,   3:431,    4:428,    5:390,  6:372,  7:528,  8:315,  9:263,  10:261,  11:263, 12:223},
        2023: {1:517,  2:311,   3:236,    4:253,    5:339,  6:209,  7:187,  8:187,  9:336,  10:150,  11:199, 12:216},
        2024: {1:353,  2:275,   3:303,    4:175,    5:272,  6:206,  7:114,  8:142,  9:254,  10:12,   11:227, 12:256},
        2025: {1:143,  2:151,   3:228,    4:177,    5:139,  6:147,  7:73,   8:22,   9:119,  10:-105, 11:64,  12:50},
        2026: {1:130,  2:-92,   3:178,    4:115,    5:172,  6:57},
    }

    import datetime as _dt
    cur_year  = _dt.date.today().year
    cur_month = _dt.date.today().month

    YEARS  = list(range(2020, 2027))
    MONTHS = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]

    def _fmt(val):
        if abs(val) >= 1000:
            return ("+" if val >= 0 else "") + f"{val/1000:.1f}M"
        return ("+" if val >= 0 else "") + f"{val:+d}K"

    def _cell(val, is_future=False):
        if val is None:
            clr = "#30363d" if is_future else "#3d444d"
            return f"<td style='text-align:right;padding:7px 14px;color:{clr};font-size:13px'>—</td>"
        if val >= 500:
            color, label = "#10b981", "Excepc."
        elif val >= 200:
            color, label = "#34d399", "Forte"
        elif val >= 100:
            color, label = "#f59e0b", "Mod."
        elif val >= 0:
            color, label = "#94a3b8", "Fraco"
        else:
            color, label = "#f43f5e", "Neg."
        return (
            f"<td style='text-align:right;padding:7px 14px;white-space:nowrap'>"
            f"<span style='color:{color};font-weight:700;font-size:13px'>{_fmt(val)}</span>"
            f"&nbsp;<span style='color:#484f58;font-size:9px;vertical-align:middle'>{label}</span>"
            f"</td>"
        )

    body = ""
    for m in range(1, 13):
        cells = ""
        for y in YEARS:
            val    = FIRST_PRINT.get(y, {}).get(m)
            future = (y > cur_year) or (y == cur_year and m > cur_month)
            cells += _cell(val, is_future=future)
        even = " style='background:rgba(255,255,255,.025)'" if m % 2 == 0 else ""
        body += (
            f"<tr{even}>"
            f"<td style='padding:7px 14px;color:#8b949e;font-size:12px;font-weight:700;white-space:nowrap'>{MONTHS[m-1]}</td>"
            f"{cells}</tr>"
        )

    th_base = "padding:8px 14px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid var(--border);white-space:nowrap"
    hdr_cells = ""
    for y in YEARS:
        if y == cur_year:
            hdr_cells += f"<th style='text-align:right;{th_base};color:#58a6ff'>{y}</th>"
        elif y > cur_year:
            hdr_cells += f"<th style='text-align:right;{th_base};color:#30363d'>{y}</th>"
        else:
            hdr_cells += f"<th style='text-align:right;{th_base};color:#6e7681'>{y}</th>"

    hdr = (
        f"<thead><tr>"
        f"<th style='text-align:left;{th_base};color:#484f58'>Mês</th>"
        f"{hdr_cells}"
        f"</tr></thead>"
    )

    return (
        f"<div style='overflow-x:auto;margin-bottom:8px'>"
        f"<table style='border-collapse:collapse;width:auto'>"
        f"{hdr}<tbody>{body}</tbody>"
        f"</table></div>"
    )


def _nfp_firstprint_json() -> str:
    """Retorna JSON {dates, values} com first-print para o gráfico Plotly."""
    FIRST_PRINT = {
        2020: {1:225,  2:273,   3:-701,   4:-20537, 5:2509, 6:4800, 7:1763, 8:1371, 9:661,  10:638,  11:245, 12:-140},
        2021: {1:49,   2:379,   3:916,    4:266,    5:559,  6:850,  7:943,  8:235,  9:194,  10:531,  11:210, 12:199},
        2022: {1:467,  2:678,   3:431,    4:428,    5:390,  6:372,  7:528,  8:315,  9:263,  10:261,  11:263, 12:223},
        2023: {1:517,  2:311,   3:236,    4:253,    5:339,  6:209,  7:187,  8:187,  9:336,  10:150,  11:199, 12:216},
        2024: {1:353,  2:275,   3:303,    4:175,    5:272,  6:206,  7:114,  8:142,  9:254,  10:12,   11:227, 12:256},
        2025: {1:143,  2:151,   3:228,    4:177,    5:139,  6:147,  7:73,   8:22,   9:119,  10:-105, 11:64,  12:50},
        2026: {1:130,  2:-92,   3:178,    4:115,    5:172,  6:57},
    }
    dates, values = [], []
    for y in sorted(FIRST_PRINT):
        for m in sorted(FIRST_PRINT[y]):
            dates.append(f"{y}-{m:02d}-01")
            values.append(FIRST_PRINT[y][m])
    return json.dumps({"dates": dates, "values": values})


def _wage_growth_json() -> str:
    """Retorna JSON {dates, values} com Average Hourly Earnings YoY% (BLS,
    serie CES0500000003, nao-dessazonalizada) pra grafico Plotly.

    Diferente do NFP_FIRST_PRINT acima, isto NAO e' "first print" (valor da
    divulgacao original antes de revisao) — e' o dado mais recente/revisado
    disponivel via FRED. Decisao deliberada: revisao de wage growth costuma
    ser pequena (<=0.2pp), bem diferente da revisao de payrolls (que pode
    mudar centenas de milhares), entao nao vale o esforco de garimpar 78
    releases historicos do BLS so pra capturar uma diferenca marginal.
    Valores calculados a partir do nivel bruto ($/hora) do FRED
    (CES0500000003), YoY = nivel_mes / nivel_mesmo_mes_ano_anterior - 1;
    conferido contra os dois pontos extremos publicamente conhecidos (pico
    8.1% em abr/2020, minima 0.6% em abr/2021 — efeito de composicao da
    forca de trabalho na pandemia) — bateram exato. Pesquisado 13/jul/2026.
    """
    WAGE_YOY = {
        2020: {1:3.0, 2:3.1, 3:3.5, 4:8.1, 5:6.6, 6:5.0, 7:4.9, 8:4.8, 9:4.8, 10:4.6, 11:4.6, 12:5.4},
        2021: {1:5.3, 2:5.3, 3:4.5, 4:0.6, 5:2.3, 6:3.9, 7:4.3, 8:4.4, 9:5.0, 10:5.4, 11:5.4, 12:4.9},
        2022: {1:5.6, 2:5.3, 3:5.9, 4:5.8, 5:5.6, 6:5.4, 7:5.5, 8:5.4, 9:5.1, 10:5.0, 11:5.1, 12:4.9},
        2023: {1:4.5, 2:4.8, 3:4.6, 4:4.6, 5:4.4, 6:4.7, 7:4.7, 8:4.5, 9:4.4, 10:4.2, 11:4.1, 12:4.1},
        2024: {1:4.4, 2:4.1, 3:4.1, 4:4.0, 5:4.1, 6:3.9, 7:3.6, 8:3.9, 9:3.9, 10:4.0, 11:4.2, 12:4.1},
        2025: {1:4.0, 2:4.1, 3:4.2, 4:3.9, 5:4.0, 6:3.9, 7:4.0, 8:4.0, 9:3.8, 10:3.9, 11:3.9, 12:3.7},
        2026: {1:3.7, 2:3.7, 3:3.4, 4:3.6, 5:3.4, 6:3.5},
    }
    dates, values = [], []
    for y in sorted(WAGE_YOY):
        for m in sorted(WAGE_YOY[y]):
            dates.append(f"{y}-{m:02d}-01")
            values.append(WAGE_YOY[y][m])
    return json.dumps({"dates": dates, "values": values})


def _sp500_table_rows(targets: list, current_spx: float = 7354.0) -> str:
    rows_html = ""
    valid = [t for t in targets if t.get("target")]
    valid.sort(key=lambda x: x["target"], reverse=True)
    for t in targets:
        target = t.get("target")
        if target:
            pct = (target - current_spx) / current_spx * 100
            pct_str = f'+{pct:.1f}%' if pct >= 0 else f'{pct:.1f}%'
            pct_color = "#10b981" if pct >= 0 else "#f43f5e"
            target_str = f'{target:,.0f}'
        else:
            pct_str = "—"
            pct_color = "#64748b"
            target_str = "N/D"
        badge = _badge_view(t.get("view",""))
        analyst = t.get("analyst","")
        rows_html += f"""
        <tr>
          <td><b>{t['bank']}</b><br><small style="color:#64748b">{analyst}</small></td>
          <td class="num">{target_str}</td>
          <td class="num" style="color:{pct_color}">{pct_str}</td>
          <td>{badge}</td>
          <td style="font-size:11px;color:#64748b;max-width:260px">{t.get('rationale','')}</td>
        </tr>"""
    return rows_html


def _fed_table_rows(views: list) -> str:
    rows_html = ""
    for v in views:
        badge = _badge_view(v.get("view",""))
        ch = v.get("cuts_hikes_label","")
        color = "#10b981" if v.get("cuts_hikes",0) < 0 else ("#f43f5e" if v.get("cuts_hikes",0) > 0 else "#f59e0b")
        rows_html += f"""
        <tr>
          <td><b>{v['bank']}</b></td>
          <td class="num">{v.get('end_2026_label','—')}</td>
          <td class="num" style="color:{color}">{ch}</td>
          <td>{badge}</td>
          <td style="font-size:11px;color:#64748b;max-width:260px">{v.get('rationale','')}</td>
        </tr>"""
    return rows_html


def _ibov_compact_cards(targets: list, current_ibov: float = 130000.0) -> str:
    cards = ""
    view_color_map = {"BULL": "#10b981", "NEUTRAL": "#f59e0b", "BEAR": "#f43f5e", "N/D": "#64748b"}
    for t in targets:
        target = t.get("target")
        bank = t.get("bank", "—")
        view = t.get("view", "N/D")
        vc = view_color_map.get(view, "#64748b")
        if target:
            pct = (target - current_ibov) / current_ibov * 100
            pct_str = f'+{pct:.1f}%' if pct >= 0 else f'{pct:.1f}%'
            pct_color = "#10b981" if pct >= 0 else "#f43f5e"
            target_str = f'{target:,.0f}'
        else:
            pct_str = "—"
            pct_color = "#64748b"
            target_str = "N/D"
        cards += (
            f'<div style="background:var(--surface);border:1px solid var(--border);'
            f'border-left:2px solid {vc};border-radius:7px;padding:9px 10px">'
            f'<div style="font-size:10px;color:var(--muted);font-weight:700;letter-spacing:.4px;margin-bottom:3px">{bank}</div>'
            f'<div style="font-size:17px;font-weight:700;color:var(--text);line-height:1">{target_str}</div>'
            f'<div style="display:flex;align-items:center;justify-content:space-between;margin-top:4px">'
            f'<span style="font-size:11px;color:{pct_color};font-weight:600">{pct_str}</span>'
            f'<span style="font-size:9px;color:{vc};font-weight:700;letter-spacing:.4px">{view}</span>'
            f'</div></div>'
        )
    return cards


def _ibov_table_rows(targets: list, current_ibov: float = 130000.0) -> str:
    rows_html = ""
    for t in targets:
        target = t.get("target")
        if target:
            pct = (target - current_ibov) / current_ibov * 100
            pct_str = f'+{pct:.1f}%' if pct >= 0 else f'{pct:.1f}%'
            pct_color = "#10b981" if pct >= 0 else "#f43f5e"
            target_str = f'{target:,.0f}'
        else:
            pct_str = "—"
            pct_color = "#64748b"
            target_str = "N/D"
        badge = _badge_view(t.get("view", ""))
        rows_html += f"""
        <tr>
          <td><b>{t['bank']}</b></td>
          <td class="num">{target_str}</td>
          <td class="num" style="color:{pct_color}">{pct_str}</td>
          <td>{badge}</td>
          <td style="font-size:11px;color:#64748b;max-width:260px">{t.get('rationale','')}</td>
        </tr>"""
    return rows_html


def _commodity_cards_html(commodities: dict) -> str:
    """Renders compact 4-column commodity target cards (Ouro, Prata, Petróleo, Cobre)."""
    items = [
        ("ouro",         "OURO",      "/oz",  "#c9a227"),
        ("prata",        "PRATA",     "/oz",  "#94a3b8"),
        ("petroleo_wti", "PETRÓLEO",  "/bbl", "#f97316"),
        ("cobre",        "COBRE",     "/ton", "#b45309"),
    ]
    cols = ""
    for key, label_pt, unit_suffix, color in items:
        data = commodities.get(key, {})
        targets = data.get("bank_targets", [])
        unit_str = data.get("unit", f"USD{unit_suffix}")
        preco_atual = data.get("preco_atual")
        rows_html = ""
        for t in targets:
            bank_short = (t.get("bank", "—")
                          .replace("Goldman Sachs", "Goldman")
                          .replace("Morgan Stanley", "M.Stanley")
                          .replace("JP Morgan", "JPMorgan"))
            tgt = t.get("target")
            view = t.get("view", "")
            view_color = "#10b981" if view == "BULL" else "#f43f5e" if view == "BEAR" else "#f59e0b"
            if tgt is None:
                tgt_str = "N/D"
            elif tgt < 100 and tgt % 1 != 0:
                tgt_str = f'${tgt:.2f}'
            else:
                tgt_str = f'${int(tgt):,}'
            upside_html = ""
            if tgt and preco_atual:
                pct = (tgt - preco_atual) / preco_atual * 100
                sign = "+" if pct >= 0 else ""
                up_color = "#10b981" if pct >= 0 else "#f43f5e"
                upside_html = f'<span style="font-size:10px;color:{up_color};margin-left:3px">{sign}{pct:.0f}%</span>'
            rows_html += (
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:3px 0;border-bottom:1px solid rgba(255,255,255,.04)">'
                f'<span style="font-size:11.5px;color:var(--muted)">{bank_short}</span>'
                f'<span style="font-size:12.5px;font-weight:700;color:var(--text)">{tgt_str}'
                f'<span style="font-size:10.5px;color:{view_color};margin-left:3px">{view}</span>'
                f'{upside_html}</span>'
                f'</div>'
            )
        preco_atual_html = ""
        if preco_atual:
            preco_str = f'${preco_atual:,.0f}' if preco_atual >= 100 else f'${preco_atual:.2f}'
            preco_atual_html = (
                f'<div style="font-size:10.5px;color:var(--muted);margin-bottom:5px;'
                f'padding-bottom:4px;border-bottom:1px solid rgba(255,255,255,.08)">'
                f'Spot: <span style="color:var(--text);font-weight:600">{preco_str}</span>'
                f'</div>'
            )
        cols += (
            f'<div style="background:var(--surface);border:1px solid var(--border);'
            f'border-top:2px solid {color};border-radius:8px;padding:10px 11px;min-width:0">'
            f'<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:5px">'
            f'<span style="font-size:13px;font-weight:700;letter-spacing:.4px;color:{color}">{label_pt}</span>'
            f'<span style="font-size:10.5px;color:var(--muted)">{unit_str}</span>'
            f'</div>'
            f'{preco_atual_html}'
            f'{rows_html}'
            f'</div>'
        )
    return f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:6px">{cols}</div>'


def _eleicoes_html(data: dict) -> str:
    """Renders election poll block from pesquisas_eleitorais_2026 JSON section."""
    if not data or not data.get("institutos"):
        return ""
    institutos = data["institutos"]
    blocks = ""
    for inst in institutos:
        nome = inst.get("instituto", "—")
        data_col = inst.get("data_coleta", "—")
        amostra = inst.get("amostra", "—")
        margem = inst.get("margem_erro", "—")
        primeiro = inst.get("primeiro_turno", [])
        segundo = inst.get("segundo_turno", [])
        resumo = inst.get("resumo", "")

        primeiro_html = ""
        if primeiro:
            top = [c for c in primeiro if c.get("pct", 0) >= 2][:5]
            bar_colors = {"Lula": "#2563eb", "Flávio Bolsonaro": "#dc2626", "Flávio": "#dc2626",
                          "Ronaldo Caiado": "#7c3aed", "Romeu Zema": "#0891b2", "Renan Santos": "#64748b"}
            for c in top:
                name = c.get("candidato", "—")
                pct = c.get("pct", 0)
                party = c.get("partido", "")
                color = bar_colors.get(name, "#64748b")
                primeiro_html += (
                    f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">'
                    f'<span style="font-size:10px;color:var(--muted);width:115px;flex-shrink:0">{name} <span style="opacity:.6">({party})</span></span>'
                    f'<div style="flex:1;background:rgba(255,255,255,.07);border-radius:2px;height:6px">'
                    f'<div style="width:{pct}%;height:100%;background:{color};border-radius:2px"></div></div>'
                    f'<span style="font-size:11px;font-weight:700;color:{color};width:28px;text-align:right">{pct}%</span>'
                    f'</div>'
                )

        segundo_html = ""
        if segundo:
            s = segundo[0]
            lp = s.get("lula", 0)
            op = s.get("oponente", 0)
            oponente_name = s.get("cenario", "Oponente").split(" vs ")[-1] if " vs " in s.get("cenario", "") else "Oponente"
            segundo_html = (
                f'<div style="margin-top:8px;padding-top:8px;border-top:1px solid rgba(255,255,255,.06)">'
                f'<div style="font-size:9px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;color:var(--muted);margin-bottom:6px">2º TURNO — Lula vs {oponente_name}</div>'
                f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">'
                f'<div style="background:rgba(37,99,235,.1);border:1px solid rgba(37,99,235,.3);border-radius:6px;padding:7px 10px;text-align:center">'
                f'<div style="font-size:10px;color:#93c5fd;margin-bottom:2px">Lula</div>'
                f'<div style="font-size:22px;font-weight:800;color:#2563eb">{lp}%</div></div>'
                f'<div style="background:rgba(220,38,38,.1);border:1px solid rgba(220,38,38,.3);border-radius:6px;padding:7px 10px;text-align:center">'
                f'<div style="font-size:10px;color:#fca5a5;margin-bottom:2px">{oponente_name.split()[0]}</div>'
                f'<div style="font-size:22px;font-weight:800;color:#dc2626">{op}%</div></div>'
                f'</div></div>'
            )

        blocks += (
            f'<div style="background:var(--surface2);border:1px solid var(--border);border-radius:7px;padding:10px 12px;margin-bottom:10px">'
            f'<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px">'
            f'<span style="font-size:10px;font-weight:700;letter-spacing:.6px;color:var(--gold)">{nome.upper()}</span>'
            f'<span style="font-size:9px;color:var(--muted)">{data_col} &nbsp;·&nbsp; n={amostra:,} &nbsp;·&nbsp; MoE ±{margem}pp</span>'
            f'</div>'
            f'<div style="font-size:9px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;color:var(--muted);margin-bottom:5px">1º TURNO</div>'
            f'{primeiro_html}'
            f'{segundo_html}'
            f'{"<div style=font-size:10px;color:var(--muted);margin-top:6px;line-height:1.5>" + resumo + "</div>" if resumo else ""}'
            f'</div>'
        )
    nota = data.get("_nota", "")
    return f'<div>{blocks}<div class="source-note">{nota}</div></div>'


def _copom_table_rows(views: list) -> str:
    rows_html = ""
    for v in views:
        badge = _badge_view(v.get("view",""))
        mov = v.get("movimento","")
        selic = v.get("selic_fim_2026", 14.25)
        color = "#10b981" if selic < 14.25 else ("#f43f5e" if selic > 14.25 else "#f59e0b")
        rows_html += f"""
        <tr>
          <td><b>{v['bank']}</b></td>
          <td class="num">{v.get('selic_label','—')}</td>
          <td class="num" style="color:{color}">{mov}</td>
          <td>{badge}</td>
          <td style="font-size:11px;color:#64748b;max-width:220px">{v.get('rationale','')}</td>
        </tr>"""
    return rows_html


def _render_html(**kw) -> str:
    fed   = kw["fed"]
    cpi   = kw["cpi"]
    ccpi  = kw["ccpi"]
    nfp   = kw["nfp"]

    fed_color   = "#f59e0b"
    cpi_color   = "#f43f5e" if cpi.get("yoy", 0) > 3 else "#10b981"
    ccpi_color  = "#f43f5e" if ccpi.get("yoy",0) > 2.5 else "#10b981"
    nfp_color   = "#10b981" if nfp.get("value",0) > 0 else "#f43f5e"

    current_spx  = kw.get("current_spx", 7354.0)
    current_ibov = kw.get("current_ibov", 130000.0)
    nfp_table    = kw.get("nfp_table", "")
    sp500_rows   = _sp500_table_rows(kw["sp500_targets"], current_spx)
    fed_rows     = _fed_table_rows(kw["fed_views"])
    ibov_rows          = kw.get("ibov_rows", "")
    ibov_compact_cards = kw.get("ibov_compact_cards", "")
    commodity_html     = kw.get("commodity_html", "")
    eleicoes_html      = kw.get("eleicoes_html", "")

    brazil      = kw.get("brazil", {})
    ipca_br     = brazil.get("ipca", {})
    selic_br    = brazil.get("selic", {})
    copom_rows  = _copom_table_rows(kw.get("copom_views", []))
    ipca_color  = "#f43f5e" if ipca_br.get("yoy", 0) > ipca_br.get("teto", 4.5) else "#f59e0b"

    saz        = kw["saz"]
    cot        = kw.get("cot_data", {})
    last_upd   = kw["last_updated"]

    def _saz_js(group: str, name: str) -> str:
        return saz.get(group, {}).get(name, "null")

    def _cot_js(key: str) -> str:
        return cot.get(key, "null")

    def _cot_weekly_html(key: str, category_label: str, use_am: bool = False) -> str:
        return f"""
      <div class="cot-weekly-wrap">
        <div class="cot-weekly-toolbar">
          <span class="cot-weekly-title">Variação Semanal — {category_label}</span>
          <span class="period-toggle" data-cot-key="{key}" data-use-am="{"1" if use_am else "0"}">
            <button data-weeks="4">4W</button>
            <button data-weeks="8">8W</button>
            <button data-weeks="12" class="active">12W</button>
            <button data-weeks="26">26W</button>
            <button data-weeks="39">39W</button>
            <button data-weeks="52">52W</button>
          </span>
        </div>
        <div id="cot-{key}-weekly-tbl"></div>
      </div>"""

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Macro Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
*, *::before, *::after {{ box-sizing:border-box; margin:0; padding:0 }}
:root {{
  --bg:       #080c14;
  --surface:  #0f1623;
  --surface2: #151e2e;
  --gold:     #c9a227;
  --gold2:    rgba(201,162,39,.15);
  --text:     #e8eef5;
  --muted:    #7d90a8;
  --pos:      #10b981;
  --neg:      #f43f5e;
  --warn:     #f59e0b;
  --border:   rgba(255,255,255,.06);
  --nav-h:    54px;
}}
html,body {{ height:100%; background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; font-size:14px; overflow-x:hidden }}
nav {{
  position:fixed; top:0; left:0; right:0; height:var(--nav-h);
  background:#0b1120; border-bottom:1px solid var(--border);
  display:flex; align-items:center; padding:0 24px; gap:8px; z-index:100;
}}
.brand {{ font-size:11px; font-weight:700; letter-spacing:2px; text-transform:uppercase; color:var(--gold); margin-right:20px; white-space:nowrap }}
.tab-btn {{
  padding:8px 18px; border-radius:6px; border:none; background:transparent;
  color:var(--muted); font-size:13px; font-weight:500; cursor:pointer; transition:.15s;
  white-space:nowrap; letter-spacing:.3px;
}}
.tab-btn:hover {{ color:var(--text); background:rgba(255,255,255,.05) }}
.tab-btn.active {{ color:var(--gold); background:var(--gold2); border-bottom:2px solid var(--gold) }}
.upd {{ margin-left:auto; font-size:11px; color:var(--muted) }}
main {{ margin-top:var(--nav-h); padding:28px 28px }}
section {{ display:none }}
section.active {{ display:block }}

/* Cards */
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:16px; margin-bottom:28px }}
.card {{
  background:var(--surface); border:1px solid var(--border); border-radius:10px;
  padding:20px 22px; position:relative; overflow:hidden;
}}
.card::before {{ content:""; position:absolute; top:0; left:0; right:0; height:2px; background:var(--gold-line,var(--gold)) }}
.card-label {{ font-size:11px; font-weight:600; letter-spacing:1.5px; text-transform:uppercase; color:var(--muted); margin-bottom:8px }}
.card-value {{ font-size:28px; font-weight:700; color:var(--text); line-height:1.1; margin-bottom:6px }}
.card-sub {{ font-size:12px; color:var(--muted) }}
.card-badge {{ display:inline-block; padding:3px 10px; border-radius:4px; font-size:11px; font-weight:700; margin-top:8px; letter-spacing:.5px }}

/* Section titles */
.section-title {{ font-size:11px; font-weight:700; letter-spacing:2px; text-transform:uppercase; color:var(--gold); margin:28px 0 14px; border-bottom:1px solid var(--border); padding-bottom:8px }}

/* Tables */
.tbl-wrap {{ overflow-x:auto; margin-bottom:28px }}
table {{ width:100%; border-collapse:collapse; font-size:13px }}
thead tr {{ background:var(--surface2) }}
th {{ padding:10px 14px; text-align:left; font-size:10px; font-weight:700; letter-spacing:1.5px; text-transform:uppercase; color:var(--muted); border-bottom:1px solid var(--border) }}
td {{ padding:11px 14px; border-bottom:1px solid var(--border); vertical-align:middle }}
tr:last-child td {{ border-bottom:none }}
tr:hover td {{ background:rgba(255,255,255,.025) }}
td.num {{ text-align:right; font-variant-numeric:tabular-nums; font-weight:600 }}
.badge {{ padding:3px 9px; border-radius:4px; font-size:10px; font-weight:700; letter-spacing:.5px }}

/* COT weekly micro-table */
.cot-weekly-wrap {{ margin-top:10px; border-top:1px solid var(--border); padding-top:10px }}
.cot-weekly-toolbar {{ display:flex; align-items:center; gap:10px; margin-bottom:6px }}
.cot-weekly-title {{ flex:1; font-size:10px; font-weight:700; letter-spacing:1px; text-transform:uppercase; color:var(--muted) }}
.period-toggle {{ display:flex; gap:4px; flex-wrap:wrap; justify-content:flex-end }}
.period-toggle button {{ background:var(--surface2); border:1px solid var(--border); color:var(--muted); font-size:10px; font-weight:700; padding:3px 8px; border-radius:4px; cursor:pointer }}
.period-toggle button:hover {{ color:var(--text) }}
.period-toggle button.active {{ background:var(--gold,#c9a24b); border-color:var(--gold,#c9a24b); color:#000 }}
.cot-weekly-wrap table {{ font-size:11px }}
.cot-weekly-wrap th {{ padding:6px 8px; font-size:9px }}
.cot-weekly-wrap td {{ padding:6px 8px }}
.cot-weekly-wrap tr.cot-weekly-latest td {{ background:var(--surface2); font-weight:700; border-left:2px solid var(--gold,#c9a24b) }}
.delta-pos {{ color:#10b981 }}
.delta-neg {{ color:#f43f5e }}

/* Grid 2 cols */
.grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:20px }}
@media(max-width:900px) {{ .grid2 {{ grid-template-columns:1fr }} }}

/* Chart containers */
.chart-box {{ background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:16px }}
.chart-title {{ font-size:12px; font-weight:600; letter-spacing:1px; text-transform:uppercase; color:var(--muted); margin-bottom:4px }}

/* Alça sobre o eixo Y — arraste vertical reescala o preço (ver JS) */
.price-scale-handle {{
  position:absolute; cursor:ns-resize; background:rgba(56,189,248,.06);
  border-left:2px solid rgba(56,189,248,.45); border-right:2px solid rgba(56,189,248,.45);
}}
.price-scale-handle:hover {{ background:rgba(56,189,248,.14); }}

/* BTC stats */
.btc-stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:14px; margin-bottom:24px }}
.stat-box {{ background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:16px }}
.stat-lbl {{ font-size:10px; font-weight:600; letter-spacing:1.2px; text-transform:uppercase; color:var(--muted); margin-bottom:4px }}
.stat-val {{ font-size:20px; font-weight:700 }}

/* Source note */
.source-note {{ font-size:11px; color:var(--muted); margin-top:12px; padding:8px 12px; background:var(--surface2); border-radius:6px; border-left:3px solid var(--gold) }}
</style>
</head>
<body>

<nav>
  <div class="brand">&#9670; Macro Dashboard</div>
  <button class="tab-btn active" onclick="showTab('macro',this)">Macro</button>
  <button class="tab-btn" onclick="showTab('saz-mercados',this)">Sazonalidade — Mercados</button>
  <button class="tab-btn" onclick="showTab('saz-energia',this)">Sazonalidade — Energia e Metais</button>
  <button class="tab-btn" onclick="showTab('saz-agricola',this)">Sazonalidade — Agrícola</button>
  <button class="tab-btn" onclick="showTab('bitcoin',this)">Bitcoin — Ciclos</button>
  <div class="upd">Atualizado: {last_upd} &nbsp;|&nbsp; <a href="#" onclick="triggerUpdate();return false" style="color:var(--gold);text-decoration:none">↻ Atualizar</a></div>
</nav>

<main>

<!-- ═══════════════════════════════ MACRO ══════════════════════════════════ -->
<section id="tab-macro" class="active">

  <div class="cards">
    <div class="card" style="--gold-line:{fed_color}">
      <div class="card-label">Fed Funds Rate</div>
      <div class="card-value" style="color:{fed_color}">{fed.get('value','—')}</div>
      <div class="card-sub">Próxima reunião: {fed.get('next_meeting','—')}</div>
      <div class="card-badge" style="background:{fed_color}22;color:{fed_color}">{fed.get('decision','—')}</div>
      <div class="card-sub" style="margin-top:6px">Hold: {fed.get('fomc_probability_hold','—')}% &nbsp;|&nbsp; Corte: {fed.get('fomc_probability_cut','—')}%</div>
    </div>

    <div class="card" style="--gold-line:{cpi_color}">
      <div class="card-label">CPI — Inflação ({cpi.get('period','—')})</div>
      <div class="card-value" style="color:{cpi_color}">{cpi.get('yoy','—')}%<span style="font-size:14px;color:var(--muted)"> YoY</span></div>
      <div class="card-sub">MoM: {'+' if cpi.get('mom',0)>=0 else ''}{cpi.get('mom','—')}%</div>
      <div class="card-sub" style="margin-top:4px">Próx. divulgação: {cpi.get('next_release','—')}</div>
    </div>

    <div class="card" style="--gold-line:{ccpi_color}">
      <div class="card-label">Core CPI ({ccpi.get('period','—')})</div>
      <div class="card-value" style="color:{ccpi_color}">{ccpi.get('yoy','—')}%<span style="font-size:14px;color:var(--muted)"> YoY</span></div>
      <div class="card-sub">MoM: {'+' if ccpi.get('mom',0)>=0 else ''}{ccpi.get('mom','—')}%</div>
      <div class="card-sub" style="margin-top:4px">Exclui: alimentos e energia</div>
    </div>

    <div class="card" style="--gold-line:{nfp_color}">
      <div class="card-label">NFP — Non-Farm Payrolls ({nfp.get('period','—')})</div>
      <div class="card-value" style="color:{nfp_color}">{'+' if nfp.get('value',0)>=0 else ''}{nfp.get('value','—')}K</div>
      <div class="card-sub">Desemprego: {nfp.get('unemployment','—')}%</div>
      <div class="card-sub" style="margin-top:4px">Próx. divulgação: {nfp.get('next_release','—')}</div>
    </div>
  </div>

  <!-- CPI charts -->
  <div class="section-title">Histórico — Inflação (BLS)</div>
  <div class="grid2">
    <div class="chart-box">
      <div class="chart-title">CPI YoY %</div>
      <div style="font-size:11px;color:var(--muted);margin:4px 0 10px;line-height:1.5">
        <b style="color:var(--text)">Consumer Price Index</b> — mede a variação anual do custo de vida.
        Cesta: habitação 33% · transporte 15% · alimentação 14% · saúde 8% · energia 7% · outros 23%.
        <span style="color:#10b981">Meta Fed: 2%.</span>
      </div>
      <div id="ch-cpi" style="height:220px"></div>
    </div>
    <div class="chart-box">
      <div class="chart-title">Core CPI YoY %</div>
      <div style="font-size:11px;color:var(--muted);margin:4px 0 10px;line-height:1.5">
        <b style="color:var(--text)">Core CPI</b> — igual ao CPI mas <b style="color:#f59e0b">exclui alimentos e energia</b> (mais voláteis).
        Preferido pelo Fed para calibrar política monetária por refletir tendência estrutural da inflação.
        <span style="color:#10b981">Meta Fed: 2%.</span>
      </div>
      <div id="ch-ccpi" style="height:220px"></div>
    </div>
  </div>

  <!-- Payroll history -->
  <div class="section-title">Non-Farm Payrolls — Histórico First Print (2020–2026)</div>
  <div style="font-size:11px;color:var(--muted);margin-bottom:10px;line-height:1.6">
    Valores da <b style="color:var(--text)">primeira divulgação do BLS</b> (first print) — o número que moveu os mercados no dia do anúncio, antes de revisões posteriores.
    Fonte: BLS press releases, CNBC, FXStreet.
    Próxima divulgação: <b style="color:var(--text)">{nfp.get('next_release','—')}</b>.
  </div>
  <!-- Legenda de cores -->
  <div style="display:flex;flex-wrap:wrap;gap:6px 16px;margin-bottom:14px;font-size:11px;align-items:center">
    <span style="color:#7d8fa3;font-size:10px;text-transform:uppercase;letter-spacing:.05em;margin-right:4px">Legenda:</span>
    <span><span style="color:#10b981;font-weight:700">■</span> <span style="color:#94a3b8">&gt;500K</span> <b style="color:#10b981">Excepcional</b> — crescimento muito acima do normal</span>
    <span><span style="color:#34d399;font-weight:700">■</span> <span style="color:#94a3b8">&gt;200K</span> <b style="color:#34d399">Forte</b> — mercado de trabalho robusto</span>
    <span><span style="color:#f59e0b;font-weight:700">■</span> <span style="color:#94a3b8">&gt;100K</span> <b style="color:#f59e0b">Moderado</b> — crescimento dentro do esperado</span>
    <span><span style="color:#94a3b8;font-weight:700">■</span> <span style="color:#94a3b8">0–100K</span> <b style="color:#94a3b8">Fraco</b> — abaixo do ritmo necessário</span>
    <span><span style="color:#f43f5e;font-weight:700">■</span> <span style="color:#94a3b8">&lt;0K</span> <b style="color:#f43f5e">Negativo</b> — destruição de empregos</span>
  </div>
  <div class="grid2" style="align-items:start">
    <div style="overflow-x:auto">{nfp_table}</div>
    <div style="display:flex;flex-direction:column;gap:16px">
      <div class="chart-box" style="min-height:260px">
        <div class="chart-title">Evolução NFP — First Print (K/mês)</div>
        <div style="font-size:11px;color:var(--muted);margin:4px 0 10px;line-height:1.5">
          Cada barra = valor da primeira divulgação (BLS press release). Eixo cortado em ±900K — valores extremos de 2020 anotados na barra.
        </div>
        <div id="ch-nfp-fp" style="height:200px"></div>
      </div>
      <div class="chart-box" style="min-height:260px">
        <div class="chart-title">Evolução Wage Growth — Average Hourly Earnings YoY (%)</div>
        <div style="font-size:11px;color:var(--muted);margin:4px 0 10px;line-height:1.5">
          Variação anual do salário-hora médio (Average Hourly Earnings YoY, BLS/FRED — série CES0500000003). Dado mais recente disponível (revisões de wage growth são pequenas — tipicamente ≤0,2pp — então não usamos "first print").
        </div>
        <div id="ch-wage-growth" style="height:200px"></div>
      </div>
    </div>
  </div>

  <!-- Bank projections S&P 500 -->
  <div class="section-title">Wall Street — Projeções S&P 500 (2026)</div>
  <div class="tbl-wrap">
    <table>
      <thead><tr><th>Banco</th><th style="text-align:right">Target</th><th style="text-align:right">Upside*</th><th>Visão</th><th>Racional</th></tr></thead>
      <tbody>{sp500_rows}</tbody>
    </table>
  </div>
  <div class="source-note">* Upside/downside calculado com S&P 500 em <b>{current_spx:,.0f}</b> (preço de fechamento mais recente via yfinance). Fontes: Goldman Sachs, JP Morgan, BofA, Citi, Morgan Stanley Research — Jun/2026.</div>

  <!-- Bank projections Fed Rate -->
  <div class="section-title">Wall Street — Expectativas Para Fed Funds Rate (Fim 2026)</div>
  <div class="tbl-wrap">
    <table>
      <thead><tr><th>Banco</th><th style="text-align:right">Target Fim 2026</th><th style="text-align:right">Movimento</th><th>Viés</th><th>Racional</th></tr></thead>
      <tbody>{fed_rows}</tbody>
    </table>
  </div>
  <div class="source-note">Taxa atual: {fed.get('value','—')} (FOMC {fed.get('decision_date','—')}). Presidente do Fed: {fed.get('chair','—')}. Divergência significativa entre bancos — BofA vê 3 altas, Morgan Stanley vê 4 cortes. Atualizar conforme revisões.</div>

  <!-- ── Commodities ── -->
  <div class="section-title" style="margin-top:18px">Wall Street — Alvos Commodities (Fim 2026)</div>
  {commodity_html}
  <div class="source-note" style="margin-top:6px">Ouro/Prata: USD/oz | Petróleo: WTI USD/bbl | Cobre: COMEX USD/lb (targets dos bancos baseados em LME). Citi virou BULL cobre em 01/jun/26 ($15k/ton). MS cobre estimativa de dez/25 — revisão pendente. Fontes: GS Insights, JPMorgan Global Research, BofA, Morgan Stanley, Citi — Jun/Jul 2026.</div>

  <!-- ── Brasil — IPCA & COPOM ── -->
  <hr style="border:none;border-top:1px solid var(--border);margin:20px 0 14px">
  <div class="section-title">🇧🇷 Brasil — IPCA &amp; COPOM</div>
  <div class="cards-row" style="grid-template-columns:repeat(2,1fr)">
    <div class="card" style="--gold-line:{ipca_color}">
      <div class="card-label">IPCA — Inflação ({ipca_br.get('period','—')})</div>
      <div class="card-value" style="color:{ipca_color}">{ipca_br.get('yoy','—')}%<span style="font-size:14px;color:var(--muted)"> YoY</span></div>
      <div class="card-sub">MoM: +{ipca_br.get('mom','—')}% &nbsp;·&nbsp; Teto meta: {ipca_br.get('teto','—')}%</div>
      <div class="card-sub" style="margin-top:4px">Projeção 2026: <b style="color:#f59e0b">{ipca_br.get('projecao_fim_2026','—')}%</b> &nbsp;·&nbsp; Próx.: {ipca_br.get('next_release','—')}</div>
    </div>
    <div class="card" style="--gold-line:#f59e0b">
      <div class="card-label">Selic — COPOM</div>
      <div class="card-value" style="color:#f59e0b">{selic_br.get('value','—')}%<span style="font-size:14px;color:var(--muted)"> a.a.</span></div>
      <div class="card-sub">Decisão: {selic_br.get('decision_date','—')} ({selic_br.get('decision','HOLD')})</div>
      <div class="card-sub" style="margin-top:4px">Próxima reunião COPOM: <b style="color:var(--text)">{selic_br.get('next_meeting','—')}</b></div>
    </div>
  </div>
  <div class="grid2">
    <div class="chart-box">
      <div class="chart-title">IPCA YoY %</div>
      <div style="font-size:11px;color:var(--muted);margin:4px 0 10px;line-height:1.5">
        <b style="color:var(--text)">Índice Nacional de Preços ao Consumidor Amplo</b> — inflação oficial do Brasil (IBGE).
        <span style="color:#10b981">Meta 2026: 3.0%.</span> <span style="color:#f59e0b">Teto: 4.5%.</span>
        Projeção Focus fim-2026: <b style="color:#f43f5e">{ipca_br.get('projecao_fim_2026','—')}%</b> (acima do teto).
      </div>
      <div id="ch-ipca" style="height:220px"></div>

      <!-- ── NTN-B Tesouro IPCA+ em tempo real ── -->
      <div style="border-top:1px solid var(--border);margin:16px 0 10px"></div>
      <div style="font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);margin-bottom:8px">
        Tesouro IPCA+ — Prêmio de Risco &nbsp;<span style="font-weight:400;letter-spacing:0;color:#10b981">↻ tempo real</span>
      </div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">

        <div style="background:var(--surface);border:1px solid var(--border);border-radius:9px;padding:12px 11px;position:relative;overflow:hidden">
          <div style="position:absolute;top:0;left:0;right:0;height:2px;background:var(--gold)"></div>
          <div style="font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--muted);margin-bottom:3px">NTN-B 2035</div>
          <div id="ntnb-2035" style="font-size:24px;font-weight:700;color:var(--gold);line-height:1">—</div>
          <div style="font-size:10px;color:var(--muted);margin-top:1px">IPCA+ a.a.</div>
          <div id="ntnb-2035-d1" style="font-size:11px;font-weight:600;margin-top:5px;min-height:13px"></div>
          <div id="ntnb-2035-hist" style="font-size:10px;color:var(--muted);margin-top:4px;line-height:1.6;border-top:1px solid var(--border);padding-top:4px;min-height:38px"></div>
        </div>

        <div style="background:var(--surface);border:1px solid var(--border);border-radius:9px;padding:12px 11px;position:relative;overflow:hidden">
          <div style="position:absolute;top:0;left:0;right:0;height:2px;background:var(--gold)"></div>
          <div style="font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--muted);margin-bottom:3px">NTN-B 2050</div>
          <div id="ntnb-2050" style="font-size:24px;font-weight:700;color:var(--gold);line-height:1">—</div>
          <div style="font-size:10px;color:var(--muted);margin-top:1px">IPCA+ a.a.</div>
          <div id="ntnb-2050-d1" style="font-size:11px;font-weight:600;margin-top:5px;min-height:13px"></div>
          <div id="ntnb-2050-hist" style="font-size:10px;color:var(--muted);margin-top:4px;line-height:1.6;border-top:1px solid var(--border);padding-top:4px;min-height:38px"></div>
        </div>

        <div style="background:var(--surface);border:1px solid var(--border);border-radius:9px;padding:12px 11px;position:relative;overflow:hidden">
          <div style="position:absolute;top:0;left:0;right:0;height:2px;background:var(--gold)"></div>
          <div style="font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--muted);margin-bottom:3px">NTN-B 2060</div>
          <div id="ntnb-2060" style="font-size:24px;font-weight:700;color:var(--gold);line-height:1">—</div>
          <div style="font-size:10px;color:var(--muted);margin-top:1px">IPCA+ a.a.</div>
          <div id="ntnb-2060-d1" style="font-size:11px;font-weight:600;margin-top:5px;min-height:13px"></div>
          <div id="ntnb-2060-hist" style="font-size:10px;color:var(--muted);margin-top:4px;line-height:1.6;border-top:1px solid var(--border);padding-top:4px;min-height:38px"></div>
        </div>

      </div>
      <div style="font-size:10px;color:var(--muted);margin-top:6px;padding:4px 8px;background:var(--surface2);border-radius:4px;border-left:2px solid var(--gold)">
        Prêmio maior = risco-Brasil percebido. Curva inclinada (2060&gt;2035) sinaliza risco fiscal de longo prazo. Fonte: Investidor10.
      </div>

      <!-- ── Eleições 2026 ── -->
      <div style="border-top:1px solid var(--border);margin:14px 0 10px"></div>
      <div style="font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);margin-bottom:8px">
        Eleições 2026 &nbsp;<span id="pm-source-tag" style="font-weight:400;letter-spacing:0;color:#c9a227;font-size:10px"></span>
      </div>
      <div style="font-size:9px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--muted);margin-bottom:6px;opacity:.7">MERCADOS DE PREDIÇÃO</div>
      <div id="pm-box" style="min-height:80px">
        <div style="font-size:12px;color:var(--muted);display:flex;align-items:center;gap:8px;padding:8px 0"><span style="animation:spin .8s linear infinite;display:inline-block;width:10px;height:10px;border:2px solid var(--muted);border-top-color:var(--gold);border-radius:50%"></span>Carregando...</div>
      </div>
      <div style="border-top:1px solid var(--border);margin:10px 0 8px"></div>
      <div style="font-size:9px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--muted);margin-bottom:7px;opacity:.7">📊 PESQUISAS ELEITORAIS</div>
      {eleicoes_html}

    </div>
    <div class="chart-box">
      <div class="chart-title">Selic — Expectativas dos Bancos (Fim 2026)</div>
      <div class="tbl-wrap" style="margin-top:8px">
        <table>
          <thead><tr><th>Banco</th><th style="text-align:right">Selic Fim 2026</th><th style="text-align:right">Movimento</th><th>Viés</th><th>Racional</th></tr></thead>
          <tbody>{copom_rows}</tbody>
        </table>
      </div>
      <div class="source-note" style="margin-top:8px">Selic atual: {selic_br.get('value','—')}% a.a. (COPOM {selic_br.get('decision_date','—')}). IPCA 2026 Focus: {ipca_br.get('projecao_fim_2026','—')}% (acima do teto de {ipca_br.get('teto','—')}%). Fontes: Banco Central, Itaú BBA, XP, BTG Pactual, Santander — Jun/2026.</div>
    </div>
  </div>

  <!-- Alvos IBOV — tabela completa abaixo -->
  <div style="margin-top:22px">
    <div style="font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);margin-bottom:10px">
      Alvos Ibovespa Fim 2026 — Projeções dos Bancos
    </div>
    <div class="tbl-wrap" style="margin-bottom:6px">
      <table>
        <thead><tr>
          <th>Banco</th>
          <th style="text-align:right">Target</th>
          <th style="text-align:right">Upside*</th>
          <th>Visão</th>
          <th>Racional</th>
        </tr></thead>
        <tbody>{ibov_rows}</tbody>
      </table>
    </div>
    <div style="font-size:10px;color:var(--muted);padding:6px 10px;background:var(--surface2);border-radius:5px;border-left:2px solid var(--gold)">
      * Upside/downside vs Ibovespa em <b style="color:var(--text)">{current_ibov:,.0f} pts</b> (último fechamento). Fontes: Morgan Stanley, BofA, XP, JP Morgan, Itaú BBA, BTG, Goldman Sachs, Citi — Jun/2026.
    </div>
  </div>

</section>


<!-- ═══════════════════════════════ SAZ MERCADOS ═══════════════════════════ -->
<section id="tab-saz-mercados">
  <div class="section-title">Sazonalidade Histórica — Mercados (últimos 20 anos)</div>
  <div class="grid2">
    <div class="chart-box"><div class="chart-title">S&amp;P 500</div><div id="ch-saz-sp500" style="height:260px"></div></div>
    <div class="chart-box"><div class="chart-title">DXY — Dólar Index</div><div id="ch-saz-dxy" style="height:260px"></div></div>
    <div class="chart-box"><div class="chart-title">VIX</div><div id="ch-saz-vix" style="height:260px"></div></div>
    <div class="chart-box"><div class="chart-title">EWZ — iShares Brasil ETF (USD)</div><div id="ch-saz-ewz" style="height:260px"></div></div>
    <div class="chart-box"><div class="chart-title">IBOVESPA (^BVSP — pontos BRL)</div><div id="ch-saz-ibov" style="height:260px"></div></div>
  </div>
  <div class="source-note">Retorno médio mensal calculado sobre histórico disponível (até 20 anos). IBOVESPA = ^BVSP em pontos BRL. EWZ = ETF Brasil negociado em USD (captura também variação BRL/USD). Sazonalidade é estatística histórica — não garante comportamento futuro. Fonte: Yahoo Finance.</div>

  <div class="section-title">COT — Posicionamento Institucional — Financeiros (CFTC TFF, 2018–2026)</div>
  <div style="font-size:11px;color:var(--muted);margin-bottom:10px;line-height:1.6">
    Relatório <b style="color:var(--text)">Traders in Financial Futures (TFF)</b> do CFTC.
    <b style="color:#f59e0b">Leveraged Funds</b>: hedge funds e CTAs em futuros financeiros — equivalente direto ao Managed Money do Disaggregated.
    <b style="color:#818cf8">Large Speculators</b>: Leveraged Funds + Other Reportables. Z-Score calcula extremos históricos de posicionamento especulativo.
  </div>
  <div style="display:flex;flex-wrap:wrap;gap:14px;align-items:center;font-size:10px;color:var(--muted);margin-bottom:18px;padding:8px 14px;background:var(--surface2);border-radius:6px">
    <span style="font-weight:700;color:var(--text);letter-spacing:.5px;text-transform:uppercase">Guia Z-Score</span>
    <span><b style="color:#f43f5e">&#8805; +2&#963;</b>&nbsp;Sobrecomprado — contrarian de venda</span>
    <span><b style="color:#f59e0b">entre &#177;1&#963;</b>&nbsp;Neutro</span>
    <span><b style="color:#10b981">&#8804; &#8722;2&#963;</b>&nbsp;Sobrevendido — contrarian de compra</span>
    <span style="padding-left:12px;border-left:1px solid var(--border)">0 = média hist. &nbsp;&#183;&nbsp; &#177;1&#963; = normal &nbsp;&#183;&nbsp; &#177;2&#963; = extremo &nbsp;&#183;&nbsp; arrastar etiquetas &#963; (esq.) = zoom vertical &nbsp;&#183;&nbsp; arrastar no gr&#225;fico = pan &nbsp;&#183;&nbsp; scroll = zoom &nbsp;&#183;&nbsp; duplo clique = resetar</span>
  </div>
  <div class="grid2">
    <div class="chart-box">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <span class="chart-title" style="flex:1" id="cot-dxy-lbl">DXY — COT ICE &nbsp;|&nbsp; Asset Managers &amp; Lev. Funds</span>
        <span id="ch-cot-dxy-zlbl"></span>
      </div>
      <div id="ch-cot-dxy" style="height:430px"></div>{_cot_weekly_html('dxy', 'Asset Manager')}
    </div>
    <div class="chart-box">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <span class="chart-title" style="flex:1" id="cot-sp500-lbl">S&amp;P 500 E-Mini — COT CME &nbsp;|&nbsp; Asset Managers &amp; Lev. Funds</span>
        <span id="ch-cot-sp500-zlbl"></span>
      </div>
      <div id="ch-cot-sp500" style="height:430px"></div>{_cot_weekly_html('sp500', 'Asset Manager')}
    </div>
  </div>
  <div class="grid2">
    <div class="chart-box">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <span class="chart-title" style="flex:1" id="cot-vix-lbl">VIX Futures — COT CBOE &nbsp;|&nbsp; Asset Managers &amp; Lev. Funds</span>
        <span id="ch-cot-vix-zlbl"></span>
      </div>
      <div id="ch-cot-vix" style="height:430px"></div>{_cot_weekly_html('vix', 'Asset Manager')}
    </div>
    <div></div>
  </div>
  <div class="source-note">Fonte: CFTC Traders in Financial Futures (TFF). <b style="color:#f59e0b">Leveraged Funds</b>: hedge funds/CTAs em contratos financeiros (≈ Managed Money). <b style="color:#818cf8">Large Speculators</b>: Lev. Funds + Other Reportables. Interpretação: net longo em DXY = bull USD; net longo em S&amp;P = especuladores comprados no mercado; net longo em VIX = hedge contra queda.</div>

</section>


<!-- ═══════════════════════════════ SAZ ENERGIA E METAIS ══════════════════ -->
<section id="tab-saz-energia">

  <div class="section-title">Sazonalidade — Energia (últimos 20 anos)</div>
  <div class="grid2">
    <div class="chart-box"><div class="chart-title">Petróleo WTI (CL=F)</div><div id="ch-saz-wti" style="height:280px"></div></div>
    <div class="chart-box"><div class="chart-title">Cobre (IMF Global Price — FRED)</div><div id="ch-saz-cobre" style="height:280px"></div></div>
  </div>

  <div class="section-title">Sazonalidade — Metais (últimos 20 anos)</div>
  <div class="grid2">
    <div class="chart-box"><div class="chart-title">Ouro (GC=F — COMEX)</div><div id="ch-saz-ouro" style="height:280px"></div></div>
    <div class="chart-box"><div class="chart-title">Prata (SI=F — COMEX)</div><div id="ch-saz-prata" style="height:280px"></div></div>
  </div>
  <div class="grid2">
    <div class="chart-box"><div class="chart-title">Gás Natural (NG=F — NYMEX futuros)</div><div id="ch-saz-gas" style="height:280px"></div></div>
    <div></div>
  </div>
  <div class="source-note" style="margin-bottom:20px">
    Sazonalidade validada vs Seasonax e EquityClock. <b style="color:var(--text)">Ouro:</b> Jan forte (+3.5% médio) = demanda Chinese New Year + casamentos Índia; Jun fraco (-0.9%). <b style="color:var(--text)">Prata:</b> Jan forte (+4.3%) = segue ouro com amplificação industrial; Jun fraco (-2.9%). <b style="color:var(--text)">Cobre:</b> Mar-Abr fortes = temporada de construção Hemisfério Norte; Nov fraco (-1.1%). Gás Natural usa FRED MHHNGSP (preco spot, sem distorcao de roll). Cobre usa IMF PCOPPUSDM. Sazonalidade é estatística histórica — não garante resultado futuro.
  </div>

  <div class="section-title">COT — Posicionamento Institucional (CFTC, 2018–2026)</div>
  <div style="font-size:11px;color:var(--muted);margin-bottom:10px;line-height:1.6">
    Relatório <b style="color:var(--text)">Commitment of Traders — Disaggregated Futures Only</b> (CFTC). Publicado semanalmente às sextas (dados de terça).
    <b style="color:#f59e0b">Managed Money</b>: hedge funds e CTAs — especuladores puros, os que mais movem mercado.
    <b style="color:#818cf8">Large Speculators</b>: MM + Other Reportables ≈ equivalente ao "Non-Commercial" do Legacy COT.
    <b>Z-Score</b>: desvio padrão histórico das posições MM desde 2018 — identifica extremos de posicionamento. Net = Long − Short.
  </div>
  <div style="display:flex;flex-wrap:wrap;gap:14px;align-items:center;font-size:10px;color:var(--muted);margin-bottom:18px;padding:8px 14px;background:var(--surface2);border-radius:6px">
    <span style="font-weight:700;color:var(--text);letter-spacing:.5px;text-transform:uppercase">Guia Z-Score</span>
    <span><b style="color:#f43f5e">&#8805; +2&#963;</b>&nbsp;Sobrecomprado — sinal contrário de venda</span>
    <span><b style="color:#f59e0b">entre &#177;1&#963;</b>&nbsp;Neutro</span>
    <span><b style="color:#10b981">&#8804; &#8722;2&#963;</b>&nbsp;Sobrevendido — sinal contrário de compra</span>
    <span style="padding-left:12px;border-left:1px solid var(--border)">0 = média hist. &nbsp;&#183;&nbsp; &#177;1&#963; = normal &nbsp;&#183;&nbsp; &#177;2&#963; = extremo &nbsp;&#183;&nbsp; &#177;3&#963; = raro &nbsp;&#183;&nbsp; arrastar etiquetas &#963; (esq.) = zoom vertical &nbsp;&#183;&nbsp; arrastar no gr&#225;fico = pan &nbsp;&#183;&nbsp; scroll = zoom &nbsp;&#183;&nbsp; duplo clique = resetar</span>
  </div>

  <div class="grid2">
    <div class="chart-box">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <span class="chart-title" style="flex:1" id="cot-ouro-lbl">Ouro — COT COMEX &nbsp;|&nbsp; Managed Money &amp; Large Spec.</span>
        <span id="ch-cot-ouro-zlbl"></span>
      </div>
      <div id="ch-cot-ouro" style="height:430px"></div>{_cot_weekly_html('ouro', 'Managed Money')}
    </div>
    <div class="chart-box">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <span class="chart-title" style="flex:1" id="cot-prata-lbl">Prata — COT COMEX &nbsp;|&nbsp; Managed Money &amp; Large Spec.</span>
        <span id="ch-cot-prata-zlbl"></span>
      </div>
      <div id="ch-cot-prata" style="height:430px"></div>{_cot_weekly_html('prata', 'Managed Money')}
    </div>
  </div>
  <div class="grid2">
    <div class="chart-box">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <span class="chart-title" style="flex:1" id="cot-cobre-lbl">Cobre — COT COMEX &nbsp;|&nbsp; Managed Money &amp; Large Spec.</span>
        <span id="ch-cot-cobre-zlbl"></span>
      </div>
      <div id="ch-cot-cobre" style="height:430px"></div>{_cot_weekly_html('cobre', 'Managed Money')}
    </div>
    <div class="chart-box">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <span class="chart-title" style="flex:1" id="cot-wti-lbl">Petróleo WTI — COT NYMEX &nbsp;|&nbsp; Managed Money &amp; Large Spec.</span>
        <span id="ch-cot-wti-zlbl"></span>
      </div>
      <div id="ch-cot-wti" style="height:430px"></div>{_cot_weekly_html('wti', 'Managed Money')}
    </div>
  </div>
  <div class="grid2">
    <div class="chart-box">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <span class="chart-title" style="flex:1" id="cot-gasnat-lbl">Gás Natural — COT NYMEX &nbsp;|&nbsp; Managed Money &amp; Large Spec.</span>
        <span id="ch-cot-gasnat-zlbl"></span>
      </div>
      <div id="ch-cot-gasnat" style="height:430px"></div>{_cot_weekly_html('gasnat', 'Managed Money')}
    </div>
    <div></div>
  </div>
  <div class="source-note">Fonte: CFTC Disaggregated Futures Only Report. 2018–2025 (1.825 registros). <b style="color:#f59e0b">Managed Money</b>: hedge funds/CTAs (posição especulativa pura). <b style="color:#818cf8">Large Speculators</b>: Managed Money + Other Reportables ≈ Non-Commercial do Legacy COT (todos os grandes especuladores). <b>Z-Score</b>: desvio padrão histórico do MM Net — acima de +2σ = sobrecomprado; abaixo de -2σ = sobrevendido (sinal contrário).</div>

</section>


<!-- ═══════════════════════════════ SAZ AGRICOLA ═══════════════════════════ -->
<section id="tab-saz-agricola">
  <div class="section-title">Sazonalidade Histórica — Grãos (últimos 20 anos)</div>
  <div class="grid2">
    <div class="chart-box"><div class="chart-title">Milho (ZC=F)</div><div id="ch-saz-milho" style="height:260px"></div></div>
    <div class="chart-box"><div class="chart-title">Trigo (IMF Global Wheat)</div><div id="ch-saz-trigo" style="height:260px"></div></div>
  </div>
  <div class="grid2">
    <div class="chart-box"><div class="chart-title">Soja (ZS=F)</div><div id="ch-saz-soja" style="height:260px"></div></div>
    <div class="chart-box"><div class="chart-title">BBG Commodity Index (^BCOM)</div><div id="ch-saz-bcom" style="height:260px"></div></div>
  </div>
  <div class="source-note">Retorno médio mensal. Trigo usa preço IMF Global Wheat (FRED PWHEAMTUSDM) — referência cash sem roll. Milho e Soja usam contratos futuros ZC=F / ZS=F (Yahoo Finance). BBG Commodity Index (^BCOM) é o Bloomberg Commodity Index — cesta ampla de energia, metais e agrícolas. Sazonalidade ligada a ciclos de plantio/colheita hemisférios norte e sul.</div>

  <div class="section-title">COT — Posicionamento Institucional — Grãos (CFTC, 2018–2026)</div>
  <div style="font-size:11px;color:var(--muted);margin-bottom:10px;line-height:1.6">
    Relatório <b style="color:var(--text)">Commitment of Traders — Disaggregated Futures Only</b> (CFTC).
    <b style="color:#f59e0b">Managed Money</b>: fundos especulativos (hedge funds, CTAs) em grãos.
    <b style="color:#818cf8">Large Speculators</b>: MM + Other Reportables ≈ Non-Commercial do Legacy COT.
    Posicionamento em grãos é altamente sazonal — correlaciona com ciclos de plantio e colheita.
  </div>
  <div style="display:flex;flex-wrap:wrap;gap:14px;align-items:center;font-size:10px;color:var(--muted);margin-bottom:18px;padding:8px 14px;background:var(--surface2);border-radius:6px">
    <span style="font-weight:700;color:var(--text);letter-spacing:.5px;text-transform:uppercase">Guia Z-Score</span>
    <span><b style="color:#f43f5e">&#8805; +2&#963;</b>&nbsp;Sobrecomprado — contrarian de venda</span>
    <span><b style="color:#f59e0b">entre &#177;1&#963;</b>&nbsp;Neutro</span>
    <span><b style="color:#10b981">&#8804; &#8722;2&#963;</b>&nbsp;Sobrevendido — contrarian de compra</span>
    <span style="padding-left:12px;border-left:1px solid var(--border)">0 = média hist. &nbsp;&#183;&nbsp; &#177;2&#963; = extremo &nbsp;&#183;&nbsp; arrastar etiquetas &#963; (esq.) = zoom vertical &nbsp;&#183;&nbsp; arrastar no gr&#225;fico = pan &nbsp;&#183;&nbsp; scroll = zoom &nbsp;&#183;&nbsp; duplo clique = resetar</span>
  </div>
  <div class="grid2">
    <div class="chart-box">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <span class="chart-title" style="flex:1" id="cot-milho-lbl">Milho — COT CBOT &nbsp;|&nbsp; Managed Money &amp; Large Spec.</span>
        <span id="ch-cot-milho-zlbl"></span>
      </div>
      <div id="ch-cot-milho" style="height:430px"></div>{_cot_weekly_html('milho', 'Managed Money')}
    </div>
    <div class="chart-box">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <span class="chart-title" style="flex:1" id="cot-trigo-lbl">Trigo SRW — COT CBOT &nbsp;|&nbsp; Managed Money &amp; Large Spec.</span>
        <span id="ch-cot-trigo-zlbl"></span>
      </div>
      <div id="ch-cot-trigo" style="height:430px"></div>{_cot_weekly_html('trigo', 'Managed Money')}
    </div>
  </div>
  <div class="grid2">
    <div class="chart-box">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <span class="chart-title" style="flex:1" id="cot-soja-lbl">Soja — COT CBOT &nbsp;|&nbsp; Managed Money &amp; Large Spec.</span>
        <span id="ch-cot-soja-zlbl"></span>
      </div>
      <div id="ch-cot-soja" style="height:430px"></div>{_cot_weekly_html('soja', 'Managed Money')}
    </div>
    <div></div>
  </div>
  <div class="source-note">Fonte: CFTC Disaggregated Futures Only Report. <b style="color:#f59e0b">Managed Money</b>: hedge funds e CTAs. <b style="color:#818cf8">Large Speculators</b>: MM + Other Reportables ≈ Non-Commercial. Milho: CORN — CBOT. Trigo: WHEAT-SRW — CBOT. Soja: SOYBEANS — CBOT.</div>

  <div class="section-title" style="margin-top:28px">COT — BBG Commodity Index (CFTC TFF, 2022–2026)</div>
  <div style="font-size:11px;color:var(--muted);margin-bottom:10px;line-height:1.6">
    Relatório <b style="color:var(--text)">Traders in Financial Futures (TFF)</b> do CFTC — CBOT.
    <b style="color:#f59e0b">Asset Managers</b>: gestoras institucionais (primary, igual Sharketo).
    <b style="color:#818cf8">Leveraged Funds</b>: hedge funds / CTAs. Histórico disponível a partir de 2022 (data de lançamento do contrato no CBOT).
  </div>
  <div style="display:flex;flex-wrap:wrap;gap:14px;align-items:center;font-size:10px;color:var(--muted);margin-bottom:18px;padding:8px 14px;background:var(--surface2);border-radius:6px">
    <span style="font-weight:700;color:var(--text);letter-spacing:.5px;text-transform:uppercase">Guia Z-Score</span>
    <span><b style="color:#f43f5e">&#8805; +2&#963;</b>&nbsp;Sobrecomprado — contrarian de venda</span>
    <span><b style="color:#f59e0b">entre &#177;1&#963;</b>&nbsp;Neutro</span>
    <span><b style="color:#10b981">&#8804; &#8722;2&#963;</b>&nbsp;Sobrevendido — contrarian de compra</span>
  </div>
  <div class="grid2">
    <div class="chart-box">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <span class="chart-title" style="flex:1" id="cot-bcom-lbl">BBG Commodity — COT CBOT &nbsp;|&nbsp; Asset Managers &amp; Lev. Funds</span>
        <span id="ch-cot-bcom-zlbl"></span>
      </div>
      <div id="ch-cot-bcom" style="height:430px"></div>{_cot_weekly_html('bcom', 'Asset Manager')}
    </div>
    <div></div>
  </div>
  <div class="source-note">Fonte: CFTC Traders in Financial Futures (TFF). <b style="color:#f59e0b">Asset Managers</b>: gestoras institucionais em contratos BBG Commodity Index (CBOT). Contrato disponível no CFTC a partir de 2022 — histórico curto mas crescente (OI ~220k contratos em 2026).</div>

</section>


<!-- ═══════════════════════════════ BITCOIN ════════════════════════════════ -->
<section id="tab-bitcoin">

  <div class="section-title">Ciclo de 4 Anos — Bitcoin (Análise por Halving)</div>
  <div id="btc-stats-boxes" class="btc-stats"></div>
  <div class="chart-box" style="margin-bottom:20px">
    <div class="chart-title">Ciclos Sobrepostos — Preço indexado ao Halving (= 1.0)</div>
    <div class="btc-chart-wrap" style="position:relative">
      <div id="ch-btc-cycle" style="height:440px"></div>
    </div>
  </div>

  <!-- ── Insights Institucionais ───────────────────────────────── -->
  <div class="section-title">Insights Institucionais — Bitcoin</div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px;margin-bottom:28px">

    <div class="stat-box" style="border-left:3px solid #f59e0b">
      <div class="stat-lbl">ETFs Spot nos EUA — Demanda Estrutural</div>
      <div style="font-size:12px;color:var(--text);line-height:1.7;margin-top:6px">
        Jan/2024: SEC aprova ETFs spot. BlackRock (IBIT), Fidelity (FBTC) e outros 9 fundos passaram a absorver BTC do mercado diariamente.
        Em 2024, ETFs acumularam ~569k BTC líquidos — superando a emissão do halving de abril/2024 (≈164k BTC/ano).
        IBIT tornou-se o ETF de crescimento mais rápido da história: US$10 bi em 49 dias (recorde anterior era de anos).
        <span style="color:var(--muted);font-size:10px;display:block;margin-top:4px">Impacto: demanda institucional criou "choque de demanda" estrutural sem precedente histórico nos 3 ciclos anteriores.</span>
      </div>
    </div>

    <div class="stat-box" style="border-left:3px solid #a78bfa">
      <div class="stat-lbl">MVRV Z-Score — Sobreaquecimento de Mercado</div>
      <div style="font-size:12px;color:var(--text);line-height:1.7;margin-top:6px">
        MVRV = Market Cap ÷ Realized Cap. Z-Score mede desvios extremos.
        <b style="color:#f43f5e">Z &gt; 7</b>: topo histórico de ciclo (2013: 9.5, 2017: 9.7, 2021: 7.1). Sempre marcou regiões de venda de longo prazo.
        <b style="color:#10b981">Z &lt; 0</b>: fundo de ciclo — preço abaixo do custo médio de todo mercado. Melhor janela de acumulação histórica.
        <b style="color:var(--warn)">Z 2–4</b>: zona intermediária, ciclo em andamento.
        <span style="color:var(--muted);font-size:10px;display:block;margin-top:4px">Fonte: Glassnode / LookIntoBitcoin. Monitorar: lookintobitcoin.com/charts/mvrv-zscore/</span>
      </div>
    </div>

    <div class="stat-box" style="border-left:3px solid #10b981">
      <div class="stat-lbl">Long-Term Holders (LTH) — Comportamento das Mãos Fortes</div>
      <div style="font-size:12px;color:var(--text);line-height:1.7;margin-top:6px">
        LTH = endereços que não moveram BTC há &gt;155 dias. Controlam ~70% do supply circulante.
        Padrão histórico: LTH acumulam nos fundos de ciclo → distribuem nos topos → reduzem supply em circulação.
        Quando LTH supply atinge máxima histórica, sinaliza mercado comprimido aguardando catalisador.
        Quando LTH passam a distribuir massivamente, o topo de ciclo está próximo (geralmente 3–6 meses depois).
        <span style="color:var(--muted);font-size:10px;display:block;margin-top:4px">Fonte: Glassnode. Métrica: "Long-Term Holder Net Position Change"</span>
      </div>
    </div>

    <div class="stat-box" style="border-left:3px solid #00bfff">
      <div class="stat-lbl">Stock-to-Flow (S2F) — Modelo de Escassez</div>
      <div style="font-size:12px;color:var(--text);line-height:1.7;margin-top:6px">
        S2F = estoque atual ÷ produção anual. Ouro: S2F ≈ 60. Após halving de 2024: BTC S2F = 112 (mais escasso que ouro).
        Modelo de Plan B correlaciona S2F com preço de mercado historicamente (R² &gt; 0.94 até 2021).
        Ciclos anteriores: cada halving dobra o S2F e precedeu rally de 10x–100x nos 12–18 meses seguintes.
        Limitações: modelo assume que apenas oferta importa; ignora choques de demanda/regulação. 4º ciclo incorpora demanda ETF como variável nova.
        <span style="color:var(--muted);font-size:10px;display:block;margin-top:4px">Referência: PlanB (@100trillionUSD). Usar como contexto, não como previsão.</span>
      </div>
    </div>

    <div class="stat-box" style="border-left:3px solid #f43f5e">
      <div class="stat-lbl">Reservas em Exchanges — Fluxo de Custódia</div>
      <div style="font-size:12px;color:var(--text);line-height:1.7;margin-top:6px">
        BTC saindo de exchanges = acumulação (reduz supply disponível para venda imediata).
        BTC entrando em exchanges = intenção de venda ou liquidação de posições.
        Desde 2020, reservas nas exchanges caíram de ~3,1M BTC para ~2,3M BTC — queda de 26% enquanto o preço subiu 10x+.
        Pós-ETF: parte do BTC custodiado por BlackRock/Coinbase Custody saiu da contagem de exchanges, mas representa demanda permanente.
        <span style="color:var(--muted);font-size:10px;display:block;margin-top:4px">Fonte: Glassnode / CryptoQuant. Métrica: "Exchange Net Position Change"</span>
      </div>
    </div>

    <div class="stat-box" style="border-left:3px solid #fb923c">
      <div class="stat-lbl">Hash Rate &amp; Dificuldade — Segurança e Confiança dos Miners</div>
      <div style="font-size:12px;color:var(--text);line-height:1.7;margin-top:6px">
        Hash rate = poder computacional total da rede. Atingiu recordes históricos em 2024–2025 (700+ EH/s).
        Miners só investem em hardware caro quando acreditam no preço futuro — hash rate alto = confiança de longo prazo.
        Pós-halving: receita dos miners cai 50%. Miners ineficientes capitulam → hash rate cai temporariamente → se recupera em meses.
        Capitulação de miners historicamente coincide com fundos de mercado (hash ribbons: MA30 cruza MA60 = sinal de compra).
        <span style="color:var(--muted);font-size:10px;display:block;margin-top:4px">Fonte: Blockchain.com / HashrateIndex. Métrica: "Hash Ribbons" (capriole.io)</span>
      </div>
    </div>

  </div>

  <div class="section-title">Sazonalidade Mensal — Bitcoin</div>
  <div class="grid2">
    <div class="chart-box"><div class="chart-title">Retorno Médio Mensal (histórico completo)</div><div id="ch-btc-saz" style="height:280px"></div></div>
    <div class="chart-box" style="padding:20px">
      <div class="chart-title" style="margin-bottom:14px">Halvings — Datas e Contexto</div>
      <table>
        <thead><tr><th>#</th><th>Data</th><th>Recompensa</th><th>Resultado Ciclo</th></tr></thead>
        <tbody>
          <tr><td>1º Halving</td><td>28 Nov 2012</td><td>50→25 BTC</td><td style="color:#10b981">+8.858% do halving ao topo</td></tr>
          <tr><td>2º Halving</td><td>09 Jul 2016</td><td>25→12.5 BTC</td><td style="color:#10b981">+2.967% do halving ao topo</td></tr>
          <tr><td>3º Halving</td><td>11 Mai 2020</td><td>12.5→6.25 BTC</td><td style="color:#10b981">+1.875% do halving ao topo</td></tr>
          <tr><td>4º Halving</td><td>19 Abr 2024</td><td>6.25→3.125 BTC</td><td style="color:var(--warn)">Em andamento...</td></tr>
        </tbody>
      </table>
      <div class="source-note" style="margin-top:14px">Padrão histórico: Topo ~12–18 meses após o halving. Diminuição dos retornos a cada ciclo. Amostra pequena (4 ciclos) — interpretar com cautela. Fonte: CoinGecko / Yahoo Finance.</div>
    </div>
  </div>

  <div class="section-title">COT — Posicionamento Institucional — Bitcoin (CFTC TFF, 2018–2026)</div>
  <div style="font-size:11px;color:var(--muted);margin-bottom:10px;line-height:1.6">
    Relatório <b style="color:var(--text)">Traders in Financial Futures (TFF)</b> do CFTC. Contrato: <b style="color:var(--text)">BITCOIN — CME</b>.
    <b style="color:#f59e0b">Leveraged Funds</b>: hedge funds e CTAs com posição em BTC futures na CME — sinal especulativo puro.
    CME Bitcoin Futures iniciados em Dez/2017 — histórico desde 2018. Z-Score identifica momentos de extremo posicionamento especulativo.
  </div>
  <div style="display:flex;flex-wrap:wrap;gap:14px;align-items:center;font-size:10px;color:var(--muted);margin-bottom:18px;padding:8px 14px;background:var(--surface2);border-radius:6px">
    <span style="font-weight:700;color:var(--text);letter-spacing:.5px;text-transform:uppercase">Guia Z-Score</span>
    <span><b style="color:#f43f5e">&#8805; +2&#963;</b>&nbsp;Sobrecomprado — contrarian de venda</span>
    <span><b style="color:#f59e0b">entre &#177;1&#963;</b>&nbsp;Neutro</span>
    <span><b style="color:#10b981">&#8804; &#8722;2&#963;</b>&nbsp;Sobrevendido — contrarian de compra</span>
    <span style="padding-left:12px;border-left:1px solid var(--border)">0 = média hist. &nbsp;&#183;&nbsp; &#177;2&#963; = extremo &nbsp;&#183;&nbsp; arrastar etiquetas &#963; (esq.) = zoom vertical &nbsp;&#183;&nbsp; arrastar no gr&#225;fico = pan &nbsp;&#183;&nbsp; scroll = zoom &nbsp;&#183;&nbsp; duplo clique = resetar</span>
  </div>
  <div class="grid2">
    <div class="chart-box">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <span class="chart-title" style="flex:1" id="cot-btc-lbl">Bitcoin CME — COT TFF &nbsp;|&nbsp; Asset Managers &amp; Lev. Funds</span>
        <span id="ch-cot-btc-zlbl"></span>
      </div>
      <div id="ch-cot-btc" style="height:430px"></div>{_cot_weekly_html('btc', 'Asset Manager')}
    </div>
    <div></div>
  </div>
  <div class="source-note">Fonte: CFTC TFF Report. Bitcoin CME Futures (código 133741). <b style="color:#f59e0b">Leveraged Funds</b> net longo em BTC = hedge funds com viés bullish. Correlacionar com ciclo do halving — especuladores tendem a acumular long antes de topos de ciclo.</div>

  <div class="section-title">Bitcoin — Custo de Produção (Modelo Capriole)</div>
  <div id="btc-prodcost-stats" class="btc-stats"></div>
  <div class="chart-box" style="margin-bottom:20px">
    <div class="chart-title">Preço vs. Custo Elétrico de Produção</div>
    <div id="ch-btc-prodcost" style="height:420px"></div>
  </div>
  <div class="source-note">
    Fonte: preço e hashrate via blockchain.info (7 dias, média móvel) &middot; metodologia Capriole Investments
    (capriole.com/bitcoins-production-cost). A eficiência de fleet (J/TH) não é publicada pela Capriole — foi recuperada
    resolvendo de trás pra frente 6 leituras reais e datadas do Bitcoin Electrical Cost publicado pela própria Capriole
    (nov/2022 a jul/2026, via capriole.com, newsletter e X de Charles Edwards), não ajustada a nenhum gráfico externo.
    Premissas: $0,05/kWh, PUE 1,10, razão elétrico/total 79% (atualizada do documento de metodologia de 2019, que
    indicava 60%, para bater com os prints reais recentes). Histórico anterior a nov/2022 é reconstrução própria.
    Atualizado semanalmente junto com o restante do pipeline.
  </div>

</section>

</main>

<script>
// ─── Tab switching ─────────────────────────────────────────────────────
function showTab(id, btn) {{
  document.querySelectorAll("section").forEach(s => s.classList.remove("active"));
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.getElementById("tab-" + id).classList.add("active");
  if (btn) btn.classList.add("active");
  if (!window._rendered) window._rendered = {{}};
  if (!window._rendered[id]) {{ window._rendered[id] = true; renderCharts(id); }}
  // Bug conhecido do Plotly: se o container estava com display:none no momento
  // do Plotly.newPlot, o gráfico "trava" numa largura padrão (~700px) mesmo com
  // responsive:true — o ResizeObserver não reage porque o tamanho do container
  // não "muda" depois (só passa a ficar visível). Força um resize explícito
  // depois que o layout já rodou (display:block aplicado).
  requestAnimationFrame(() => {{
    document.querySelectorAll("#tab-" + id + " .js-plotly-plot").forEach(el => {{
      try {{ Plotly.Plots.resize(el); }} catch(e) {{}}
    }});
  }});
}}

// ─── Theme ────────────────────────────────────────────────────────────
var LAYOUT_BASE = {{
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor:  "rgba(0,0,0,0)",
  font: {{ family:"-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif", color:"#7d90a8", size:11 }},
  margin: {{ t:10, b:40, l:50, r:10 }},
  xaxis: {{ gridcolor:"rgba(255,255,255,.05)", linecolor:"rgba(255,255,255,.08)", zerolinecolor:"rgba(255,255,255,.05)" }},
  yaxis: {{ gridcolor:"rgba(255,255,255,.05)", linecolor:"rgba(255,255,255,.08)", zerolinecolor:"rgba(255,255,255,.05)" }},
  legend: {{ bgcolor:"rgba(0,0,0,0)", font:{{ color:"#e8eef5" }} }},
  hovermode: "x unified",
}};
var CFG = {{ responsive:true, displayModeBar:false }};
var CFG_Z = {{ responsive:true, scrollZoom:true, displayModeBar:true, displaylogo:false,
  modeBarButtonsToRemove:["select2d","lasso2d","toImage","resetScale2d","hoverClosestCartesian","hoverCompareCartesian"] }};

// ─── Line chart helper (Fed Rate) ────────────────────────────────────
function lineChart(divId, data, color) {{
  if (!data) {{ document.getElementById(divId).innerHTML = '<p style="color:#7d90a8;padding:20px;text-align:center">Aguardando dados — clique em Atualizar.</p>'; return; }}
  var trace = {{ type:"scatter", mode:"lines", x:data.dates, y:data.values, line:{{ color:color, width:2 }}, fill:"tozeroy", fillcolor:color.replace(")",",0.08)").replace("rgb","rgba"), hovertemplate:"<b>%{{x}}</b><br>%{{y:.2f}}%<extra></extra>" }};
  Plotly.newPlot(divId, [trace], Object.assign({{}}, LAYOUT_BASE, {{ margin:{{ t:4,b:32,l:52,r:8 }}, yaxis: Object.assign({{}}, LAYOUT_BASE.yaxis, {{ ticksuffix:"%", tickformat:".2f" }}) }}), CFG);
}}

// ─── CPI / Core CPI chart — eixo %, tooltip, linha meta 2% ──────────
function cpiLineChart(divId, data, color, label) {{
  if (!data) {{ document.getElementById(divId).innerHTML = '<p style="color:#7d90a8;padding:20px;text-align:center">Aguardando dados — clique em Atualizar.</p>'; return; }}
  var n = Math.min(data.dates.length, 72);
  var dates  = data.dates.slice(-n);
  var values = data.values.slice(-n);
  var minV = Math.min.apply(null, values);
  var maxV = Math.max.apply(null, values);
  var pad = (maxV - minV) * 0.15 || 0.5;
  var trace = {{
    type:"scatter", mode:"lines+markers", name:label,
    x:dates, y:values,
    line:{{ color:color, width:2.5 }},
    marker:{{ size:3, color:color }},
    fill:"tozeroy",
    fillcolor:color.replace("rgb(","rgba(").replace(")",",0.07)").replace("#f43f5e","rgba(244,63,94,0.07)").replace("#f59e0b","rgba(245,158,11,0.07)"),
    hovertemplate:"<b>%{{x}}</b><br>" + label + ": <b>%{{y:.2f}}%</b><extra></extra>",
  }};
  var layout = Object.assign({{}}, LAYOUT_BASE, {{
    margin:{{ t:8, b:36, l:52, r:16 }},
    hovermode:"x unified",
    yaxis: Object.assign({{}}, LAYOUT_BASE.yaxis, {{
      ticksuffix:"%", tickformat:".1f",
      range:[Math.min(minV - pad, 1.5), maxV + pad],
      dtick: Math.ceil((maxV - minV + 2*pad) / 6 * 2) / 2,
    }}),
    shapes:[{{
      type:"line", x0:dates[0], x1:dates[dates.length-1], y0:2, y1:2,
      line:{{ color:"rgba(16,185,129,0.5)", width:1.5, dash:"dot" }}
    }}],
    annotations:[{{
      x:dates[dates.length-1], y:2, xanchor:"right", yanchor:"bottom",
      text:"Meta 2%", showarrow:false,
      font:{{ color:"#10b981", size:10 }}, bgcolor:"rgba(8,12,20,0.7)",
    }}],
  }});
  Plotly.newPlot(divId, [trace], layout, CFG);
}}

// ─── NFP bar chart — first print, eixo cortado ±900K ────────────────
function nfpBarChart(divId, data) {{
  if (!data) {{ document.getElementById(divId).innerHTML = '<p style="color:#7d90a8;padding:20px;text-align:center">Aguardando dados.</p>'; return; }}
  var CLIP = 900;
  var dates  = data.dates;
  var vals   = data.values;

  var colors = vals.map(function(v) {{
    if (v < 0)    return "#f43f5e";
    if (v >= 500) return "#10b981";
    if (v >= 200) return "#34d399";
    if (v >= 100) return "#f59e0b";
    return "#6b7d94";
  }});

  var display = vals.map(function(v) {{
    if (v >  CLIP) return  CLIP;
    if (v < -CLIP) return -CLIP;
    return v;
  }});

  var hoverVals = vals.map(function(v) {{
    var abs = Math.abs(v);
    var sign = v >= 0 ? "+" : "";
    if (abs >= 1000) return sign + (v/1000).toFixed(1) + "M";
    return sign + v.toLocaleString() + "K";
  }});

  var annots = [];
  vals.forEach(function(v, i) {{
    if (Math.abs(v) > CLIP) {{
      var abs = Math.abs(v);
      var sign = v >= 0 ? "+" : "";
      var txt  = abs >= 1000 ? sign + (v/1000).toFixed(1) + "M" : sign + v + "K";
      annots.push({{
        x: dates[i], y: display[i],
        text: txt, showarrow: false,
        font: {{ size: 9, color: v >= 0 ? "#10b981" : "#f43f5e" }},
        yanchor: v >= 0 ? "bottom" : "top",
        yshift: v >= 0 ? 4 : -4,
      }});
    }}
  }});

  var trace = {{
    type: "bar", x: dates, y: display,
    marker: {{ color: colors, opacity: 0.9 }},
    customdata: hoverVals,
    hovertemplate: "<b>%{{x|%b %Y}}</b><br>NFP: <b>%{{customdata}}</b><extra></extra>",
  }};

  var layout = Object.assign({{}}, LAYOUT_BASE, {{
    margin: {{ t:8, b:48, l:56, r:12 }},
    bargap: 0.25,
    hovermode: "x unified",
    xaxis: Object.assign({{}}, LAYOUT_BASE.xaxis, {{
      tickformat: "%b'%y", tickangle: -45,
      dtick: "M6", tickfont: {{ size: 9 }},
    }}),
    yaxis: Object.assign({{}}, LAYOUT_BASE.yaxis, {{
      ticksuffix: "K",
      range: [-CLIP * 1.15, CLIP * 1.25],
      zeroline: true, zerolinecolor: "#30363d", zerolinewidth: 1.5,
    }}),
    shapes: [{{
      type:"line", x0:dates[0], x1:dates[dates.length-1], y0:200, y1:200,
      line:{{ color:"rgba(52,211,153,0.35)", width:1, dash:"dot" }}
    }}, {{
      type:"line", x0:dates[0], x1:dates[dates.length-1], y0:0, y1:0,
      line:{{ color:"rgba(100,116,139,0.5)", width:1 }}
    }}],
    annotations: annots.concat([{{
      x: dates[dates.length-1], y: 200, xanchor:"right", yanchor:"bottom",
      text:"200K ref.", showarrow:false,
      font:{{ color:"rgba(52,211,153,0.6)", size:9 }}, bgcolor:"rgba(8,12,20,0.6)"
    }}]),
  }});
  Plotly.newPlot(divId, [trace], layout, CFG);
}}

// ─── Wage Growth bar chart — AHE YoY%, mesmo estilo do NFP ──────────
function wageGrowthChart(divId, data) {{
  if (!data) {{ document.getElementById(divId).innerHTML = '<p style="color:#7d90a8;padding:20px;text-align:center">Aguardando dados.</p>'; return; }}
  var dates = data.dates;
  var vals  = data.values;

  var colors = vals.map(function(v) {{
    if (v >= 5.0) return "#f43f5e";
    if (v >= 4.0) return "#f59e0b";
    if (v >= 2.5) return "#34d399";
    return "#6b7d94";
  }});

  var trace = {{
    type: "bar", x: dates, y: vals,
    marker: {{ color: colors, opacity: 0.9 }},
    hovertemplate: "<b>%{{x|%b %Y}}</b><br>Wage Growth YoY: <b>%{{y:.1f}}%</b><extra></extra>",
  }};

  var layout = Object.assign({{}}, LAYOUT_BASE, {{
    margin: {{ t:8, b:48, l:48, r:12 }},
    bargap: 0.25,
    hovermode: "x unified",
    xaxis: Object.assign({{}}, LAYOUT_BASE.xaxis, {{
      tickformat: "%b'%y", tickangle: -45,
      dtick: "M6", tickfont: {{ size: 9 }},
    }}),
    yaxis: Object.assign({{}}, LAYOUT_BASE.yaxis, {{
      ticksuffix: "%",
      zeroline: true, zerolinecolor: "#30363d", zerolinewidth: 1.5,
    }}),
    shapes: [{{
      type:"line", x0:dates[0], x1:dates[dates.length-1], y0:3.5, y1:3.5,
      line:{{ color:"rgba(52,211,153,0.35)", width:1, dash:"dot" }}
    }}],
    annotations: [{{
      x: dates[dates.length-1], y: 3.5, xanchor:"right", yanchor:"bottom",
      text:"3,5% ref.", showarrow:false,
      font:{{ color:"rgba(52,211,153,0.6)", size:9 }}, bgcolor:"rgba(8,12,20,0.6)"
    }}],
  }});
  Plotly.newPlot(divId, [trace], layout, CFG);
}}

// ─── IPCA chart — meta 3% + teto 4.5% ───────────────────────────────
function ipcaLineChart(divId, data) {{
  if (!data) {{ document.getElementById(divId).innerHTML = '<p style="color:#7d90a8;padding:20px;text-align:center">Aguardando dados — execute o pipeline.</p>'; return; }}
  var n = Math.min(data.dates.length, 72);
  var dates  = data.dates.slice(-n);
  var values = data.values.slice(-n);
  var minV = Math.min.apply(null, values);
  var maxV = Math.max.apply(null, values);
  var pad = (maxV - minV) * 0.15 || 0.5;
  var trace = {{
    type:"scatter", mode:"lines+markers", name:"IPCA YoY",
    x:dates, y:values,
    line:{{ color:"#fb923c", width:2.5 }},
    marker:{{ size:3, color:"#fb923c" }},
    fill:"tozeroy", fillcolor:"rgba(251,146,60,0.07)",
    hovertemplate:"<b>%{{x}}</b><br>IPCA YoY: <b>%{{y:.2f}}%</b><extra></extra>",
  }};
  var layout = Object.assign({{}}, LAYOUT_BASE, {{
    margin:{{ t:8, b:36, l:52, r:16 }},
    hovermode:"x unified",
    yaxis: Object.assign({{}}, LAYOUT_BASE.yaxis, {{
      ticksuffix:"%", tickformat:".1f",
      range:[Math.min(minV - pad, 1.5), maxV + pad],
    }}),
    shapes:[
      {{ type:"line", x0:dates[0], x1:dates[dates.length-1], y0:3, y1:3, line:{{ color:"rgba(16,185,129,0.5)", width:1.5, dash:"dot" }} }},
      {{ type:"line", x0:dates[0], x1:dates[dates.length-1], y0:4.5, y1:4.5, line:{{ color:"rgba(245,158,11,0.5)", width:1.5, dash:"dot" }} }},
    ],
    annotations:[
      {{ x:dates[dates.length-1], y:3, xanchor:"right", yanchor:"bottom", text:"Meta 3%", showarrow:false, font:{{ color:"#10b981", size:10 }}, bgcolor:"rgba(8,12,20,0.7)" }},
      {{ x:dates[dates.length-1], y:4.5, xanchor:"right", yanchor:"bottom", text:"Teto 4.5%", showarrow:false, font:{{ color:"#f59e0b", size:10 }}, bgcolor:"rgba(8,12,20,0.7)" }},
    ],
  }});
  Plotly.newPlot(divId, [trace], layout, CFG);
}}

// ─── Bar chart helper (seasonality) ──────────────────────────────────
function barChart(divId, data) {{
  if (!data) {{ document.getElementById(divId).innerHTML = '<p style="color:#7d90a8;padding:20px;text-align:center">Dados insuficientes.</p>'; return; }}
  var trace = {{
    type: "bar", x: data.months, y: data.values,
    marker: {{ color: data.colors, opacity: 0.88 }},
    text: data.values.map(function(v) {{ return (v >= 0 ? "+" : "") + v.toFixed(2) + "%" }}),
    textposition: "outside", textfont: {{ size:10, color:"#94a3b8" }},
    hovertemplate: "%{{x}}: %{{y:.2f}}%<extra></extra>",
  }};
  var layout = Object.assign({{}}, LAYOUT_BASE, {{
    margin: {{ t:16, b:40, l:52, r:12 }},
    xaxis: Object.assign({{}}, LAYOUT_BASE.xaxis, {{ type: "category", tickfont: {{ size:11 }} }}),
    shapes: [{{ type:"line", x0:-0.5, x1:11.5, y0:0, y1:0, line:{{ color:"rgba(255,255,255,.25)", width:1 }} }}],
  }});
  Plotly.newPlot(divId, [trace], layout, CFG);
}}

// ─── BTC cycle chart ──────────────────────────────────────────────────
var CYCLE_COLORS = ["#c9a227","#00bfff","#a78bfa","#10b981"];
function btcCycleChart(cycles) {{
  if (!cycles) {{ document.getElementById("ch-btc-cycle").innerHTML = '<p style="color:#7d90a8;padding:20px;text-align:center">Dados insuficientes.</p>'; return; }}
  var traces = [];
  var keys = Object.keys(cycles);

  // Limita o eixo X ao progresso do ciclo atual + 80 dias de margem
  var lastKey = keys[keys.length - 1];
  var currentCycleMax = Math.max.apply(null, cycles[lastKey].x);
  var xMax = currentCycleMax + 80;

  keys.forEach(function(k, i) {{
    var c = cycles[k];
    var isCurrent = i === keys.length - 1;
    traces.push({{
      type:"scatter", mode:"lines", name: c.label + " (" + c.halving_date + ")",
      x: c.x, y: c.y,
      line: {{ color: CYCLE_COLORS[i % CYCLE_COLORS.length], width: isCurrent ? 2.5 : 1.5 }},
      opacity: isCurrent ? 1 : 0.65,
      hovertemplate: "Dia %{{x}}: %{{y:.2f}}x<extra>" + c.label + "</extra>",
    }});
  }});
  var layout = Object.assign({{}}, LAYOUT_BASE, {{
    margin:{{ t:14,b:54,l:68,r:20 }},
    dragmode:"pan",
    xaxis: {{
      title:"Dias desde o Halving",
      range: [0, xMax],
      autorange: false,
      fixedrange: false,
      gridcolor:"rgba(255,255,255,.05)", linecolor:"rgba(255,255,255,.08)",
    }},
    yaxis: {{
      title:"Preço indexado (1.0 = dia do Halving)",
      type:"log",
      fixedrange: false,
      gridcolor:"rgba(255,255,255,.05)", linecolor:"rgba(255,255,255,.08)",
    }},
    shapes: [
      {{ type:"line", x0:365,x1:365,y0:0,y1:1,yref:"paper",line:{{color:"rgba(255,255,255,.18)",width:1,dash:"dot"}} }},
      {{ type:"line", x0:548,x1:548,y0:0,y1:1,yref:"paper",line:{{color:"rgba(251,191,36,.25)",width:1,dash:"dot"}} }},
      {{ type:"line", x0:730,x1:730,y0:0,y1:1,yref:"paper",line:{{color:"rgba(255,255,255,.18)",width:1,dash:"dot"}} }},
      {{ type:"line", x0:currentCycleMax,x1:currentCycleMax,y0:0,y1:1,yref:"paper",line:{{color:"rgba(16,185,129,.5)",width:1.5,dash:"dash"}} }},
    ],
    annotations: [
      {{ x:365, y:0.98, yref:"paper", text:"1 ano", showarrow:false, font:{{color:"#7d90a8",size:9}}, xanchor:"left" }},
      {{ x:548, y:0.98, yref:"paper", text:"18 meses (pico hist.)", showarrow:false, font:{{color:"#fbbf24",size:9}}, xanchor:"left" }},
      {{ x:730, y:0.98, yref:"paper", text:"2 anos", showarrow:false, font:{{color:"#7d90a8",size:9}}, xanchor:"left" }},
      {{ x:currentCycleMax, y:0.85, yref:"paper", text:"Hoje (ciclo 4)", showarrow:false, font:{{color:"#10b981",size:9}}, xanchor:"right" }},
    ],
    hovermode:"x",
    legend:{{ x:0.01, y:0.98, bgcolor:"rgba(0,0,0,0.3)", font:{{color:"#e8eef5",size:11}} }},
  }});
  Plotly.newPlot("ch-btc-cycle", traces, layout, CFG_Z).then(addBtcPriceScaleHandle);
}}

// Alça sobre a faixa esquerda do eixo Y — arraste vertical reescala o preço
// (mesmo padrão do Intermarket: pra baixo expande, pra cima comprime),
// via Plotly.relayout direto no yaxis.range. Overlay próprio (pointer-events
// auto) porque o comportamento nativo do Plotly nessa faixa (com
// dragmode:"pan") só desloca o range, não reescala.
var _btcScaleDrag = null;
var _btcDragRafPending = false;
var _btcLastMouseY = 0;

function _btcApplyScaleDragFrame() {{
  _btcDragRafPending = false;
  if (!_btcScaleDrag) return;
  var dy = _btcLastMouseY - _btcScaleDrag.startY;
  var center = (_btcScaleDrag.min + _btcScaleDrag.max) / 2;
  var halfRange = (_btcScaleDrag.max - _btcScaleDrag.min) / 2;
  var factor = Math.pow(1.006, dy); // arrastar pra baixo = expande, pra cima = comprime
  var newHalf = halfRange * factor;
  Plotly.relayout("ch-btc-cycle", {{ "yaxis.range": [center - newHalf, center + newHalf] }});
}}

document.addEventListener("mousemove", function(e) {{
  if (!_btcScaleDrag) return;
  _btcLastMouseY = e.clientY;
  if (!_btcDragRafPending) {{ _btcDragRafPending = true; requestAnimationFrame(_btcApplyScaleDragFrame); }}
}});
document.addEventListener("mouseup", function() {{ _btcScaleDrag = null; }});

function addBtcPriceScaleHandle() {{
  var gd = document.getElementById("ch-btc-cycle");
  var wrap = gd.parentElement;
  var old = wrap.querySelector(".price-scale-handle");
  if (old) old.remove();

  var nsRect = gd.querySelector(".draglayer .nsdrag");
  if (!nsRect) return;
  var handle = document.createElement("div");
  handle.className = "price-scale-handle";
  handle.title = "Arraste pra cima/baixo para reescalar o eixo de preço";
  handle.style.left   = nsRect.getAttribute("x") + "px";
  handle.style.top    = nsRect.getAttribute("y") + "px";
  handle.style.width  = nsRect.getAttribute("width") + "px";
  handle.style.height = nsRect.getAttribute("height") + "px";
  handle.addEventListener("mousedown", function(e) {{
    var range = gd._fullLayout.yaxis.range;
    _btcScaleDrag = {{ startY: e.clientY, min: range[0], max: range[1] }};
    e.preventDefault();
  }});
  wrap.appendChild(handle);
}}

// ─── COT Panel — positioning (top) + Z-score (bottom) num único subplot ─
// label = nome da linha primária (ex: "Asset Managers", "Managed Money")
// Sem label = Managed Money + Large Spec (Disaggregated)
// Com label = label + Lev. Funds (TFF)
// Z-score global sobre todo o período visível (2018→now) — mesma metodologia do Sharketo
// useLS=true → INVERTE qual série é a linha principal (sólida) e o Z-score: am_net
// (Large Speculators ≈ Non-Commercial) vira a primária, mm_net (Managed Money) vira
// secundária pontilhada. Usado só no WTI, pra bater com o que o Sharketo mostra.
function cotPanel(divId, zLblId, data, label, useLS) {{
  var el = document.getElementById(divId);
  if (!data) {{
    if (el) el.innerHTML = '<p style="color:#7d90a8;padding:16px;text-align:center;font-size:12px">Dados COT não disponíveis.</p>';
    return;
  }}
  var n = data.mm_net.length;
  if (n < 8) return;

  var primaryNet   = useLS ? data.am_net : data.mm_net;
  var secondaryNet = useLS ? data.mm_net : data.am_net;
  var lbl    = label || (useLS ? "Non-Comercial" : "Managed Money");
  var lbl2   = useLS ? "Managed Money" : (label ? "Lev. Funds" : "Large Spec. (≈Non-Comm.)");
  var dates  = data.dates;
  var toK    = function(v){{return Math.round(v/100)/10;}};

  // ── Z-score rolling 52 semanas, ddof=1 — padrão COTInsight/Tradingster/indústria ──
  var W   = 52;
  var zSrc = primaryNet;
  var zs  = zSrc.map(function(v, i) {{
    var start = Math.max(0, i - W + 1);
    var win = zSrc.slice(start, i + 1);
    var wn = win.length;
    if (wn < 4) return 0;
    var m = win.reduce(function(a,b){{return a+b}},0) / wn;
    var vari = win.reduce(function(a,x){{return a+(x-m)*(x-m)}},0) / (wn > 1 ? wn-1 : 1);
    var std = Math.sqrt(vari) || 1;
    return Math.round((v - m) / std * 100) / 100;
  }});
  var curZ  = zs[n-1];
  var zC    = curZ >= 2 ? "#f43f5e" : (curZ <= -2 ? "#10b981" : "#f59e0b");

  var lblEl = document.getElementById(zLblId);
  if (lblEl) {{
    lblEl.innerHTML = '<span style="background:' + zC + '22;color:' + zC + ';border:1px solid ' + zC + '44;border-radius:3px;padding:1px 6px;font-weight:700;font-size:11px">Z: ' + curZ.toFixed(2) + 'σ</span>';
  }}

  // ── Traces do painel superior ──
  var allVals = primaryNet.concat(secondaryNet).map(toK);
  var minV = Math.min.apply(null,allVals), maxV = Math.max.apply(null,allVals);
  var pad = (maxV - minV) * 0.12 || 5;
  var hasPrice = data.p_dates && data.p_dates.length > 0;

  // Todos os traces usam xaxis:"x" (eixo único) → hover unificado captura tudo
  var traces = [
    {{
      type:"scatter", mode:"lines", name:lbl, xaxis:"x", yaxis:"y",
      x:dates, y:primaryNet.map(toK),
      line:{{color:"#f59e0b", width:1.8}},
      hovertemplate:lbl + ": <b>%{{y:.1f}}K ctts</b><extra></extra>",
    }},
    {{
      type:"scatter", mode:"lines", name:lbl2, xaxis:"x", yaxis:"y",
      x:dates, y:secondaryNet.map(toK),
      line:{{color:"rgba(129,140,248,0.7)", width:1.4, dash:"dot"}},
      visible:"legendonly",
      hovertemplate:lbl2 + ": <b>%{{y:.1f}}K ctts</b><extra></extra>",
    }},
  ];
  if (hasPrice) {{
    traces.push({{
      type:"scatter", mode:"lines", name:"Preço", xaxis:"x", yaxis:"y3",
      x:data.p_dates, y:data.p_vals,
      line:{{color:"rgba(220,228,240,0.55)", width:1.5}},
      hovertemplate:"Preço: <b>%{{y:,.2f}}</b><extra></extra>",
    }});
  }}

  // ── Traces do painel inferior (Z-score) — mesmo xaxis:"x", yaxis:"y2" ──
  var zPos = zs.map(function(v){{return v>0?v:0;}});
  var zNeg = zs.map(function(v){{return v<0?v:0;}});
  traces.push({{type:"scatter",mode:"lines",xaxis:"x",yaxis:"y2",showlegend:false,
    x:dates,y:zPos,fill:"tozeroy",fillcolor:"rgba(103,232,249,0.18)",
    line:{{color:"transparent",width:0}},hoverinfo:"skip"}});
  traces.push({{type:"scatter",mode:"lines",xaxis:"x",yaxis:"y2",showlegend:false,
    x:dates,y:zNeg,fill:"tozeroy",fillcolor:"rgba(244,63,94,0.20)",
    line:{{color:"transparent",width:0}},hoverinfo:"skip"}});
  traces.push({{type:"scatter",mode:"lines",name:"Z-score",xaxis:"x",yaxis:"y2",showlegend:false,
    x:dates,y:zs,line:{{color:"#e2e8f0",width:1.6}},
    hovertemplate:"Z: <b>%{{y:.2f}}σ</b><extra></extra>"}});

  // Badge de Z no canto do painel inferior
  var zBadge = {{
    xref:"paper", x:0.01, yref:"y2",
    y: curZ >= 0 ? Math.min(curZ+0.2,3.3) : Math.max(curZ-0.2,-3.3),
    xanchor:"left", yanchor: curZ >= 0 ? "bottom" : "top",
    text:"Z: " + curZ.toFixed(2),
    font:{{color:zC, size:10, family:"monospace"}},
    bgcolor: zC + "22", borderpad:3, showarrow:false,
  }};

  var layout = Object.assign({{}}, LAYOUT_BASE, {{
    height:430,
    margin:{{t:8, b:36, l:62, r: hasPrice ? 65 : 12}},
    hovermode:"x unified", dragmode:"pan",
    hoverlabel:{{font:{{size:11}}, namelength:22}},
    legend:{{orientation:"h", x:0, y:1.02, font:{{size:10}}, bgcolor:"transparent"}},
    // Eixo X único — spike atravessa os dois painéis automaticamente
    xaxis: {{
      domain:[0,1], type:"date",
      gridcolor:"rgba(255,255,255,.05)", zeroline:false,
      showspikes:true, spikemode:"across", spikedash:"solid",
      spikethickness:0.5, spikecolor:"rgba(180,195,215,0.15)",
    }},
    // Painel superior (67% do altura)
    yaxis: Object.assign({{}}, LAYOUT_BASE.yaxis, {{
      domain:[0.33,1], anchor:"x",
      ticksuffix:"K", tickformat:".0f",
      range:[minV-pad, maxV+pad], fixedrange:false,
    }}),
    // Painel inferior Z-score (28% da altura) — yaxis2 independente, mesmo xaxis
    yaxis2: Object.assign({{}}, LAYOUT_BASE.yaxis, {{
      domain:[0,0.28], anchor:"x",
      range:[-3.5,3.5], fixedrange:false, tickformat:".0f",
      tickvals:[-2,-1,0,1,2], ticktext:["-2σ","-1σ","0","+1σ","+2σ"],
    }}),
    shapes:[
      {{type:"line",xref:"paper",yref:"y", x0:0,x1:1,y0:0,y1:0, line:{{color:"rgba(255,255,255,0.12)",width:1}}}},
      {{type:"line",xref:"paper",yref:"paper",x0:0,x1:1,y0:0.31,y1:0.31, line:{{color:"rgba(255,255,255,0.15)",width:1}}}},
      {{type:"rect",xref:"paper",yref:"y2",x0:0,x1:1,y0:2, y1:3.5, fillcolor:"rgba(244,63,94,0.06)",  line:{{width:0}}}},
      {{type:"rect",xref:"paper",yref:"y2",x0:0,x1:1,y0:-3.5,y1:-2,fillcolor:"rgba(16,185,129,0.06)", line:{{width:0}}}},
      {{type:"line",xref:"paper",yref:"y2",x0:0,x1:1,y0:2,  y1:2,  line:{{color:"rgba(244,63,94,0.8)",  width:1.2,dash:"dot"}}}},
      {{type:"line",xref:"paper",yref:"y2",x0:0,x1:1,y0:-2, y1:-2, line:{{color:"rgba(16,185,129,0.8)", width:1.2,dash:"dot"}}}},
      {{type:"line",xref:"paper",yref:"y2",x0:0,x1:1,y0:1,  y1:1,  line:{{color:"rgba(244,63,94,0.28)", width:0.8,dash:"dot"}}}},
      {{type:"line",xref:"paper",yref:"y2",x0:0,x1:1,y0:-1, y1:-1, line:{{color:"rgba(16,185,129,0.28)",width:0.8,dash:"dot"}}}},
      {{type:"line",xref:"paper",yref:"y2",x0:0,x1:1,y0:0,  y1:0,  line:{{color:"rgba(255,255,255,0.25)",width:1}}}},
    ],
    annotations:[
      {{xref:"paper",yref:"y2",x:0.01,y:2.1, xanchor:"left",yanchor:"bottom",text:"+2σ",font:{{color:"#f43f5e",size:9}},showarrow:false}},
      {{xref:"paper",yref:"y2",x:0.01,y:-2.1,xanchor:"left",yanchor:"top",   text:"-2σ",font:{{color:"#10b981",size:9}},showarrow:false}},
      {{xref:"paper",yref:"y2",x:0.01,y:1.08,xanchor:"left",yanchor:"bottom",text:"+1σ",font:{{color:"rgba(244,63,94,0.45)",size:8}},showarrow:false}},
      {{xref:"paper",yref:"y2",x:0.01,y:-1.08,xanchor:"left",yanchor:"top",  text:"-1σ",font:{{color:"rgba(16,185,129,0.45)",size:8}},showarrow:false}},
      zBadge,
    ],
  }});
  if (hasPrice) {{
    layout.yaxis3 = {{overlaying:"y",side:"right",showgrid:false,zeroline:false,
      tickformat:"~s",fixedrange:false,color:"rgba(203,213,225,0.4)"}};
  }}
  Plotly.newPlot(divId, traces, layout, CFG_Z);
}}

// ─── COT weekly micro-table (Long/Short/Net + variação + saldo acumulado) ─
// useAM=true → usa am_long/am_short/am_net (Non-Comercial) em vez de mm_* (Managed Money)
function renderCotWeeklyTable(key, weeks, useAM) {{
  var wrap = document.getElementById("cot-" + key + "-weekly-tbl");
  if (!wrap) return;
  var data = DATA.cot[key];
  var srcLong = useAM ? "am_long" : "mm_long", srcShort = useAM ? "am_short" : "mm_short", srcNet = useAM ? "am_net" : "mm_net";
  if (!data || !data[srcLong] || !data[srcLong].length) {{
    wrap.innerHTML = '<p style="color:#7d90a8;padding:8px;font-size:11px">Dados não disponíveis.</p>';
    return;
  }}
  var dates = data.dates, longs = data[srcLong], shorts = data[srcShort], net = data[srcNet];
  var n = dates.length;
  var deltas = net.map(function(v, i) {{ return (i === 0 || longs[i] === null || longs[i-1] === null) ? null : v - net[i-1]; }});
  var start = Math.max(0, n - weeks);
  var rows = [];
  var cum = 0;
  for (var i = start; i < n; i++) {{
    if (deltas[i] !== null) cum += deltas[i];
    rows.push({{date: dates[i], long: longs[i], short: shorts[i], net: net[i], delta: deltas[i], cum: cum}});
  }}
  rows.reverse();
  var fmt = function(v) {{ return (v === null || v === undefined) ? "—" : Math.round(v).toLocaleString("pt-BR"); }};
  var fmtSigned = function(v) {{ return (v === null || v === undefined) ? "—" : (v > 0 ? "+" : "") + Math.round(v).toLocaleString("pt-BR"); }};
  var deltaCls = function(v) {{ return v > 0 ? "delta-pos" : (v < 0 ? "delta-neg" : ""); }};
  var html = '<table><thead><tr><th>Data</th><th style="text-align:right">Long</th><th style="text-align:right">Short</th>'
    + '<th style="text-align:right">Net</th><th style="text-align:right">Δ Semana</th><th style="text-align:right">Saldo Acum.</th></tr></thead><tbody>';
  rows.forEach(function(r, idx) {{
    html += '<tr' + (idx === 0 ? ' class="cot-weekly-latest"' : '') + '>'
      + '<td>' + r.date + '</td>'
      + '<td style="text-align:right">' + fmt(r.long) + '</td>'
      + '<td style="text-align:right">' + fmt(r.short) + '</td>'
      + '<td style="text-align:right">' + fmt(r.net) + '</td>'
      + '<td style="text-align:right" class="' + deltaCls(r.delta) + '">' + fmtSigned(r.delta) + '</td>'
      + '<td style="text-align:right" class="' + deltaCls(r.cum) + '">' + fmtSigned(r.cum) + '</td>'
      + '</tr>';
  }});
  html += '</tbody></table>';
  wrap.innerHTML = html;
}}

document.addEventListener("click", function(e) {{
  var btn = e.target.closest(".period-toggle button");
  if (!btn) return;
  var group = btn.closest(".period-toggle");
  var key = group.getAttribute("data-cot-key");
  var useAM = group.getAttribute("data-use-am") === "1";
  group.querySelectorAll("button").forEach(function(b) {{ b.classList.remove("active"); }});
  btn.classList.add("active");
  renderCotWeeklyTable(key, parseInt(btn.getAttribute("data-weeks"), 10), useAM);
}});

// ─── BTC stats boxes ──────────────────────────────────────────────────
function renderBtcStats(stats) {{
  if (!stats) return;
  var boxes = [
    ["Último Halving", stats.halving_date],
    ["Dias desde Halving", stats.days_since_halving.toLocaleString()],
    ["Preço no Halving", "$ " + stats.price_at_halving.toLocaleString()],
    ["Preço Atual (BTC)", "$ " + stats.current_price.toLocaleString()],
    ["Retorno desde Halving", (stats.pct_from_halving >= 0 ? "+" : "") + stats.pct_from_halving + "%"],
    ["vs ATH", stats.pct_from_ath + "%"],
  ];
  var html = "";
  boxes.forEach(function(b) {{
    var color = b[0].includes("Retorno") || b[0].includes("ATH") ?
      (parseFloat(b[1]) >= 0 ? "#10b981" : "#f43f5e") : "#e8eef5";
    html += '<div class="stat-box"><div class="stat-lbl">' + b[0] + '</div><div class="stat-val" style="color:' + color + '">' + b[1] + '</div></div>';
  }});
  document.getElementById("btc-stats-boxes").innerHTML = html;
}}

// ─── BTC Production Cost (modelo Capriole) ─────────────────────────────
var BTC_HALVING_DATES = ["2012-11-28","2016-07-09","2020-05-11","2024-04-20"];

function renderBtcProdCostStats(data) {{
  var el = document.getElementById("btc-prodcost-stats");
  if (!data || !data.dates || !data.dates.length) {{ el.innerHTML = ''; return; }}
  var n = data.dates.length;
  var price = data.price[n-1], elec = data.elec[n-1], prod = data.prod[n-1],
      margin = data.margin[n-1], hash = data.hashEH[n-1];
  var eff = data.meta ? data.meta.last_eff_jth : null;
  var marginColor = margin >= 0 ? "#10b981" : "#f43f5e";
  var fmtUsd = function(v) {{ return "$ " + Math.round(v).toLocaleString("pt-BR"); }};
  var boxes = [
    ["Preço Atual (BTC)", fmtUsd(price), "#e8eef5"],
    ["Custo Elétrico (piso)", fmtUsd(elec), "#00bfff"],
    ["Custo Total (Produção)", fmtUsd(prod), "#e8eef5"],
    ["Margem vs. Custo Elétrico", (margin >= 0 ? "+" : "") + margin.toFixed(1) + "%", marginColor],
    ["Hashrate da Rede", hash.toFixed(1) + " EH/s", "#e8eef5"],
    ["Eficiência Implícita (Fleet)", (eff !== null ? eff.toFixed(1) : "—") + " J/TH", "#e8eef5"],
  ];
  var html = "";
  boxes.forEach(function(b) {{
    html += '<div class="stat-box"><div class="stat-lbl">' + b[0] + '</div><div class="stat-val" style="color:' + b[2] + '">' + b[1] + '</div></div>';
  }});
  el.innerHTML = html;
}}

function btcProdCostChart(divId, data) {{
  if (!data || !data.dates || !data.dates.length) {{
    document.getElementById(divId).innerHTML = '<p style="color:#7d90a8;padding:20px;text-align:center">Aguardando dados — clique em Atualizar.</p>';
    return;
  }}
  var traces = [
    {{ type:"scatter", mode:"lines", name:"Preço BTC", x:data.dates, y:data.price,
       line:{{color:"#c9a227", width:2}}, hovertemplate:"<b>%{{x}}</b><br>Preço: $%{{y:,.0f}}<extra></extra>" }},
    {{ type:"scatter", mode:"lines", name:"Custo Elétrico (piso)", x:data.dates, y:data.elec,
       line:{{color:"#00bfff", width:2}}, hovertemplate:"<b>%{{x}}</b><br>Custo elétrico: $%{{y:,.0f}}<extra></extra>" }},
  ];
  var shapes = BTC_HALVING_DATES
    .filter(function(d) {{ return d >= data.dates[0]; }})
    .map(function(d) {{
      return {{ type:"line", x0:d, x1:d, y0:0, y1:1, yref:"paper",
                line:{{color:"rgba(245,158,11,.35)", width:1, dash:"dot"}} }};
    }});
  var layout = Object.assign({{}}, LAYOUT_BASE, {{
    margin:{{ t:14, b:40, l:64, r:20 }},
    yaxis: Object.assign({{}}, LAYOUT_BASE.yaxis, {{ type:"log", title:"USD (log)" }}),
    shapes: shapes,
    hovermode:"x unified",
    legend:{{ x:0.01, y:0.98, bgcolor:"rgba(0,0,0,0.3)", font:{{color:"#e8eef5",size:11}} }},
  }});
  Plotly.newPlot(divId, traces, layout, CFG_Z);
}}

// ─── Embed data ───────────────────────────────────────────────────────
var DATA = {{
  cpi:    {kw['cpi_hist']},
  ccpi:   {kw['ccpi_hist']},
  ipcaBr: {kw['ipca_hist']},
  saz: {{
    sp500: {_saz_js('mercados','S&P 500')},
    ibov:  {_saz_js('mercados','IBOVESPA')},
    ewz:   {_saz_js('mercados','EWZ')},
    vix:   {_saz_js('mercados','VIX')},
    dxy:   {_saz_js('mercados','DXY')},
    wti:   {_saz_js('energia','Petróleo WTI')},
    gas:   {_saz_js('energia','Gás Natural')},
    ouro:  {_saz_js('metais','Ouro')},
    prata: {_saz_js('metais','Prata')},
    cobre: {_saz_js('metais','Cobre')},
    milho: {_saz_js('agricola','Milho')},
    trigo: {_saz_js('agricola','Trigo')},
    soja:  {_saz_js('agricola','Soja')},
    bcom:  {_saz_js('agricola','BBG Commodity')},
  }},
  cot: {{
    ouro:   {_cot_js('ouro')},
    prata:  {_cot_js('prata')},
    cobre:  {_cot_js('cobre')},
    wti:    {_cot_js('wti')},
    gasnat: {_cot_js('gasnat')},
    dxy:    {_cot_js('dxy')},
    sp500:  {_cot_js('sp500')},
    vix:    {_cot_js('vix')},
    btc:    {_cot_js('btc')},
    milho:  {_cot_js('milho')},
    trigo:  {_cot_js('trigo')},
    soja:   {_cot_js('soja')},
    bcom:   {_cot_js('bcom')},
  }},
  btcSaz:   {kw['btc_saz']},
  btcCycle: {kw['btc_cycle']},
  btcStats: {kw['btc_stats']},
  btcProdCost: {kw.get('btc_prodcost','null')},
  nfpFP:    {kw['nfp_fp_json']},
  wageGrowth: {kw['wage_json']},
}};

// ─── Render function ──────────────────────────────────────────────────
function renderCharts(tab) {{
  if (tab === "macro") {{
    cpiLineChart("ch-cpi",  DATA.cpi,  "#f43f5e", "CPI YoY");
    cpiLineChart("ch-ccpi", DATA.ccpi, "#f59e0b", "Core CPI YoY");
    ipcaLineChart("ch-ipca", DATA.ipcaBr);
    nfpBarChart("ch-nfp-fp", DATA.nfpFP);
    wageGrowthChart("ch-wage-growth", DATA.wageGrowth);
  }} else if (tab === "saz-mercados") {{
    barChart("ch-saz-sp500", DATA.saz.sp500);
    barChart("ch-saz-dxy",   DATA.saz.dxy);
    barChart("ch-saz-vix",   DATA.saz.vix);
    barChart("ch-saz-ewz",   DATA.saz.ewz);
    barChart("ch-saz-ibov",  DATA.saz.ibov);
    cotPanel("ch-cot-dxy",   "ch-cot-dxy-zlbl",   DATA.cot.dxy,   "Asset Managers");
    cotPanel("ch-cot-sp500", "ch-cot-sp500-zlbl", DATA.cot.sp500, "Asset Managers");
    cotPanel("ch-cot-vix",   "ch-cot-vix-zlbl",   DATA.cot.vix,   "Asset Managers");
    renderCotWeeklyTable("dxy", 12);
    renderCotWeeklyTable("sp500", 12);
    renderCotWeeklyTable("vix", 12);
  }} else if (tab === "saz-energia") {{
    barChart("ch-saz-wti",  DATA.saz.wti);
    barChart("ch-saz-gas",  DATA.saz.gas);
    barChart("ch-saz-ouro", DATA.saz.ouro);
    barChart("ch-saz-prata",DATA.saz.prata);
    barChart("ch-saz-cobre",DATA.saz.cobre);
    cotPanel("ch-cot-ouro",   "ch-cot-ouro-zlbl",   DATA.cot.ouro);
    cotPanel("ch-cot-prata",  "ch-cot-prata-zlbl",  DATA.cot.prata);
    cotPanel("ch-cot-cobre",  "ch-cot-cobre-zlbl",  DATA.cot.cobre);
    cotPanel("ch-cot-wti",    "ch-cot-wti-zlbl",    DATA.cot.wti);
    cotPanel("ch-cot-gasnat", "ch-cot-gasnat-zlbl", DATA.cot.gasnat);
    renderCotWeeklyTable("ouro", 12);
    renderCotWeeklyTable("prata", 12);
    renderCotWeeklyTable("cobre", 12);
    renderCotWeeklyTable("wti", 12);
    renderCotWeeklyTable("gasnat", 12);
  }} else if (tab === "saz-agricola") {{
    barChart("ch-saz-milho", DATA.saz.milho);
    barChart("ch-saz-trigo", DATA.saz.trigo);
    barChart("ch-saz-soja",  DATA.saz.soja);
    barChart("ch-saz-bcom",  DATA.saz.bcom);
    cotPanel("ch-cot-milho", "ch-cot-milho-zlbl", DATA.cot.milho);
    cotPanel("ch-cot-trigo", "ch-cot-trigo-zlbl", DATA.cot.trigo);
    cotPanel("ch-cot-soja",  "ch-cot-soja-zlbl",  DATA.cot.soja);
    cotPanel("ch-cot-bcom",  "ch-cot-bcom-zlbl",  DATA.cot.bcom, "Asset Managers");
    renderCotWeeklyTable("milho", 12);
    renderCotWeeklyTable("trigo", 12);
    renderCotWeeklyTable("soja", 12);
    renderCotWeeklyTable("bcom", 12);
  }} else if (tab === "bitcoin") {{
    renderBtcStats(DATA.btcStats);
    btcCycleChart(DATA.btcCycle);
    barChart("ch-btc-saz", DATA.btcSaz);
    cotPanel("ch-cot-btc", "ch-cot-btc-zlbl", DATA.cot.btc, "Asset Managers");
    renderCotWeeklyTable("btc", 12);
    renderBtcProdCostStats(DATA.btcProdCost);
    btcProdCostChart("ch-btc-prodcost", DATA.btcProdCost);
  }}
}}

// ─── Update trigger ───────────────────────────────────────────────────
function triggerUpdate() {{
  fetch("/api/update", {{method:"POST"}})
    .then(r => r.json())
    .then(d => {{
      if (d.status === "started") alert("Atualização iniciada! Aguarde ~60s e recarregue a página.");
      else alert("Pipeline já em execução. Aguarde.");
    }});
}}

// ─── NTN-B yields — Investidor10 / Tesouro Direto ────────────────────
(function() {{
  var IDS = {{"2035":"ntnb-2035","2050":"ntnb-2050","2060":"ntnb-2060"}};

  function rateColor(r) {{
    return r >= 9 ? "#f43f5e" : (r >= 8 ? "#f59e0b" : (r >= 7.5 ? "#c9a227" : "#10b981"));
  }}
  function deltaArrow(d) {{
    if (d === null || d === undefined) return "";
    var sign = d > 0 ? "▲" : (d < 0 ? "▼" : "—");
    var color = d > 0 ? "#f43f5e" : (d < 0 ? "#10b981" : "#64748b");
    var val = Math.abs(d).toFixed(2);
    return '<span style="color:' + color + '">' + sign + ' ' + val + ' pp hoje</span>';
  }}
  function histLine(label, val) {{
    if (val === null || val === undefined) return "";
    var sign = val > 0 ? "+" : "";
    var color = val > 0 ? "rgba(244,63,94,.8)" : "rgba(16,185,129,.8)";
    return label + ': <span style="color:' + color + '">' + sign + val.toFixed(2) + '</span>  ';
  }}

  fetch("/api/ntnb-yields")
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
      if (data.error) throw new Error(data.error);
      Object.keys(IDS).forEach(function(yr) {{
        var info = data[yr];
        var baseId = IDS[yr];
        if (!info) return;
        var rate = typeof info === "object" ? info.rate : info;

        // Taxa principal
        var el = document.getElementById(baseId);
        if (el) {{
          el.textContent = rate.toFixed(2) + "%";
          el.style.color = rateColor(rate);
        }}
        // Variação diária
        var d1El = document.getElementById(baseId + "-d1");
        if (d1El) d1El.innerHTML = typeof info === "object" ? deltaArrow(info.d1) : "";
        // Histórico sutil
        var histEl = document.getElementById(baseId + "-hist");
        if (histEl && typeof info === "object") {{
          var lines = "";
          lines += histLine("1s", info.w1);
          lines += histLine("1m", info.m1);
          lines += histLine("2m", info.m2);
          histEl.innerHTML = lines || '<span style="color:var(--muted)">acumulados em breve</span>';
        }}
      }});
    }})
    .catch(function() {{
      Object.values(IDS).forEach(function(id) {{
        var el = document.getElementById(id);
        if (el) {{ el.textContent = "N/D"; el.style.color = "#64748b"; el.style.fontSize = "18px"; }}
      }});
    }});
}})();

// ─── Eleições 2026 — Odds de Mercado ─────────────────────────────────
(function() {{
  function renderElections(data) {{
    var box = document.getElementById("pm-box");
    var src = document.getElementById("pm-source-tag");
    if (!box) return;

    if (data.error) {{
      box.innerHTML = '<div style="font-size:11px;color:var(--muted);padding:8px 0">Odds indisponíveis nesta rede.<br><span style="font-size:10px">Ver pesquisa Datafolha abaixo.</span></div>';
      if (src) src.textContent = "indisponível";
      return;
    }}

    var outcomes = (data.outcomes || []).slice().sort(function(a,b){{return b.price-a.price;}});
    var html = '<div style="display:flex;flex-direction:column;gap:10px">';
    outcomes.forEach(function(o) {{
      var pct = Math.round((o.price||0)*100);
      var name = (o.name||"—").replace(/\bWins?\b/i,"").replace(/\b2026\b/,"").trim();
      html += _candidateCard(name, pct, pct>=50?"#10b981":(pct>=35?"#f59e0b":"#f43f5e"));
    }});
    html += '</div>';
    if (data.updated || data.cached) {{
      html += '<div style="font-size:10px;color:var(--muted);margin-top:10px">';
      if (data.cached) html += '⚠ cache · ';
      html += (data.updated||"") + '</div>';
    }}
    box.innerHTML = html;
    if (src) src.textContent = "↻ " + (data.source||"Mercado");
  }}

  function _candidateCard(name, pct, color) {{
    var bar = Math.min(100, Math.max(0, pct));
    return [
      '<div style="background:var(--surface);border:1px solid var(--border);border-left:3px solid '+color+';border-radius:7px;padding:9px 12px;margin-bottom:7px">',
      '<div style="display:flex;align-items:baseline;justify-content:space-between">',
      '<span style="font-size:12px;font-weight:600;color:var(--text)">' + name + '</span>',
      '<span style="font-size:26px;font-weight:800;color:'+color+';line-height:1">' + pct + '%</span>',
      '</div>',
      '<div style="background:rgba(255,255,255,.07);border-radius:3px;height:3px;margin-top:5px">',
      '<div style="width:'+bar+'%;height:100%;background:'+color+';border-radius:3px;transition:.4s"></div>',
      '</div>',
      '</div>'
    ].join("");
  }}

  function tryBrowserDirect() {{
    fetch("https://gamma-api.polymarket.com/events?q=Brazil+2026+president&limit=5")
      .then(function(r) {{ return r.json(); }})
      .then(function(events) {{
        if (!Array.isArray(events) || !events.length) throw new Error("vazio");
        var ev = events[0];
        var outcomes = (ev.markets||[]).map(function(m) {{
          return {{ name: m.groupItemTitle||m.title||"", price: parseFloat(m.lastTradePrice||m.bestAsk||m.price||0) }};
        }}).filter(function(o){{ return o.name; }});
        renderElections({{ source:"Polymarket", market_name:ev.title, outcomes:outcomes, updated:new Date().toLocaleString("pt-BR") }});
      }})
      .catch(function() {{
        renderElections({{error:true}});
      }});
  }}

  fetch("/api/polymarket/brazil2026")
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
      if (data.error) {{ tryBrowserDirect(); return; }}
      renderElections(data);
    }})
    .catch(function() {{ tryBrowserDirect(); }});
}})();

// ─── Initial render (all tabs pre-rendered) ───────────────────────────
window._rendered = {{}};
["macro","saz-mercados","saz-energia","saz-agricola","bitcoin"].forEach(function(id) {{
  window._rendered[id] = true;
  renderCharts(id);
}});
</script>
</body>
</html>"""
