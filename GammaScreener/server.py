import concurrent.futures
import os
import threading
import time
import traceback
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

import oplab_client
import b3_oi_client
import history_store
from gex_engine import build_gex_payload, flatten_legs_from_oi

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")

DEFAULT_TICKER = "BOVA11"
DEFAULT_ROOT = "BOVA"

# Filtro de qualidade do mercado de GEX, substituindo o corte fixo por rank
# de OI (validado em 03/ago/2026 contra os 168 ativos classificaveis do
# universo -- ver memoria do projeto). Rank de OI sozinho deixa passar
# ativos com mercado de opcoes degenerado: ex. CVCB3 tinha OI alto (rank 39)
# mas IV implicita de 169% e so R$3mi/dia no papel-base -- sinal classico de
# preco de opcao sem negociacao real por tras. RAIZ4/ONCO3/PCAR3/MILS3/HBOR3
# tinham OI decente mas iv_current=0 (OpLab sem cotacao viva de opcao), caso
# em que o motor de GEX cairia no fallback de IV fixa (17.5%) e fabricaria
# um numero. Um ativo so entra na lista se passar em TODOS os criterios:
CANDIDATE_POOL_SIZE = 200      # avalia todo o universo classificavel real (~168) antes do filtro
MIN_ACTIVE_STRIKES = 30        # profundidade minima de cadeia p/ sweep +-30% confiavel (via B3, sem custo de API)
MIN_OI_TOTAL = 1_000_000       # piso de OI agregado (via B3, sem custo de API)
MIN_FINANCIAL_VOLUME = 10_000_000  # liquidez minima do papel-base, R$/dia (via OpLab)
# iv_current > 0 (cotacao viva de opcao na OpLab) tambem e exigido, checado
# direto em _passes_quality_filter -- sem constante numerica, e booleano.

OI_TTL_SECONDS = 2 * 60 * 60  # pedido do usuario 03/ago/2026 (era 6h)
ASSET_TTL_SECONDS = 5 * 60    # spot/IV mudam intraday
SCREENER_TTL_SECONDS = 5 * 60

_oi_cache = {"index": None, "ref_date": None, "fetched_at": 0}
_asset_cache = {}  # ticker -> {"payload":..., "fetched_at":...}
_screener_cache = {"payload": None, "fetched_at": 0}


def _get_oi_index(force=False):
    """Busca (e indexa) o arquivo de OI da B3 no maximo 1x por TTL -- NUNCA por ativo.

    O arquivo tem ~10MB; baixar de novo pra cada um dos 30 ativos do
    screener derrubou o tempo de resposta pra mais de 1 minuto e chegou a
    estourar timeout no servidor da B3. Cache local resolve.
    """
    now = time.time()
    if force or _oi_cache["index"] is None or now - _oi_cache["fetched_at"] > OI_TTL_SECONDS:
        data, ref_date = b3_oi_client.fetch_latest_oi()
        index = b3_oi_client.build_root_index(data)
        _oi_cache.update(index=index, ref_date=ref_date, fetched_at=now)
    return _oi_cache["index"], _oi_cache["ref_date"]


