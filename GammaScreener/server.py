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
from gex_engine import build_gex_payload, flatten_legs_from_oi

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")

DEFAULT_TICKER = "BOVA11"
DEFAULT_ROOT = "BOVA"
UNIVERSE_SIZE = 60

OI_TTL_SECONDS = 6 * 60 * 60  # arquivo da B3 so muda uma vez por dia
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
        }
    except Exception as asset_err:
        traceback.print_exc()
        return {"ticker": asset["ticker"], "root": asset["root"], "name": asset["name"],
                "error": str(asset_err)}


def _refresh_screener(force=False):
    """Recalcula o screener inteiro. As chamadas por ativo na OpLab sao a
    parte lenta (I/O de rede, uma por ativo) -- paralelizadas com um thread
    pool em vez de sequenciais, senao 60 ativos x ~300-500ms cada vira
    15-25s de espera. O arquivo de OI da B3 continua buscado 1x so (dentro
    de _get_oi_index, TTL proprio), nunca por ativo.
    """
    oi_index, ref_date = _get_oi_index(force=force)
    universe = b3_oi_client.build_universe(oi_index, top_n=UNIVERSE_SIZE)
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        rows = list(pool.map(
            lambda asset: _row_for_asset(asset, oi_index, ref_date, force), universe
        ))
    payload = {
        "rows": rows,
        "oi_reference_date": ref_date.strftime("%Y-%m-%d"),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
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
