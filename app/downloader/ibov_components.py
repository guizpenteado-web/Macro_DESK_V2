"""
Download da composição atual do IBOVESPA.
Fonte primária: API B3 | Fallback: lista local.

Adaptado do padrão usado em Market_BREADTH_ULTRA/app/downloader/ibov_components.py
(cópia própria — este projeto não importa do outro módulo).
"""
from __future__ import annotations
import base64
import json
from typing import Optional

import requests

from app.database.connection import get_session
from app.database.repository import AssetRepository
from app.utils.logger import logger

_B3_API = (
    "https://sistemaswebb3-listados.b3.com.br"
    "/indexProxy/indexCall/GetPortfolioDay/{token}"
)

_FALLBACK: list[str] = [
    "ABEV3", "ALOS3", "ASAI3", "AURE3", "AXIA3", "AZZA3",
    "B3SA3", "BBAS3", "BBDC3", "BBDC4", "BBSE3", "BEEF3", "BPAC11",
    "BRAP4", "BRAV3", "BRKM5", "CEAB3", "CMIG4", "CMIN3", "COGN3",
    "CPFE3", "CPLE3", "CSAN3", "CSMG3", "CSNA3", "CURY3", "CXSE3",
    "CYRE3", "DIRR3", "EGIE3", "EMBJ3", "ENEV3", "ENGI11", "EQTL3",
    "FLRY3", "GGBR4", "GOAU4", "HAPV3", "HYPE3", "IGTI11", "ISAE4",
    "ITSA4", "ITUB4", "KLBN11", "LREN3", "MBRF3", "MGLU3", "MOTV3",
    "MRVE3", "MULT3", "NATU3", "PETR3", "PETR4", "POMO4", "PRIO3",
    "PSSA3", "RADL3", "RAIL3", "RDOR3", "RECV3", "RENT3", "SANB11",
    "SBSP3", "SLCE3", "SMFT3", "SUZB3", "TAEE11", "TIMS3", "TOTS3",
    "UGPA3", "USIM5", "VALE3", "VAMO3", "VBBR3", "VIVA3", "VIVT3",
    "WEGE3", "YDUQ3",
]


def _b3_token() -> str:
    p = {"language": "pt-br", "pageNumber": 1, "pageSize": 120, "index": "IBOV", "segment": "1"}
    return base64.b64encode(json.dumps(p, separators=(",", ":")).encode()).decode()


def _fetch_from_b3() -> Optional[list[dict]]:
    try:
        r = requests.get(
            _B3_API.format(token=_b3_token()),
            headers={"User-Agent": "Mozilla/5.0"}, timeout=20,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return None
        return [
            {
                "ticker": i["cod"].strip(),
                "name": i.get("asset", "").strip(),
                "weight": float(str(i.get("part", "0") or "0").replace(",", ".")),
            }
            for i in results
        ]
    except Exception as e:
        logger.warning(f"B3 API indisponivel: {e}")
        return None


def fetch_ibov_components() -> list[dict]:
    c = _fetch_from_b3()
    if c:
        logger.info(f"B3 API: {len(c)} ativos")
        return c
    logger.info(f"Fallback local: {len(_FALLBACK)} ativos")
    return [{"ticker": t, "name": "", "weight": 0.0} for t in _FALLBACK]


def sync_components() -> int:
    components = fetch_ibov_components()
    with get_session() as s:
        repo = AssetRepository(s)
        repo.deactivate_all()
        for c in components:
            repo.upsert(ticker=c["ticker"], name=c.get("name", ""), weight=c.get("weight", 0.0))
    logger.success(f"Componentes sincronizados: {len(components)} ativos")
    return len(components)