def _compute_asset_payload(ticker, root, oi_index, ref_date):
    stock = oplab_client.get_stock(ticker)
    spot = stock.get("bid") or stock.get("close")
    iv = (stock.get("iv_current") or 17.5) / 100.0

    oi_legs_raw = b3_oi_client.extract_legs_from_index(oi_index, root)
    legs = flatten_legs_from_oi(oi_legs_raw, ref_date)
    note = (
        f"Peso de posicionamento = Open Interest OFICIAL da B3, referente ao "
        f"fechamento de {ref_date.strftime('%d/%m/%Y')} (arquivo publico "
        f"'Posicoes em Aberto' da B3 -- defasagem normal de D-1/D-2, mesma "
        f"pratica de qualquer ferramenta de GEX, inclusive nos EUA). Spot e "
        f"volatilidade implicita usados sao os atuais (ao vivo, OpLab); so o "
        f"posicionamento (OI) e do ultimo fechamento disponivel."
    )
    payload = build_gex_payload(spot, iv, legs, note, weight_label="Open Interest")
    payload["symbol"] = ticker
    payload["root"] = root
    payload["name"] = stock.get("name")
    payload["source_label"] = f"Open Interest oficial B3 ({ref_date.strftime('%d/%m/%Y')})"
    payload["oi_reference_date"] = ref_date.strftime("%Y-%m-%d")
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    # Campos usados pelo filtro de qualidade do screener (_passes_quality_filter)
    payload["financial_volume"] = stock.get("financial_volume") or 0
    payload["iv_current_raw"] = stock.get("iv_current") or 0

    # Registra o ponto de hoje no historico com IV real (ao vivo) -- so o
    # backfill do passado usa proxy de volatilidade realizada. Upsert por
    # (ticker, ref_date): reescreve o mesmo dia varias vezes ao longo do
    # pregao sem criar linha duplicada. Nunca deve derrubar o calculo do
    # cockpit por causa de um problema no SQLite.
    try:
        history_store.upsert_snapshot(
            ticker=ticker, root=root, ref_date=payload["oi_reference_date"],
            gamma_flip=payload["gamma_flip"], spot=spot, regime=payload["regime"],
            iv_source="oplab_live", computed_at=payload["updated_at"],
        )
    except Exception:
        traceback.print_exc()

    return payload


def _get_asset_payload(ticker, root, oi_index, ref_date, force=False):
    now = time.time()
    entry = _asset_cache.get(ticker)
    if force or entry is None or now - entry["fetched_at"] > ASSET_TTL_SECONDS:
        payload = _compute_asset_payload(ticker, root, oi_index, ref_date)
        entry = {"payload": payload, "fetched_at": now}
        _asset_cache[ticker] = entry
    return entry["payload"]


@app.route("/api/gex")
def api_gex():
    force = request.args.get("force") == "1"
    ticker = request.args.get("ticker", DEFAULT_TICKER)
    root = request.args.get("root", DEFAULT_ROOT)
    try:
        oi_index, ref_date = _get_oi_index(force=force)
        return jsonify(_get_asset_payload(ticker, root, oi_index, ref_date, force=force))
    except Exception as e:
        traceback.print_exc()
        entry = _asset_cache.get(ticker)
        if entry is not None:
            stale = dict(entry["payload"])
            stale["fetch_error"] = str(e)
            return jsonify(stale)
        return jsonify({"error": str(e)}), 502


def _row_for_asset(asset, oi_index, ref_date, force):
    try:
        p = _get_asset_payload(asset["ticker"], asset["root"], oi_index, ref_date, force=force)
        return {
            "ticker": asset["ticker"],
            "root": asset["root"],
            "name": asset["name"],
            "spot": p["spot"],
            "gamma_flip": p["gamma_flip"],
            "distance_pct": ((p["gamma_flip"] / p["spot"] - 1) * 100) if p["gamma_flip"] else None,
            "regime": p["regime"],
            "gex_net_total": p["gex_net_total"],
            "oi_total": asset["oi_total"],
            "n_active_strikes": asset["n_active_strikes"],
            "financial_volume": p["financial_volume"],
            "iv_current": p["iv_current_raw"],
        }
    except Exception as asset_err:
        traceback.print_exc()
        return {"ticker": asset["ticker"], "root": asset["root"], "name": asset["name"],
                "error": str(asset_err)}


def _passes_quality_filter(row):
    """Segunda etapa do filtro (depende de dado da OpLab, ja calculado em
    _row_for_asset). Ver constantes no topo do arquivo pro racional de cada
    criterio."""
    if "error" in row:
        return False
    return (
        (row.get("iv_current") or 0) > 0
        and (row.get("financial_volume") or 0) >= MIN_FINANCIAL_VOLUME
    )


