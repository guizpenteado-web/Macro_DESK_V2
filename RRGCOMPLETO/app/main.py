"""
RRGCOMPLETO — Rotação Relativa vs IBOV, universo expandido (IBOV + TODOS os
membros de qualquer sub-índice setorial B3, ~155 ativos — não só os ~78 do
IBOV). Variante do RRG_Dashboard original (ver [[project_rrg_dashboard]]).

Rotas:
  GET  /                  — frontend (matriz)
  GET  /api/matrix        — payload completo (ativos, setores, métricas semanais)
  POST /api/collect/trigger — dispara pipeline (universo + preços + cálculo) em background
  GET  /api/status        — estado do pipeline
"""
from __future__ import annotations

import threading
from datetime import datetime
from statistics import mean

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.config.settings import settings
from app.database.connection import get_session, init_database
from app.database.repository import (
    AssetRepository, PriceRepository, SectorComponentRepository, WeeklyMetricRepository,
)
from app.calc.sector_index import sector_ticker
from app.downloader.price_downloader import IBOV_TICKER
from app.downloader.sector_components import SECTOR_LABELS
from app.utils.logger import logger

app = FastAPI(title="RRGCOMPLETO — Rotação Relativa (universo expandido)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_state: dict = {"running": False, "step": "", "last_update": None, "error": None}


def _run_pipeline() -> None:
    global _state
    _state["running"] = True
    _state["error"] = None
    steps = [
        ("Sincronizando setores (sub-índices B3)...", _step_sectors),
        ("Sincronizando universo completo (IBOV + setores)...", _step_universe),
        ("Baixando preços (incremental)...", _step_prices),
        ("Calculando RS-Ratio / Momentum / Score...", _step_calc),
        ("Construindo índices sintéticos de setor...", _step_sector_composites),
        ("Calculando RS-Ratio / Momentum dos setores...", _step_sector_calc),
    ]
    try:
        for label, fn in steps:
            _state["step"] = label
            logger.info(label)
            fn()
        _state["last_update"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        _state["step"] = "Concluído"
        logger.success("Pipeline concluído.")
    except Exception as exc:
        _state["error"] = str(exc)
        _state["step"] = "Erro"
        logger.error(f"Pipeline falhou: {exc}")
    finally:
        _state["running"] = False


def _step_universe():
    from app.downloader.universe import sync_universe
    sync_universe()


def _step_sectors():
    from app.downloader.sector_components import sync_sector_components
    sync_sector_components()


def _step_prices():
    from app.downloader.price_downloader import update_prices
    update_prices()


def _step_calc():
    from app.calc.rrg_engine import compute_all
    compute_all()


def _step_sector_composites():
    from app.calc.sector_index import build_all_sector_composites
    build_all_sector_composites()


def _step_sector_calc():
    from app.calc.sector_index import compute_sector_metrics
    compute_sector_metrics()


def _avg_daily_value(ticker: str) -> float:
    """Volume financeiro médio (R$) dos últimos ~20 pregões — proxy de liquidez."""
    with get_session() as s:
        recent = PriceRepository(s).get_recent(ticker, 20)
    values = [p.close * p.volume for p in recent if p.close and p.volume]
    return round(mean(values), 2) if values else 0.0


@app.get("/")
def index():
    if not settings.frontend_path.exists():
        return JSONResponse({"error": "Frontend não encontrado."}, status_code=503)
    return FileResponse(settings.frontend_path, media_type="text/html")


@app.get("/api/matrix")
def get_matrix():
    with get_session() as s:
        assets = AssetRepository(s).get_all()
        sectors_by_ticker = SectorComponentRepository(s).get_sectors_by_ticker()
        metrics = WeeklyMetricRepository(s).get_all()

    by_ticker: dict[str, list[dict]] = {}
    all_weeks: set[str] = set()
    for m in metrics:
        wk = m.week_ending.isoformat()
        all_weeks.add(wk)
        by_ticker.setdefault(m.ticker, []).append({
            "week_ending": wk,
            "close": m.close,
            "weekly_return": m.weekly_return,
            "ibov_weekly_return": m.ibov_weekly_return,
            "rs_ratio": m.rs_ratio,
            "rs_momentum": m.rs_momentum,
            "quadrant": m.quadrant,
            "rotation_score": m.rotation_score,
        })

    out_assets = []
    for a in assets:
        weekly = by_ticker.get(a.ticker, [])
        if not weekly:
            continue  # sem histórico suficiente ainda (ex: IPO recente)
        out_assets.append({
            "ticker": a.ticker,
            "name": a.name or "",
            "weight": a.weight or 0.0,
            "is_ibov": bool(a.is_ibov),
            "sectors": sectors_by_ticker.get(a.ticker, []),
            "avg_daily_value": _avg_daily_value(a.ticker),
            "weekly": sorted(weekly, key=lambda r: r["week_ending"]),
        })

    # Índices sintéticos de setor — variante experimental (ver app/calc/sector_index.py):
    # cada setor tratado como "ativo" próprio, mesma metodologia RRG, vs IBOV.
    out_sectors = []
    for code, label in SECTOR_LABELS.items():
        weekly = by_ticker.get(sector_ticker(code), [])
        if not weekly:
            continue
        out_sectors.append({
            "code": code,
            "name": label,
            "weekly": sorted(weekly, key=lambda r: r["week_ending"]),
        })

    return {
        "generated_at": datetime.now().isoformat(),
        "benchmark": IBOV_TICKER,
        "weeks_available": sorted(all_weeks),
        "sector_labels": SECTOR_LABELS,
        "assets": out_assets,
        "sector_indices": out_sectors,
    }


@app.post("/api/collect/trigger")
def trigger_update():
    if _state["running"]:
        return {"status": "already_running", "step": _state["step"]}
    t = threading.Thread(target=_run_pipeline, daemon=True)
    t.start()
    return {"status": "started"}


@app.get("/api/status")
def get_status():
    return _state


def _start_scheduler() -> None:
    from apscheduler.schedulers.background import BackgroundScheduler
    hour, minute = (int(x) for x in settings.scheduler_time.split(":"))
    scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")
    scheduler.add_job(_run_pipeline, "cron", hour=hour, minute=minute)
    scheduler.start()
    logger.info(f"Scheduler iniciado — coleta diária às {settings.scheduler_time} BRT.")


if __name__ == "__main__":
    init_database()
    _start_scheduler()
    logger.info(f"RRG Dashboard iniciado em http://localhost:{settings.port}")
    uvicorn.run(app, host="127.0.0.1", port=settings.port, log_level="warning")
