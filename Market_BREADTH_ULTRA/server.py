"""
Servidor local do IBOV Market Breadth.
Acesso: http://localhost:8001

Rotas:
  GET  /           — dashboard HTML
  POST /api/update — dispara o pipeline de atualização em background
  GET  /api/status — estado atual do pipeline
"""
from __future__ import annotations
import threading
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from app.config.settings import settings
from app.utils.logger import logger

app = FastAPI(title="IBOV Market Breadth")

# init_database() so rodava dentro de `if __name__ == "__main__"` (linha
# ~169), mas o Hub sobe este servico via `uvicorn server:app` (import como
# modulo), que nunca executa esse bloco — o banco nunca era criado (achado
# 13/07/2026: "no such table: assets" na primeira atualizacao real depois
# do fix do settings.py). Chamando aqui, em import-time, garante que roda
# nos dois modos de execucao (import pelo uvicorn ou `python server.py`).
from app.database.connection import init_database
init_database()

_state: dict = {
    "running": False,
    "step": "",
    "last_update": None,
    "error": None,
}

DASHBOARD_FILE = settings.dashboard_output


def _run_pipeline() -> None:
    global _state
    _state["running"] = True
    _state["error"] = None

    steps = [
        ("Sincronizando componentes do IBOVESPA...", _step_components),
        ("Baixando precos (incremental)...",         _step_prices),
        ("Atualizando indice IBOVESPA...",           _step_ibov),
        ("Calculando indicadores e breadth...",      _step_indicators),
        ("Sincronizando sub-indices...",             _step_index_components),
        ("Baixando precos dos sub-indices...",       _step_index_prices),
        ("Calculando breadth dos sub-indices...",    _step_index_breadth),
        ("Gerando dashboard...",                     _step_dashboard),
        ("Gerando relatorio Excel...",               _step_report),
    ]

    try:
        for label, fn in steps:
            _state["step"] = label
            logger.info(label)
            fn()
        _state["last_update"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        _state["step"] = "Concluido"
        logger.success("Pipeline concluido.")
    except Exception as exc:
        _state["error"] = str(exc)
        _state["step"] = "Erro"
        logger.error(f"Pipeline falhou: {exc}")
    finally:
        _state["running"] = False


def _step_components():
    from app.downloader.ibov_components import sync_components
    sync_components()


def _step_prices():
    from app.downloader.price_downloader import update_prices
    update_prices()


def _step_ibov():
    import yfinance as yf, pandas as pd
    from app.database.connection import get_session
    from app.database.repository import PriceRepository
    from datetime import date, timedelta
    with get_session() as s:
        last = PriceRepository(s).get_latest_date("IBOV")
    start = (last + timedelta(days=1)).isoformat() if last else "2020-01-01"
    if start > date.today().isoformat():
        return
    df = yf.download("^BVSP", start=start, progress=False, auto_adjust=True)
    if df.empty:
        return
    if hasattr(df.columns, "get_level_values"):
        df.columns = df.columns.get_level_values(0)
    rows = []
    for idx, row in df.iterrows():
        d = idx.date() if hasattr(idx, "date") else idx
        c = float(row.get("Close", 0) or 0)
        if c <= 0:
            continue
        rows.append({"ticker":"IBOV","date":d,"close":c,"open":None,"high":None,
                     "low":None,"volume":None,"adj_close":c})
    if rows:
        with get_session() as s:
            PriceRepository(s).bulk_upsert(rows)


def _step_indicators():
    from app.indicators.calculator import calculate_indicators
    calculate_indicators()


def _step_index_components():
    from app.downloader.index_components import sync_index_components
    sync_index_components()


def _step_index_prices():
    from app.downloader.index_components import get_all_index_tickers
    from app.downloader.price_downloader import update_prices
    tickers = get_all_index_tickers()
    if tickers:
        update_prices(tickers)


def _step_index_breadth():
    from app.indicators.calculator import calculate_index_breadth
    calculate_index_breadth()


def _step_dashboard():
    from app.dashboard.html_generator import generate_dashboard
    generate_dashboard()


def _step_report():
    from app.reports.excel_report import generate_report
    generate_report()


# ── Rotas ────────────────────────────────────────────────────────

@app.get("/")
def index():
    if not DASHBOARD_FILE.exists():
        return JSONResponse({"error": "Dashboard nao gerado ainda. POST /api/update"}, 503)
    return FileResponse(DASHBOARD_FILE, media_type="text/html")


@app.post("/api/update")
def trigger_update():
    if _state["running"]:
        return {"status": "already_running", "step": _state["step"]}
    t = threading.Thread(target=_run_pipeline, daemon=True)
    t.start()
    return {"status": "started"}


@app.get("/api/status")
def get_status():
    return {
        "running":     _state["running"],
        "step":        _state["step"],
        "last_update": _state["last_update"],
        "error":       _state["error"],
    }


# ── Entry point ──────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Servidor iniciado em http://localhost:8001")
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")
