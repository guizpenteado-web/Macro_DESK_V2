"""Cliente minimo para a API da OpLab (autenticacao + dados de opcoes da B3)."""

import os
import threading
import time
import requests

BASE_URL = "https://api.oplab.com.br/v3"

_token_cache = {"token": None, "expires_at": 0}
_token_lock = threading.Lock()
TOKEN_TTL_SECONDS = 20 * 60


def _login():
    email = os.environ["OPLAB_EMAIL"]
    password = os.environ["OPLAB_PASSWORD"]
    last_exc = None
    for attempt in range(2):
        try:
            r = requests.post(
                f"{BASE_URL}/domain/users/authenticate",
                data={"email": email, "password": password},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            token = data.get("access-token")
            if not token:
                raise RuntimeError("Login na OpLab falhou: sem access-token na resposta")
            return token
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            last_exc = exc
    raise last_exc


def get_token(force=False):
    # Fast path sem lock — caso comum (token valido), evita contencao entre
    # as 8 threads do screener numa chamada que so le o cache.
    now = time.time()
    if not force and _token_cache["token"] is not None and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    # Achado 04/ago/2026: sem lock aqui, quando o token expira as 8 threads
    # do ThreadPoolExecutor (+ a thread de warmer em background) detectavam
    # "expirado" ao mesmo tempo e disparavam ate 9 logins simultaneos na
    # OpLab — o proprio endpoint de autenticacao nao aguenta essa rajada e
    # passa a dar timeout em cascata (visto: 5000+ ReadTimeoutError no log,
    # screener inteiro voltando com 0 linhas). Double-checked locking: so a
    # primeira thread realmente faz login, as outras esperam o lock e reusam
    # o token que ela acabou de cachear.
    with _token_lock:
        now = time.time()
        if not force and _token_cache["token"] is not None and now < _token_cache["expires_at"]:
            return _token_cache["token"]
        _token_cache["token"] = _login()
        _token_cache["expires_at"] = now + TOKEN_TTL_SECONDS
        return _token_cache["token"]


def _get(path, params=None, retries=4):
    token = get_token()
    for attempt in range(retries):
        r = requests.get(f"{BASE_URL}{path}", params=params, headers={"Access-Token": token}, timeout=60)
        if r.status_code == 401:
            token = get_token(force=True)
            r = requests.get(f"{BASE_URL}{path}", params=params, headers={"Access-Token": token}, timeout=60)
        # 503 e a API sobrecarregada (achado em 03/ago/2026 varrendo ~90
        # tickers em paralelo pro filtro de qualidade do GammaScreener) --
        # backoff curto e reduz drasticamente as falhas sem esperar demais.
        if r.status_code == 503 and attempt < retries - 1:
            time.sleep(1.5 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()


def get_stock(symbol):
    return _get(f"/market/stocks/{symbol}")


def get_all_stocks():
    """/market/stocks (sem symbol) retorna TODOS os ativos (~240) numa unica
    chamada -- mesmos campos de get_stock() (bid, close, iv_current,
    financial_volume, name, etc), achado 04/ago/2026. O screener usava
    get_stock() por ticker, um por um (ate ~98 chamadas por atualizacao);
    trocar pra essa chamada em lote reduz o consumo da API de ~98
    requisicoes por ciclo pra 1 -- pedido explicito do usuario apos suspeita
    de bloqueio por padrao de acesso agressivo (ver server.py, historico do
    _scheduled_warmer)."""
    return _get("/market/stocks")


def get_historical_options(spot_ticker, date_from, date_to):
    """Historico REAL de opcoes (IV/gregas/spot por opcao/dia), endpoint
    /market/historical/options/{spot}/{from}/{to} -- achado por engenharia
    reversa do spec OpenAPI embutido em apidocs.oplab.com.br (nao estava
    documentado nos endpoints ja mapeados antes; confirmado funcionando com
    volatility real por opcao voltando a pelo menos jun/2025).
    date_from/date_to: "YYYY-MM-DD".
    """
    return _get(f"/market/historical/options/{spot_ticker}/{date_from}/{date_to}")