def _refresh_screener(force=False):
    """Recalcula o screener inteiro com filtro de qualidade em 2 etapas:

    1) Pre-filtro barato (OI total + numero de strikes ativos), calculado
       direto do arquivo da B3 sem nenhuma chamada de API -- descarta a
       maior parte dos candidatos claramente ilíquidos antes de gastar
       requisicao na OpLab.
    2) Filtro caro (IV implicita viva + volume financeiro do papel-base),
       que so roda pros sobreviventes da etapa 1. As chamadas por ativo na
       OpLab sao a parte lenta (I/O de rede) -- paralelizadas com thread
       pool, senao dezenas de ativos x ~300-500ms cada vira 15-25s+ de
       espera. O arquivo de OI da B3 continua buscado 1x so (dentro de
       _get_oi_index, TTL proprio), nunca por ativo.

    Achado em 03/ago/2026: rank de OI puro deixava passar ativos com mercado
    de opcoes degenerado (IV implicita absurda por falta de negociacao real,
    ou nenhuma cotacao viva de opcao) -- ver constantes no topo do arquivo.
    """
    oi_index, ref_date = _get_oi_index(force=force)
    candidates = b3_oi_client.build_universe(oi_index, top_n=CANDIDATE_POOL_SIZE)
    for c in candidates:
        c["n_active_strikes"] = b3_oi_client.count_active_strikes(oi_index, c["root"])
    prefiltered = [
        c for c in candidates
        if c["oi_total"] >= MIN_OI_TOTAL and c["n_active_strikes"] >= MIN_ACTIVE_STRIKES
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(
            lambda asset: _row_for_asset(asset, oi_index, ref_date, force), prefiltered
        ))
    kept_rows = [r for r in rows if _passes_quality_filter(r)]
    kept_rows.sort(key=lambda r: -(r.get("oi_total") or 0))
    payload = {
        "rows": kept_rows,
        "oi_reference_date": ref_date.strftime("%Y-%m-%d"),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "universe_candidates": len(candidates),
        "universe_prefiltered": len(prefiltered),
        "universe_kept": len(kept_rows),
    }
    _screener_cache["payload"] = payload
    _screener_cache["fetched_at"] = time.time()
    return payload


@app.route("/api/screener")
def api_screener():
    force = request.args.get("force") == "1"
    now = time.time()
    if force or _screener_cache["payload"] is None or now - _screener_cache["fetched_at"] > SCREENER_TTL_SECONDS:
        try:
            return jsonify(_refresh_screener(force=force))
        except Exception as e:
            traceback.print_exc()
            if _screener_cache["payload"] is not None:
                stale = dict(_screener_cache["payload"])
                stale["fetch_error"] = str(e)
                return jsonify(stale)
            return jsonify({"error": str(e)}), 502
    return jsonify(_screener_cache["payload"])


@app.route("/api/gex-history")
def api_gex_history():
    ticker = request.args.get("ticker", DEFAULT_TICKER)
    return jsonify({"ticker": ticker, "points": history_store.get_history(ticker)})


@app.route("/")
def index():
    return send_from_directory(str(BASE_DIR), "index.html")


def _background_warmer():
    """Mantem o cache do screener sempre quente, pra quem clicar no botao
    nunca cair no caminho frio (~15-25s). Roda um pouco antes do TTL vencer,
    em background, sem depender de nenhum clique de usuario pra disparar.
    """
    time.sleep(5)  # da tempo do processo terminar de subir
    while True:
        try:
            _refresh_screener(force=False)
        except Exception:
            traceback.print_exc()
        time.sleep(max(30, SCREENER_TTL_SECONDS - 30))


threading.Thread(target=_background_warmer, daemon=True).start()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8017))
    app.run(host="0.0.0.0", port=port, debug=False)
