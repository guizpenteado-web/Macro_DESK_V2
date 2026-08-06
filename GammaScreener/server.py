import json
import os
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env")

import oplab_client
import b3_oi_client
from gex_engine import build_gex_payload, flatten_legs_from_oi, SELIC_RATE

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")

DEFAULT_TICKER = "BOVA11"
DEFAULT_ROOT = "BOVA"

# Filtro de qualidade do mercado de GEX -- ver server.py do Hub
# (Mktsentiment/GammaScreener) pro racional completo, validado em
# 03/ago/2026. Substitui o corte fixo por rank de OI.
CANDIDATE_POOL_SIZE = 200
MIN_ACTIVE_STRIKES = 30
MIN_OI_TOTAL = 1_000_000
MIN_FINANCIAL_VOLUME = 10_000_000

OI_TTL_SECONDS = 2 * 60 * 60   # pedido do usuario 03/ago/2026 (era 6h)
ASSET_TTL_SECONDS = 50 * 60    # 05/ago/2026: dado em tempo real nao e prioridade,
                                # o que importa e a metrica certa -- intervalo maior
                                # poupa a OpLab (historico de instabilidade/bloqueio
                                # sob carga, ver memoria do incidente 04/ago)
# SCREENER_TTL nao existe mais -- o screener so atualiza nos horarios fixos
# de SCHEDULED_REFRESH_TIMES_BRT (ver _scheduled_warmer), nunca por TTL.

_oi_cache = {"index": None, "ref_date": None, "fetched_at": 0}
_asset_cache = {}  # ticker -> {"payload":..., "fetched_at":...}
_screener_cache = {"payload": None, "fetched_at": 0}
_screener_lock = threading.Lock()
_screener_refreshing = False
_screener_ready = threading.Event()  # sinaliza quando o 1o calculo (cold start) termina

# Persistencia em disco do cache do screener -- achado 06/ago/2026: o Hub
# (processo pai) estava sendo reiniciado externamente via SSH a cada poucos
# minutos (fora do nosso controle), e cada restart derrubava esse processo
# junto, zerando o cache em memoria. Sem isso, toda vez o 1o usuario a abrir
# a tela caia na janela de "calculando pela primeira vez" (503 por ate ~90s).
# Com o cache em disco, o processo recem-subido ja responde na hora com o
# ultimo resultado valido (marcado com sua idade real) enquanto recalcula em
# background.
_SCREENER_CACHE_FILE = BASE_DIR / "screener_cache.json"


def _load_screener_cache_from_disk():
    try:
        with open(_SCREENER_CACHE_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        _screener_cache["payload"] = saved["payload"]
        _screener_cache["fetched_at"] = saved["fetched_at"]
        _screener_ready.set()
    except Exception:
        pass


def _save_screener_cache_to_disk():
    try:
        with open(_SCREENER_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"payload": _screener_cache["payload"], "fetched_at": _screener_cache["fetched_at"]}, f)
    except Exception:
        traceback.print_exc()


_load_screener_cache_from_disk()


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


def _compute_asset_payload(ticker, root, oi_index, ref_date, use_atm_iv=True):
    stock = oplab_client.get_stock(ticker)
    bid, ask = stock.get("bid"), stock.get("ask")
    spot = (bid + ask) / 2 if bid and ask else (stock.get("close") or bid)

    iv_current = stock.get("iv_current") or 17.5
    iv_atm = None
    # IV ATM real (venc. mais curto) so ajuda em acoes -- em ETF/unit (sufixo
    # 11, ex BOVA11) o iv_current ja bate bem com o flip real (testado
    # 05/ago/2026: aplicar ATM la piorou o resultado vs iv_current flat).
    is_etf_or_unit = ticker.endswith("11")
    if use_atm_iv and not is_etf_or_unit:
        # So busca a serie completa (chamada pesada na OpLab) na tela de
        # detalhe de 1 ativo -- fazer isso pra cada um dos 30-60 ativos do
        # screener em lote reintroduziria o mesmo travamento da OpLab ja
        # visto antes (ver incidente de bloqueio, 04/ago/2026).
        try:
            iv_atm = oplab_client.get_atm_iv(ticker, spot, irate_pct=SELIC_RATE * 100)
        except Exception:
            iv_atm = None
    iv = (iv_atm if iv_atm else iv_current) / 100.0

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
    payload["financial_volume"] = stock.get("financial_volume") or 0
    payload["iv_source"] = "atm_nearest_expiry" if iv_atm else "stock_iv_current"
    payload["iv_current_raw"] = stock.get("iv_current") or 0
    return payload


