"""
Sincroniza a composição dos sub-índices setoriais da B3, usados aqui como
proxy de "setor" para o filtro do RRG Dashboard (decisão confirmada com o
usuário — não existe uma taxonomia de setor "limpa" disponível no momento).

Inclui também IDIV/IBLV (índices de fator — dividendos / baixa volatilidade,
não setor "de verdade") a pedido explícito do usuário, como mais duas opções
de filtro além dos sub-índices setoriais.

Adaptado do padrão em Market_BREADTH_ULTRA/app/downloader/index_components.py
(cópia própria — este projeto não importa do outro módulo).
"""
from __future__ import annotations
import base64
import json

import requests

from app.database.connection import get_session
from app.database.repository import AssetRepository, SectorComponentRepository
from app.utils.logger import logger

SECTOR_CODES: list[str] = ["IFNC", "IEEX", "IMOB", "ICON", "IMAT", "UTIL", "SMLL", "INDX", "IDIV", "IBLV"]

# "TODOS" não vem da API B3 — é a união dinâmica de todo o universo de ativos
# (ver sync_sector_components), sempre o último botão da lista no frontend.
CURATED_CODES: list[str] = ["TODOS"]

SECTOR_LABELS: dict[str, str] = {
    "IFNC": "Financeiro",
    "IEEX": "Energia Elétrica",
    "IMOB": "Imobiliário",
    "ICON": "Consumo",
    "IMAT": "Materiais Básicos",
    "UTIL": "Utilidade Pública",
    "SMLL": "Small Caps",
    "INDX": "Industrial",
    "IDIV": "Dividendos",
    "IBLV": "Baixa Volatilidade",
    "TODOS": "Todos os Ativos",
}

# Ativos cuja Classificação Setorial B3 real é "Petróleo, Gás e Biocombustíveis"
# — não tem índice tradeable B3 próprio. A pedido explícito do usuário
# (07/jul/2026), em vez de manter uma aba "PETRO" separada, esses ativos
# foram unidos ao IMAT. Os de "Transporte" (RAIL3, MOTV3, ECOR3, HBSA3,
# JSLG3, TGMA3) NÃO entram aqui — ficam só na aba "TODOS".
_IMAT_EXTRA: list[str] = [
    "PETR3", "PETR4", "PRIO3", "RECV3", "BRAV3", "UGPA3", "VBBR3", "CSAN3",  # Petróleo e Gás
]

# Fallbacks locais caso a API B3 falhe
_FALLBACKS: dict[str, list[str]] = {
    "IFNC": ["AXIA3", "B3SA3", "BBAS3", "BBDC3", "BBDC4", "BBSE3", "BPAC11",
             "BRAP4", "CXSE3", "IRBR3", "ITSA4", "ITUB4", "PSSA3", "SANB11"],
    "IEEX": ["AURE3", "CEAB3", "CMIG4", "CPFE3", "CPLE3", "EGIE3", "ENEV3",
             "ENGI11", "EQTL3", "ISAE4", "TAEE11"],
    "IMOB": ["ALOS3", "CURY3", "CYRE3", "DIRR3", "IGTI11", "MRVE3", "MULT3", "SMFT3"],
    "ICON": ["ABEV3", "ASAI3", "AZZA3", "BEEF3", "CSAN3", "HYPE3", "LREN3",
             "MGLU3", "NATU3", "RADL3", "RENT3", "SLCE3", "UGPA3", "VBBR3", "VIVA3", "YDUQ3"],
    "IMAT": ["BRAV3", "BRKM5", "CMIN3", "CSNA3", "GGBR4", "GOAU4", "KLBN11",
             "PETR3", "PETR4", "PRIO3", "RECV3", "SUZB3", "USIM5", "VALE3"],
    "UTIL": ["CSMG3", "SBSP3"],
    "SMLL": ["COGN3", "FLRY3", "HAPV3", "MOTV3", "RDOR3", "CURY3", "DIRR3", "SMFT3",
             "ALOS3", "CYRE3", "IGTI11", "MRVE3", "CEAB3", "AURE3", "RECV3", "POMO4",
             "VAMO3", "TOTS3"],
    "INDX": ["WEGE3", "RAIL3", "CMIN3", "POMO4", "VAMO3",
             "CSNA3", "GGBR4", "GOAU4", "USIM5", "BRKM5"],
    "IDIV": ["BBAS3", "BBDC3", "BBDC4", "BEEF3", "CMIG4", "CPFE3", "EGIE3", "ENGI11",
             "EQTL3", "ISAE4", "ITSA4", "ITUB4", "KLBN11", "PETR3", "PETR4", "PSSA3",
             "SANB11", "TAEE11", "TIMS3", "VALE3", "VIVT3", "BBSE3", "CSMG3", "WEGE3"],
    "IBLV": ["ABEV3", "AURE3", "BBSE3", "CMIG4", "CPFE3", "CPLE3", "CSMG3", "CXSE3",
             "EGIE3", "ENGI11", "EQTL3", "ISAE4", "ITSA4", "KLBN11", "PSSA3", "SBSP3",
             "TAEE11", "TIMS3", "VIVT3", "WEGE3"],
}


def _b3_url(index_code: str) -> str:
    params = {
        "language": "pt-br",
        "pageNumber": 1,
        "pageSize": 200,
        "index": index_code,
        "segment": "1",
    }
    encoded = base64.b64encode(json.dumps(params, separators=(",", ":")).encode()).decode()
    return f"https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/{encoded}"


def _fetch_b3(index_code: str) -> list[str]:
    try:
        resp = requests.get(_b3_url(index_code), headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            raise ValueError("API retornou lista vazia")
        tickers = [c["cod"].strip() for c in results if c.get("cod")]
        logger.info(f"{index_code}: {len(tickers)} componentes (API B3)")
        return tickers
    except Exception as exc:
        logger.warning(f"B3 API falhou para {index_code}: {exc} — usando fallback")
        fb = _FALLBACKS.get(index_code, [])
        logger.info(f"{index_code}: {len(fb)} componentes (fallback)")
        return fb


def sync_sector_components() -> dict[str, int]:
    totals: dict[str, int] = {}
    for code in SECTOR_CODES:
        tickers = _fetch_b3(code)
        if code == "IMAT":
            tickers = sorted(set(tickers) | set(_IMAT_EXTRA))
            logger.info(f"IMAT: +{len(_IMAT_EXTRA)} ativos de Petróleo/Gás e Transporte unidos manualmente")
        with get_session() as s:
            SectorComponentRepository(s).replace_sector(code, tickers)
        totals[code] = len(tickers)
    logger.success(f"Setores sincronizados: {totals}")
    return totals


def sync_todos_sector() -> int:
    """"TODOS" — união dinâmica de todo o universo de ativos ativos no banco.

    Precisa rodar DEPOIS de sync_universe() (Asset já populado), por isso é um
    passo próprio no pipeline em vez de ficar dentro de sync_sector_components().
    """
    with get_session() as s:
        all_tickers = sorted(AssetRepository(s).get_active_tickers())
        SectorComponentRepository(s).replace_sector("TODOS", all_tickers)
    logger.info(f"TODOS: {len(all_tickers)} componentes (união de todo o universo)")
    return len(all_tickers)
