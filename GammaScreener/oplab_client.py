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


def _get(path, params=None):
    token = get_token()
    r = requests.get(f"{BASE_URL}{path}", params=params, headers={"Access-Token": token}, timeout=60)
    if r.status_code == 401:
        token = get_token(force=True)
        r = requests.get(f"{BASE_URL}{path}", params=params, headers={"Access-Token": token}, timeout=60)
    r.raise_for_status()
    return r.json()


def get_stock(symbol):
    return _get(f"/market/stocks/{symbol}")