def _get_asset_payload(ticker, root, oi_index, ref_date, force=False, use_atm_iv=True):
    now = time.time()
    cache_key = (ticker, use_atm_iv)
    entry = _asset_cache.get(cache_key)
    if force or entry is None or now - entry["fetched_at"] > ASSET_TTL_SECONDS:
        payload = _compute_asset_payload(ticker, root, oi_index, ref_date, use_atm_iv=use_atm_iv)
        entry = {"payload": payload, "fetched_at": now}
        _asset_cache[cache_key] = entry
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
        entry = _asset_cache.get((ticker, True))
        if entry is not None:
            stale = dict(entry["payload"])
            stale["fetch_error"] = str(e)
            return jsonify(stale)
        return jsonify({"error": str(e)}), 502


def _compute_screener(force):
    """Calculo pesado (percorre ~100+ ativos na OpLab, sequencial, pode levar
    minutos se a OpLab estiver degradada) -- roda SEMPRE numa thread separada
    (nunca no request handler), pra nenhum clique de usuario ficar pendurado
    esperando rede de terceiro. Atualiza _screener_cache quando termina;
    request handler so LE o cache, nunca espera esse calculo direto (exceto
    no cold-start, com timeout curto -- ver api_screener). Achado 05/ago/2026:
    a OpLab ficou intermitente/lenta e o calculo sincrono anterior deixava a
    aba inteira "travada" no clique do usuario por minutos."""
    global _screener_refreshing
    try:
        oi_index, ref_date = _get_oi_index(force=force)
        candidates = b3_oi_client.build_universe(oi_index, top_n=CANDIDATE_POOL_SIZE)
        for c in candidates:
            c["n_active_strikes"] = b3_oi_client.count_active_strikes(oi_index, c["root"])
        prefiltered = [
            c for c in candidates
            if c["oi_total"] >= MIN_OI_TOTAL and c["n_active_strikes"] >= MIN_ACTIVE_STRIKES
        ]
        rows = []
        for asset in prefiltered:
            try:
                p = _get_asset_payload(asset["ticker"], asset["root"], oi_index, ref_date, force=force, use_atm_iv=False)
                if (p.get("iv_current_raw") or 0) <= 0 or (p.get("financial_volume") or 0) < MIN_FINANCIAL_VOLUME:
                    continue
                rows.append({
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
                })
            except Exception:
                traceback.print_exc()
        rows.sort(key=lambda r: -(r.get("oi_total") or 0))
        _screener_cache["payload"] = {
            "rows": rows,
            "oi_reference_date": ref_date.strftime("%Y-%m-%d"),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "universe_candidates": len(candidates),
            "universe_prefiltered": len(prefiltered),
            "universe_kept": len(rows),
        }
        _screener_cache["fetched_at"] = time.time()
        _save_screener_cache_to_disk()
    except Exception as e:
        traceback.print_exc()
        if _screener_cache["payload"] is not None:
            stale = dict(_screener_cache["payload"])
            stale["fetch_error"] = str(e)
            _screener_cache["payload"] = stale
            # fetched_at NAO avanca -- proxima chamada tenta de novo, nao
            # fica presa achando que esse erro e um resultado valido fresco.
    finally:
        _screener_refreshing = False
        _screener_ready.set()


def _kick_off_screener_refresh(force=False):
    """Dispara _compute_screener em background se nao tiver uma rodando
    ja -- lock evita 2 threads batendo na OpLab ao mesmo tempo pro mesmo
    calculo (varios usuarios clicando juntos, por ex)."""
    global _screener_refreshing
    with _screener_lock:
        if _screener_refreshing:
            return False
        _screener_refreshing = True
        _screener_ready.clear()
    threading.Thread(target=_compute_screener, args=(force,), daemon=True).start()
    return True


