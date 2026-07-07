"""
Sincroniza as composicoes de todos os indices B3 usados no dashboard.

Indices de SETOR (tabelas de ativos):
  IFNC, IEEX, IMOB, ICON, IMAT, UTIL, SMALL — via API B3

Indices de AMPLITUDE (grafico comparativo):
  IDIV, IBLV — via API B3
  EWZ        — hardcoded (ETF americano, fora da API B3)

A API B3 e a fonte de verdade: composicao sempre atualizada.
"""
from __future__ import annotations
import base64
import json
import requests

from app.database.connection import get_session
from app.database.repository import IndexComponentRepository
from app.utils.logger import logger

# Indices de setor — buscados da API B3
# B3 usa "SMLL" para o Indice Small Cap (nao "SMALL")
SECTOR_CODES: list[str] = ["IFNC", "IEEX", "IMOB", "ICON", "IMAT", "UTIL", "SMLL", "INDX", "IDIV", "IBLV"]
SECTOR_DISPLAY: dict[str, str] = {"SMLL": "SMALL"}  # alias para exibicao

# Indices de amplitude — buscados da API B3 + EWZ hardcoded (IDIV/IBLV movidos para SECTOR_CODES)
AMPLITUDE_CODES: list[str] = []

# EWZ — iShares MSCI Brazil ETF (componentes BR, posicao Jun/2025)
_EWZ_TICKERS: list[str] = [
    "VALE3","PETR4","ITUB4","BBDC4","B3SA3","ABEV3","WEGE3","SUZB3",
    "EQTL3","RDOR3","RENT3","HAPV3","GGBR4","BBAS3","PRIO3","ITSA4",
    "BPAC11","RAIL3","MULT3","ENEV3","ENGI11","KLBN11","BBSE3","SANB11",
    "LREN3","SBSP3","UGPA3","CMIG4","VBBR3","CPFE3","TAEE11","EGIE3",
    "PETR3","CSNA3","USIM5","SLCE3","AZZA3","CSAN3","ASAI3","BRAV3",
]

# Fallbacks locais por se a API B3 falhar
_FALLBACKS: dict[str, list[str]] = {
    "IFNC": ["AXIA3","B3SA3","BBAS3","BBDC3","BBDC4","BBSE3","BPAC11",
             "BRAP4","CXSE3","IRBR3","ITSA4","ITUB4","PSSA3","SANB11"],
    "IEEX": ["AURE3","CEAB3","CMIG4","CPFE3","CPLE3","EGIE3","ENEV3",
             "ENGI11","EQTL3","ISAE4","TAEE11"],
    "IMOB": ["ALOS3","CURY3","CYRE3","DIRR3","IGTI11","MRVE3","MULT3","SMFT3"],
    "ICON": ["ABEV3","ASAI3","AZZA3","BEEF3","CSAN3","HYPE3","LREN3",
             "MGLU3","NATU3","RADL3","RENT3","SLCE3","UGPA3","VBBR3","VIVA3","YDUQ3"],
    "IMAT": ["BRAV3","BRKM5","CMIN3","CSNA3","GGBR4","GOAU4","KLBN11",
             "PETR3","PETR4","PRIO3","RECV3","SUZB3","USIM5","VALE3"],
    "UTIL": ["CSMG3","SBSP3"],
    "SMLL": ["COGN3","FLRY3","HAPV3","MOTV3","RDOR3","CURY3","DIRR3","SMFT3",
             "ALOS3","CYRE3","IGTI11","MRVE3","CEAB3","AURE3","RECV3","POMO4",
             "VAMO3","EMBJ3","TOTS3","MOTV3"],
    "INDX": ["WEGE3","RAIL3","EMBR3","EMBJ3","TGMA3","CMIN3","POMO4","VAMO3",
             "ROMI3","FRAS3","AGRO3","CSNA3","GGBR4","GOAU4","USIM5","BRKM5"],
    "IDIV": ["BBAS3","BBDC3","BBDC4","BEEF3","CMIG4","CPFE3","EGIE3","ENGI11",
             "EQTL3","ISAE4","ITSA4","ITUB4","KLBN11","PETR3","PETR4","PSSA3",
             "SANB11","TAEE11","TIMS3","VALE3","VIVT3","BBSE3","CSMG3","WEGE3"],
    "IBLV": ["ABEV3","AURE3","BBSE3","CMIG4","CPFE3","CPLE3","CSMG3","CXSE3",
             "EGIE3","ENGI11","EQTL3","ISAE4","ITSA4","KLBN11","PSSA3","SBSP3",
             "TAEE11","TIMS3","VIVT3","WEGE3"],
}


def _b3_url(index_code: str) -> str:
    params = {
        "language": "pt-br",
        "pageNumber": 1,
        "pageSize": 200,   # amplo para capturar indices grandes como SMALL
        "index": index_code,
        "segment": "1",
    }
    encoded = base64.b64encode(
        json.dumps(params, separators=(",", ":")).encode()
    ).decode()
    return (
        "https://sistemaswebb3-listados.b3.com.br"
        f"/indexProxy/indexCall/GetPortfolioDay/{encoded}"
    )


def _fetch_b3(index_code: str) -> list[tuple[str, float]]:
    """Busca composicao de um indice B3. Retorna [(ticker, weight), ...]."""
    try:
        resp = requests.get(_b3_url(index_code), timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            raise ValueError("API retornou lista vazia")
        components = [
            (c["cod"], float(c.get("part", "0").replace(",", ".")))
            for c in results
            if c.get("cod")
        ]
        logger.info(f"{index_code}: {len(components)} componentes (API B3)")
        return components
    except Exception as exc:
        logger.warning(f"B3 API falhou para {index_code}: {exc} — usando fallback")
        fb = [(t, 0.0) for t in _FALLBACKS.get(index_code, [])]
        logger.info(f"{index_code}: {len(fb)} componentes (fallback)")
        return fb


def sync_index_components() -> dict[str, int]:
    """
    Busca composicoes atualizadas de todos os indices na API B3 e persiste.
    Retorna {index_code: n_componentes}.
    """
    all_codes = SECTOR_CODES + AMPLITUDE_CODES

    totals: dict[str, int] = {}
    for code in all_codes:
        components = _fetch_b3(code)
        rows = [{"index_code": code, "ticker": t, "weight": w} for t, w in components]
        with get_session() as s:
            IndexComponentRepository(s).replace_index(code, rows)
        totals[code] = len(rows)

    # EWZ hardcoded
    ewz_rows = [{"index_code": "EWZ", "ticker": t, "weight": 0.0} for t in _EWZ_TICKERS]
    with get_session() as s:
        IndexComponentRepository(s).replace_index("EWZ", ewz_rows)
    totals["EWZ"] = len(ewz_rows)
    logger.info(f"EWZ: {len(ewz_rows)} componentes (hardcoded)")

    logger.success(f"Indices sincronizados: {totals}")
    return totals


def get_all_index_tickers() -> list[str]:
    """Todos os tickers unicos em qualquer indice."""
    with get_session() as s:
        return IndexComponentRepository(s).get_all_tickers()


def get_sector_tickers() -> list[str]:
    """Tickers dos indices de setor (para tabelas de ativos)."""
    with get_session() as s:
        from app.database.models import IndexComponent
        from sqlalchemy import select
        rows = s.execute(
            select(IndexComponent.ticker)
            .where(IndexComponent.index_code.in_(SECTOR_CODES))
            .distinct()
        ).scalars().all()
        return list(rows)
