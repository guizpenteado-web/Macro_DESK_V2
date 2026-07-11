import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import alerts, assets, buybacks, funds, insiders, performance, rankings
from app.services.scheduler_jobs import start_scheduler

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    _scheduler = start_scheduler(settings.schedule_tz)
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


@app.get("/api/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=settings.backend_port, log_level="info")