@app.route("/api/screener")
def api_screener():
    # Achado 05/ago/2026: o botao "Atualizar" (force=1) e o TTL de 5min NAO
    # disparam mais coleta nova aqui -- so o _scheduled_warmer (horarios
    # fixos, ver mais abaixo) tem permissao pra bater na OpLab pro screener.
    # Motivo: o loop varre ate ~107 ativos, cada exception (ex. login falhando)
    # so passava pro proximo -- combinado com TTL curto e clientes clicando
    # em "Atualizar", isso gerava dezenas de tentativas de login em sequencia
    # (achado ao vivo: 500+ tentativas em 35min numa OpLab degradada), o
    # mesmo padrao de "efeito manada" que ja causou bloqueio antes (ver
    # incidente 04/ago/2026 na memoria do projeto). Unica excecao: processo
    # acabou de subir e ainda nao tem NENHUM cache (bootstrap unico).
    if _screener_cache["payload"] is None:
        _kick_off_screener_refresh(force=False)
        finished = _screener_ready.wait(timeout=25)
        if finished and _screener_cache["payload"] is not None:
            return jsonify(_screener_cache["payload"])
        return jsonify({"error": "Calculando dados pela primeira vez, ainda nao pronto -- tente novamente em alguns segundos."}), 503

    payload = dict(_screener_cache["payload"])
    payload["next_scheduled_refresh"] = _next_scheduled_refresh_label()
    return jsonify(payload)


@app.route("/")
def index():
    return send_from_directory(str(BASE_DIR), "index.html")


# Horarios fixos de coleta na OpLab pro screener, horario de Brasilia --
# pedido explicito do usuario 05/ago/2026: nao precisa de dado em tempo
# real, so 3x/dia (abertura, meio do dia, fechamento). Mais enxuto que o
# padrao de 9x/dia (hora em hora) ja usado no server.py do Hub (git,
# Mktsentiment/GammaScreener) desde 04/ago/2026 -- aqui reduzido ainda mais
# porque o usuario nao precisa de granularidade intradiaria nenhuma.
SCHEDULED_REFRESH_TIMES_BRT = [(11, 0), (15, 0), (18, 0)]
BR_TZ = ZoneInfo("America/Sao_Paulo")


def _next_scheduled_refresh_label() -> str:
    now = datetime.now(BR_TZ)
    today_slots = [now.replace(hour=h, minute=m, second=0, microsecond=0) for h, m in SCHEDULED_REFRESH_TIMES_BRT]
    upcoming = [s for s in today_slots if s > now]
    nxt = min(upcoming) if upcoming else min(today_slots)
    return nxt.strftime("%H:%M") + " (BRT)"


def _scheduled_warmer():
    """Atualiza o cache do screener so nos horarios fixos de
    SCHEDULED_REFRESH_TIMES_BRT. Bootstrap unico ao subir (se ainda nao
    tiver cache nenhum) fica a cargo do proprio api_screener (1a requisicao
    apos o processo subir); aqui so cuidamos dos horarios agendados."""
    last_run_key = None
    while True:
        now = datetime.now(BR_TZ)
        run_key = now.strftime("%Y-%m-%d %H:%M")
        if (now.hour, now.minute) in SCHEDULED_REFRESH_TIMES_BRT and run_key != last_run_key:
            _kick_off_screener_refresh(force=True)
            last_run_key = run_key
        time.sleep(30)


# GAMMA_WARMER_DISABLED=1 no .env pausa a coleta agendada por completo (fica
# 100% manual/parada) -- valvula de escape pra qualquer proximo incidente de
# bloqueio da OpLab, mesmo padrao ja usado no Hub em 04/ago/2026.
if os.environ.get("GAMMA_WARMER_DISABLED") != "1":
    threading.Thread(target=_scheduled_warmer, daemon=True).start()
    # Dispara o 1o calculo assim que o processo sobe, em vez de esperar o
    # primeiro usuario clicar (ver comentario de _SCREENER_CACHE_FILE acima
    # -- com restarts externos frequentes, isso reduz ainda mais a janela
    # em que /api/screener so tem o cache antigo do disco pra oferecer).
    _kick_off_screener_refresh(force=False)


if __name__ == "__main__":
    # threaded=True -- achado 05/ago/2026: sem isso, o servidor de dev do
    # Flask processa 1 requisicao por vez; o cold-start do screener (ate 25s
    # de espera, ver api_screener) travava ATE requisicoes de outros
    # endpoints (ex. /api/gex de outro usuario) na fila atras dele.
    app.run(host="127.0.0.1", port=8017, debug=False, threaded=True)
