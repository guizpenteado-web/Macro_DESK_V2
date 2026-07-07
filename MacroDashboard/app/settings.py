import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

_cfg_path = BASE_DIR / "config.json"
_cfg = json.loads(_cfg_path.read_text(encoding="utf-8")) if _cfg_path.exists() else {}

FRED_API_KEY       = _cfg.get("fred_api_key", "")
SERVER_PORT        = int(_cfg.get("server_port", 8002))
DATABASE_PATH      = BASE_DIR / "database" / "macro.db"
BANK_DATA_PATH     = BASE_DIR / "data" / "bank_projections.json"
DASHBOARD_PATH     = BASE_DIR / "dashboard" / "index.html"

SEASONALITY_TICKERS = {
    "mercados": {
        "S&P 500":  "^GSPC",
        "IBOVESPA": "^BVSP",
        "EWZ":      "EWZ",              # iShares MSCI Brazil ETF (USD-traded)
        "VIX":      "^VIX",
        "DXY":      "DX-Y.NYB",
    },
    "energia": {
        "Petróleo WTI": "CL=F",
        "Gás Natural":  "NG=F",         # futuros front-month NYMEX — igual metodologia Seasonax
    },
    "metais": {
        "Ouro":  "GC=F",                # COMEX gold futures — roll < 0.1%, adequado para sazonalidade
        "Prata": "SI=F",                # COMEX silver futures — idem
        "Cobre": "PCOPPUSDM",           # IMF Global Copper Price (FRED) — preco cash
    },
    "agricola": {
        "Milho":           "ZC=F",
        "Trigo":           "PWHEAMTUSDM",   # IMF Global Wheat cash price (FRED)
        "Soja":            "ZS=F",
        "BBG Commodity":   "^BCOM",         # Bloomberg Commodity Index (CBOT futures)
    },
}

# Series do FRED que nao sao tickers yfinance — coletados via CSV endpoint
FRED_TICKERS = {
    "MHHNGSP":     "Gas Natural (Henry Hub spot)",
    "PWHEAMTUSDM": "Trigo (IMF Global Wheat)",
    "PCOPPUSDM":   "Cobre (IMF Global Price USD/mt)",
}

# Contratos CFTC para COT (Disaggregated Futures Only) — metais, energia, agricola
# Listas incluem aliases pré-2015: CFTC renomeou vários contratos ao longo dos anos.
COT_CONTRACTS = {
    "ouro":   ["GOLD - COMMODITY EXCHANGE INC."],
    "prata":  ["SILVER - COMMODITY EXCHANGE INC."],
    "cobre":  ["COPPER- #1 - COMMODITY EXCHANGE INC.",
               "COPPER-GRADE #1 - COMMODITY EXCHANGE INC."],   # nome pre-2015
    "wti":    ["WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE",           # nome pós-2022 (NYMEX CL, ~2M OI)
               "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE"],  # nome pré-2022 (NYMEX CL, ~2M OI)
    "gasnat": ["NAT GAS NYME - NEW YORK MERCANTILE EXCHANGE",    # nome pós-2022 (CFTC renomeou)
               "NATURAL GAS - NEW YORK MERCANTILE EXCHANGE"],   # nome pré-2022 — mesmo contrato 023651 (10k MMBTU)
    "milho":  ["CORN - CHICAGO BOARD OF TRADE"],
    "trigo":  ["WHEAT-SRW - CHICAGO BOARD OF TRADE",
               "WHEAT - CHICAGO BOARD OF TRADE"],                   # nome pre-2013 (antes do split SRW/HRW)
    "soja":   ["SOYBEANS - CHICAGO BOARD OF TRADE"],
}

# Contratos CFTC para COT TFF (Traders in Financial Futures) — financeiros
# Listas de nomes alternativos: o CFTC renomeou vários contratos ao longo dos anos.
# Todos os nomes mapeiam para a mesma key no banco.
COT_CONTRACTS_TFF = {
    "dxy":   ["USD INDEX - ICE FUTURES U.S.",
              "U.S. DOLLAR INDEX - ICE FUTURES U.S."],        # nome pre-2022
    "sp500": ["E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE",
              "E-MINI S&P 500 STOCK INDEX - CHICAGO MERCANTILE EXCHANGE"],  # nome pre-2022
    "vix":   ["VIX FUTURES - CBOE FUTURES EXCHANGE"],
    "btc":   ["BITCOIN - CHICAGO MERCANTILE EXCHANGE"],
    "bcom":  ["BBG COMMODITY - CHICAGO BOARD OF TRADE"],      # Bloomberg Commodity Index (TFF, 2022+)
}

BTC_TICKER = "BTC-USD"

BTC_HALVINGS = [
    {"date": "2012-11-28", "label": "1º Halving"},
    {"date": "2016-07-09", "label": "2º Halving"},
    {"date": "2020-05-11", "label": "3º Halving"},
    {"date": "2024-04-19", "label": "4º Halving"},
]

SEASONALITY_YEARS = 20
