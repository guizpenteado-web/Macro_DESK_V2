"""Cliente minimo para a API da OpLab (autenticacao + dados de opcoes da B3)."""

import os
import time
import requests

BASE_URL = "https://api.oplab.com.br/v3"

_token_cache = {"token": None, "expires_at": 0}
TOKEN_TTL_SECONDS = 20 * 60


def _login():
    email = os.environ["OPLAB_EMAIL"]
    password = os.environ["OPLAB_PASSWORD"]
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


def get_token(force=False):
    now = time.time()
    if force or _token_cache["token"] is None or now >= _token_cache["expires_at"]:
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


def get_historical_options(spot_ticker, date_from, date_to):
    """Historico REAL de opcoes (IV/gregas/spot por opcao/dia), endpoint
    /market/historical/options/{spot}/{from}/{to} -- achado por engenharia
    reversa do spec OpenAPI embutido em apidocs.oplab.com.br (nao estava
    documentado nos endpoints ja mapeados antes; confirmado funcionando com
    volatility real por opcao voltando a pelo menos jun/2025).
    date_from/date_to: "YYYY-MM-DD".
    """
    return _get(f"/market/historical/options/{spot_ticker}/{date_from}/{date_to}")
