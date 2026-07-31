import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import SessionLocal
from app.routers import alerts, assets, buybacks, favorites, funds, insiders, market, performance, portfolio, rankings
from app.services.scheduler_jobs import start_scheduler

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_scheduler = None


def _warm_caches() -> None:
    """O processo inteiro (Hub unificado, unified_server.py) reinicia com
    frequencia (deploys de qualquer sub-app, nao so SmartMoneyBR) — cada
    restart zera os caches TTL em memoria de top-performers/flow-evolution
    (performance.py) e do set has_equity (funds.py), expondo o PRIMEIRO
    usuario real depois de cada restart ao custo frio (9-16s Top20/Evolucao,
    ~0,6s Fundos). Roda numa thread separada pra nao atrasar o healthcheck/
    startup do app — se um usuario real bater no endpoint antes dessa thread
    terminar, ele so cai no mesmo caminho frio de sempre (nao quebra nada)."""
    t0 = time.time()
    db = SessionLocal()
    try:
        funds._has_equity_fund_ids(db)
        performance._top_performers_cache[(20, 20)] = (time.time(), performance._compute_top_performers(20, 20, db))
        performance._flow_evolution_cache["data"] = performance._compute_flow_evolution(db)
        performance._flow_evolution_cache["ts"] = time.time()
        logger.info("cache warmup concluido em %.1fs", time.time() - t0)
    except Exception:
        logger.exception("cache warmup falhou (nao critico, endpoints ainda funcionam sob demanda)")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    _scheduler = start_scheduler(settings.schedule_tz)
    threading.Thread(target=_warm_caches, daemon=True).start()
    yield
    if _scheduler:
        _scheduler.shutdown(wait=False)


app = FastAPI(title="SmartMoneyBR API", version="0.1.0", lifespan=lifespan)

# Normalmente o browser nunca chama esta API cross-origin: o Next.js
# (next.config.ts) reescreve /smartmoney/api/* pra ca no proprio servidor.
# Origens abaixo sao so um fallback pra acesso direto/debug (porta 3100
# solta, Hub em :8000, dominio publico ngrok do Hub).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3100",
        "http://localhost:8000",
        "https://jawed-sermon-extras.ngrok-free.dev",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(funds.router)
app.include_router(assets.router)
# performance.router must come before rankings.router: it defines the static
# path /api/rankings/top-performers, and rankings.router's /api/rankings/{kind}
# is a catch-all that would otherwise intercept it first (FastAPI matches in
# registration order).
app.include_router(performance.router)
app.include_router(rankings.router)
app.include_router(buybacks.router)
app.include_router(insiders.router)
app.include_router(alerts.router)
app.include_router(market.router)
app.include_router(favorites.router)
app.include_router(portfolio.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=settings.backend_port, log_level="info")
