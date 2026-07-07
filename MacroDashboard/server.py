"""
Macro Dashboard — servidor FastAPI.

http://localhost:8002
"""
from __future__ import annotations
import threading, time, logging
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
import requests as _requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from app.settings import SERVER_PORT, DASHBOARD_PATH
from app.pipeline import run_pipeline

log = logging.getLogger(__name__)

_status = {"running": False, "last_run": None, "error": None}


def _bg_pipeline():
    _status["running"] = True
    _status["error"] = None
    try:
        run_pipeline()
        _status["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
        log.info("Pipeline OK — %s", _status["last_run"])
    except Exception as e:
        _status["error"] = str(e)
        log.error("Pipeline ERRO: %s", e)
    finally:
        _status["running"] = False


@asynccontextmanager
async def lifespan(app):
    if not DASHBOARD_PATH.exists():
        log.info("Dashboard não encontrado — gerando agora...")
        t = threading.Thread(target=_bg_pipeline, daemon=True)
        t.start()
    else:
        log.info("Dashboard existente em %s", DASHBOARD_PATH)

    # APScheduler: 07:00 e 16:00 horário de Brasília
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        sched = BackgroundScheduler(timezone="America/Sao_Paulo")
        sched.add_job(_bg_pipeline, "cron", hour=7,  minute=0, id="macro_morning")
        sched.add_job(_bg_pipeline, "cron", hour=16, minute=0, id="macro_afternoon")
        sched.start()
        log.info("Scheduler configurado: pipeline às 07:00 e 16:00 BRT")
    except Exception as e:
        log.warning("APScheduler não disponível: %s", e)

    yield


app = FastAPI(title="Macro Dashboard", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def index():
    headers = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}
    if DASHBOARD_PATH.exists():
        return HTMLResponse(DASHBOARD_PATH.read_text(encoding="utf-8"), headers=headers)
    return HTMLResponse("""
    <html><body style="background:#080c14;color:#e8eef5;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column;gap:16px">
      <h2 style="color:#c9a227">Gerando Dashboard...</h2>
      <p style="color:#7d90a8">Coletando dados (BLS + yfinance). Aguarde ~60 segundos e recarregue.</p>
      <script>setTimeout(()=>location.reload(),8000)</script>
    </body></html>
    """)


@app.post("/api/update")
def trigger_update():
    if _status["running"]:
        return JSONResponse({"status": "already_running"})
    t = threading.Thread(target=_bg_pipeline, daemon=True)
    t.start()
    return JSONResponse({"status": "started"})


@app.get("/api/status")
def get_status():
    return JSONResponse(_status)


_NTNB_CACHE: dict = {"data": None, "ts": 0}
_NTNB_HISTORY_FILE = Path(__file__).parent / "data" / "ntnb_history.json"


def _scrape_inv10_ntnb() -> dict:
    """Scrapa taxas NTN-B 2035/2050/2060 + variação diária do Investidor10."""
    import re
    from curl_cffi import requests as curl_req
    resp = curl_req.get(
        "https://investidor10.com.br/tesouro-direto/",
        impersonate="chrome",
        timeout=20,
        headers={"Accept-Language": "pt-BR,pt;q=0.9"},
    )
    resp.raise_for_status()
    text = resp.text
    TARGET_YEARS = {2035, 2050, 2060}
    result: dict = {}
    seen: set = set()
    for m in re.finditer(r'data-order="([\d.]+)"', text):
        rate = float(m.group(1))
        raw_block = text[m.end():m.end() + 1200]
        if "IPCA" not in raw_block:
            continue
        clean = re.sub(r"<[^>]+>", " ", raw_block)
        clean = re.sub(r"\s+", " ", clean).strip()
        date_match = re.search(r"(\d{2}/\d{2}/(\d{4}))", clean)
        if not date_match:
            continue
        year = int(date_match.group(2))
        if year not in TARGET_YEARS or year in seen:
            continue
        # tenta extrair variação diária (ex: "+0,04" ou "-0,12")
        delta_match = re.search(r"([+-]?\d+[,\.]\d+)\s*pp", clean[:300])
        daily_delta = None
        if delta_match:
            try:
                daily_delta = float(delta_match.group(1).replace(",", "."))
            except ValueError:
                pass
        seen.add(year)
        result[year] = {"rate": rate, "delta_d": daily_delta}
        if len(seen) == len(TARGET_YEARS):
            break
    return result


def _load_ntnb_history() -> list:
    try:
        if _NTNB_HISTORY_FILE.exists():
            import json as _json
            return _json.loads(_NTNB_HISTORY_FILE.read_text())
    except Exception:
        pass
    return []


def _save_ntnb_snapshot(rates: dict) -> None:
    try:
        import json as _json
        history = _load_ntnb_history()
        snapshot = {"ts": datetime.now(timezone.utc).isoformat(), "rates": {str(k): v["rate"] for k, v in rates.items()}}
        history.append(snapshot)
        # manter max 120 snapshots (aprox 2 meses de leituras diárias)
        history = history[-120:]
        _NTNB_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        _NTNB_HISTORY_FILE.write_text(_json.dumps(history, indent=2))
    except Exception as e:
        log.warning("ntnb history save erro: %s", e)


def _get_hist_rate(history: list, year: int, days_ago: int) -> float | None:
    """Busca a taxa mais próxima de N dias atrás no histórico."""
    import json as _json
    target_ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
    best = None
    best_diff = float("inf")
    for snap in history:
        try:
            snap_ts = datetime.fromisoformat(snap["ts"]).replace(tzinfo=timezone.utc) if snap["ts"].endswith("Z") or "+" not in snap["ts"][10:] else datetime.fromisoformat(snap["ts"])
            diff = abs((snap_ts - target_ts).total_seconds())
            if diff < best_diff:
                rates = snap.get("rates", {})
                v = rates.get(str(year))
                if v is not None:
                    best_diff = diff
                    best = float(v)
        except Exception:
            continue
    # só retorna se o snapshot estiver dentro de uma janela razoável
    max_window = days_ago * 86400 * 0.4 + 86400  # ±40% + 1 dia
    return best if best_diff < max_window else None


@app.get("/api/ntnb-yields")
def ntnb_yields():
    """Retorna taxas NTN-B 2035/2050/2060 com deltas históricos (cache 20 min)."""
    now = time.time()
    if _NTNB_CACHE["data"] and (now - _NTNB_CACHE["ts"]) < 1200:
        return JSONResponse(_NTNB_CACHE["data"])
    try:
        scraped = _scrape_inv10_ntnb()
        if not scraped:
            if _NTNB_CACHE["data"]:
                return JSONResponse(_NTNB_CACHE["data"])
            return JSONResponse({"error": "Nenhum título NTN-B encontrado"})

        _save_ntnb_snapshot(scraped)
        history = _load_ntnb_history()

        result: dict = {}
        for year, data in scraped.items():
            rate = data["rate"]
            deltas: dict = {}
            # delta_d: diferença entre hoje e ontem (~1 dia atrás)
            h1 = _get_hist_rate(history, year, 1)
            if h1 and h1 != rate:
                deltas["d1"] = round(rate - h1, 3)
            elif data.get("delta_d") is not None:
                deltas["d1"] = data["delta_d"]
            # 1 semana
            h7 = _get_hist_rate(history, year, 7)
            if h7:
                deltas["w1"] = round(rate - h7, 3)
            # 1 mês
            h30 = _get_hist_rate(history, year, 30)
            if h30:
                deltas["m1"] = round(rate - h30, 3)
            # 2 meses
            h60 = _get_hist_rate(history, year, 60)
            if h60:
                deltas["m2"] = round(rate - h60, 3)
            result[str(year)] = {"rate": rate, **deltas}

        _NTNB_CACHE["data"] = result
        _NTNB_CACHE["ts"] = now
        return JSONResponse(result)
    except Exception as e:
        log.error("ntnb-yields erro: %s", e)
        if _NTNB_CACHE["data"]:
            return JSONResponse(_NTNB_CACHE["data"])
        return JSONResponse({"error": str(e)}, status_code=502)


def _parse_polymarket_events(events: list) -> dict | None:
    if not isinstance(events, list) or not events:
        return None
    target = None
    for ev in events:
        title = (ev.get("title") or ev.get("name") or "").lower()
        if any(k in title for k in ["brazil", "brasil", "lula", "bolsonaro"]):
            target = ev
            break
    if not target and events:
        target = events[0]
    if not target:
        return None
    markets = target.get("markets", [])
    outcomes = []
    for m in markets:
        name = m.get("groupItemTitle") or m.get("title") or ""
        try:
            price = float(m.get("lastTradePrice") or m.get("bestAsk") or m.get("price") or 0)
        except (TypeError, ValueError):
            price = 0.0
        if name:
            outcomes.append({"name": name, "price": price})
    if not outcomes:
        return None
    return {
        "source": "Polymarket",
        "market_name": target.get("title") or target.get("name") or "Brasil 2026",
        "outcomes": outcomes,
        "updated": datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC"),
    }


def _try_manifold() -> dict | None:
    """Tenta buscar odds de eleições brasileiras no Manifold Markets."""
    from curl_cffi import requests as curl_req
    try:
        r = curl_req.get(
            "https://api.manifold.markets/v0/search-markets?term=brazil+president+2026&limit=8",
            impersonate="chrome", timeout=10,
        )
        r.raise_for_status()
        markets = r.json()
        if not isinstance(markets, list):
            return None
        target = None
        for m in markets:
            q = (m.get("question") or "").lower()
            if any(k in q for k in ["brazil", "brasil", "lula", "bolsonaro", "presidential"]):
                target = m
                break
        if not target and markets:
            target = markets[0]
        if not target:
            return None
        # Manifold: probability field + answers for multi-choice
        answers = target.get("answers") or []
        outcomes = []
        if answers:
            for a in answers:
                outcomes.append({
                    "name": a.get("text", ""),
                    "price": float(a.get("probability", 0)),
                })
        else:
            prob = target.get("probability", 0)
            q = target.get("question", "")
            outcomes = [{"name": q, "price": float(prob)}, {"name": "Não", "price": 1 - float(prob)}]
        if not outcomes:
            return None
        return {
            "source": "Manifold Markets",
            "market_name": target.get("question") or "Brasil 2026",
            "outcomes": outcomes,
            "updated": datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC"),
        }
    except Exception:
        return None


_ELECTIONS_CACHE: dict = {"data": None, "ts": 0}


@app.get("/api/polymarket/brazil2026")
def polymarket_brazil():
    """Probabilidades eleitorais — tenta Polymarket, depois Manifold Markets."""
    now = time.time()
    if _ELECTIONS_CACHE["data"] and (now - _ELECTIONS_CACHE["ts"]) < 1800:
        return JSONResponse(_ELECTIONS_CACHE["data"])
    try:
        from curl_cffi import requests as curl_req
        resp = curl_req.get(
            "https://gamma-api.polymarket.com/events?q=Brazil+2026+president&limit=10",
            impersonate="chrome",
            timeout=12,
        )
        resp.raise_for_status()
        events = resp.json()
        if not isinstance(events, list):
            events = events.get("events", [])

        target_event = None
        result = _parse_polymarket_events(resp.json())
        if result:
            _ELECTIONS_CACHE["data"] = result
            _ELECTIONS_CACHE["ts"] = now
            return JSONResponse(result)
        raise ValueError("Nenhum evento encontrado no Polymarket")
    except Exception as e:
        log.warning("polymarket falhou (%s) — tentando Manifold...", e)
        manifold = _try_manifold()
        if manifold:
            _ELECTIONS_CACHE["data"] = manifold
            _ELECTIONS_CACHE["ts"] = now
            return JSONResponse(manifold)
        if _ELECTIONS_CACHE["data"]:
            cached = dict(_ELECTIONS_CACHE["data"])
            cached["cached"] = True
            return JSONResponse(cached)
        return JSONResponse({"error": "Fontes de predição de mercado indisponíveis nesta rede"}, status_code=503)


if __name__ == "__main__":
    print()
    print("  ╔══════════════════════════════════════╗")
    print("  ║        Macro Dashboard v1.0          ║")
    print("  ╠══════════════════════════════════════╣")
    print(f"  ║  http://localhost:{SERVER_PORT}              ║")
    print("  ╚══════════════════════════════════════╝")
    print()
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT, log_level="info")
