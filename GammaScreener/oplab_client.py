"""Cliente minimo para a API da OpLab (autenticacao + dados de opcoes da B3)."""

import os
import time
import requests

BASE_URL = "https://api.oplab.com.br/v3"

_token_cache = {"token": None, "expires_at": 0}
TOKEN_TTL_SECONDS = 20 * 60

# Circuit breaker de login -- achado 05/ago/2026: sem isso, quando a OpLab
# fica com o proprio endpoint de autenticacao fora do ar, CADA chamada de
# get_token() (uma por ativo no loop do screener, ate ~107 por ciclo)
# tentava logar de novo do zero -- ate 107 tentativas de login em sequencia,
# 30s cada, o mesmo padrao de "efeito manada" que ja causou bloqueio antes
# (incidente 04/ago/2026). Com o breaker, 1 falha de login basta pra todas
# as chamadas seguintes falharem IMEDIATAMENTE (sem bater na rede de novo)
# ate o cooldown passar -- essencial ser MAIOR que o tempo de um ciclo
# inteiro do loop do screener, senao o breaker abre e fecha no meio do
# mesmo ciclo e nao protege nada.
LOGIN_FAILURE_COOLDOWN_SECONDS = 5 * 60
_login_failure = {"last_at": 0.0}

# Espacamento minimo entre chamadas -- a OpLab ja travou/instabilizou sob
# carga antes (efeito manada, ver incidente 04/ago/2026); dado em tempo real
# nao e prioridade aqui, entao vale poupar a API mesmo custando um pouco de
# latencia.
MIN_REQUEST_INTERVAL_SECONDS = 1.0
_last_request_at = {"t": 0.0}


def _throttle():
    now = time.time()
    wait = MIN_REQUEST_INTERVAL_SECONDS - (now - _last_request_at["t"])
    if wait > 0:
        time.sleep(wait)
    _last_request_at["t"] = time.time()


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
        if now - _login_failure["last_at"] < LOGIN_FAILURE_COOLDOWN_SECONDS:
            raise RuntimeError(
                "OpLab login falhando (circuit breaker aberto, tentando de novo em "
                f"{int(LOGIN_FAILURE_COOLDOWN_SECONDS - (now - _login_failure['last_at']))}s)"
            )
        try:
            _token_cache["token"] = _login()
        except Exception:
            _login_failure["last_at"] = time.time()
            raise
        _token_cache["expires_at"] = now + TOKEN_TTL_SECONDS
    return _token_cache["token"]


def _get(path, params=None, retries=4):
    token = get_token()
    for attempt in range(retries):
        _throttle()
        r = requests.get(f"{BASE_URL}{path}", params=params, headers={"Access-Token": token}, timeout=60)
        if r.status_code == 401:
            token = get_token(force=True)
            _throttle()
            r = requests.get(f"{BASE_URL}{path}", params=params, headers={"Access-Token": token}, timeout=60)
        if r.status_code in (502, 503) and attempt < retries - 1:
            time.sleep(2.0 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()


def get_stock(symbol):
    return _get(f"/market/stocks/{symbol}")


def get_atm_iv(symbol, spot, irate_pct):
    """IV real (Black-Scholes da OpLab) da opcao mais proxima do dinheiro no
    vencimento mais curto ainda nao vencido -- e o vencimento que mais pesa
    no gamma perto do flip, entao usar o IV dele em vez do iv_current
    (media/suavizado do ativo) calibra melhor o sweep. So considera opcoes
    com bid/ask>0 (com liquidez) pra nao pegar IV=0 de serie sem book."""
    data = _get(f"/market/instruments/series/{symbol}", params={"bs": "true", "irate": irate_pct})
    series = [e for e in data.get("series", []) if (e.get("days_to_maturity") or 0) > 0]
    if not series:
        return None
    nearest = min(series, key=lambda e: e["days_to_maturity"])

    best_iv, best_dist = None, None
    for row in nearest.get("strikes", []):
        strike = row.get("strike")
        if strike is None:
            continue
        for side in ("call", "put"):
            opt = row.get(side) or {}
            if (opt.get("bid") or 0) <= 0 and (opt.get("ask") or 0) <= 0:
                continue
            iv = (opt.get("bs") or {}).get("volatility")
            if not iv or iv <= 0:
                continue
            dist = abs(strike - spot)
            if best_dist is None or dist < best_dist:
                best_dist, best_iv = dist, iv
    return best_iv
