"""Cliente pro arquivo oficial de Posicoes em Aberto de opcoes da B3.

Achado por engenharia reversa da pagina publica
https://www.b3.com.br/pt_br/.../opcoes/posicoes-em-aberto/ : o formulario
legado (Lumis) por baixo dos panos so busca um JSON estatico publicado pela
propria B3, sem autenticacao:

    https://www.b3.com.br/json/{AAAAMMDD}/Posicoes/Empresa/SI_C_OPCPOSABEMP.json

Esse arquivo cobre o mercado inteiro (~10MB) e traz Open Interest REAL por
serie (posTo = posicao total em aberto), nao um proxy. E publicado com
defasagem (normalmente D-1 ou D-2 em relacao a data corrente), entao sempre
tentamos as ultimas datas ate achar a mais recente disponivel.
"""

import json
import os
import tempfile
import requests
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

URL_TEMPLATE = "https://www.b3.com.br/json/{d}/Posicoes/Empresa/SI_C_OPCPOSABEMP.json"

TMERC_CATEGORY = {"70": "CALL", "80": "PUT"}

BR_TZ = ZoneInfo("America/Sao_Paulo")

# Cache em disco (~10MB) do ultimo arquivo baixado com sucesso -- achado
# 04/ago/2026: a propria B3 pode ficar lenta/sem responder pro arquivo
# especifico de posicoes (mesmo com o site principal deles no ar), derrubando
# o screener inteiro sem nenhuma rede de seguranca (o cache anterior era so
# em memoria, sumia a cada restart do processo). Serve como ultimo recurso
# quando TODAS as tentativas de fetch_oi_near falham -- dado pode ficar mais
# velho que o normal (D-1/D-2), mas real, nao inventado.
CACHE_PATH = Path(__file__).resolve().parent / "b3_oi_cache.json"


def _save_cache(data, ref_date):
    payload = {"ref_date": ref_date.isoformat(), "data": data}
    fd, tmp_path = tempfile.mkstemp(dir=CACHE_PATH.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp_path, CACHE_PATH)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def _load_cache():
    if not CACHE_PATH.exists():
        return None
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return payload["data"], date.fromisoformat(payload["ref_date"])
    except Exception:
        return None


def _try_fetch(d):
    """Retorna (data, transient_error). data=None + transient_error=False
    significa "essa data nao tem arquivo publicado" (404/302 normal, segue
    o loop pro dia anterior). transient_error=True significa que a
    REQUISICAO em si falhou (timeout/conexao) -- sinal de que a B3 esta com
    problema agora mesmo, nao que essa data especifica nao existe."""
    url = URL_TEMPLATE.format(d=d.strftime("%Y%m%d"))
    try:
        r = requests.get(url, timeout=60, allow_redirects=False)
    except requests.exceptions.RequestException:
        return None, True
    if r.status_code == 200:
        return r.json(), False
    return None, False


def fetch_oi_near(target_date, max_days_back=10):
    """Retorna (data_json, data_referencia) do arquivo disponivel mais proximo
    de target_date, andando pra tras (fins de semana/feriados nao publicam
    arquivo -- so tenta o dia anterior ate achar um pregao real). Se TODAS as
    tentativas falharem (B3 fora do ar/instavel), cai pro ultimo arquivo
    salvo em disco em vez de quebrar o screener inteiro.

    Achado 04/ago/2026: um timeout de conexao (B3 travada) e tratado
    diferente de um 404 limpo (data sem arquivo) -- continuar andando pra
    tras dia a dia num timeout real levaria ate max_days_back x 60s (10min)
    pra desistir; ao primeiro timeout, para de tentar outras datas e cai
    direto pro cache (muito mais rapido, e datas anteriores tendem a falhar
    do mesmo jeito quando o problema e o servidor da B3, nao a data).
    """
    d = target_date
    for _ in range(max_days_back):
        data, transient = _try_fetch(d)
        if data is not None:
            _save_cache(data, d)
            return data, d
        if transient:
            break
        d -= timedelta(days=1)
    cached = _load_cache()
    if cached is not None:
        return cached
    raise RuntimeError(f"Nao encontrei arquivo de posicoes em aberto da B3 perto de {target_date}")


def fetch_latest_oi(max_days_back=10):
    """Retorna (data_json, data_referencia) do dia mais recente disponivel.

    Usa a data de HOJE em horario de Brasilia, nao a data local do servidor
    (achado 04/ago/2026: VPS roda em UTC, entao date.today() adiantava um
    dia inteiro entre ~21h e meia-noite BRT, sempre desperdicando a primeira
    tentativa numa data que a B3 nunca vai ter publicado).
    """
    today_brt = datetime.now(BR_TZ).date()
    return fetch_oi_near(today_brt, max_days_back=max_days_back)


def build_root_index(data):
    """Agrupa todas as entradas por ticker raiz (mer) numa unica passada.

    Consultar 30 ativos reescaneando o arquivo de ~10MB inteiro a cada um
    levava >20s; com o indice pronto cada ativo vira um dict lookup O(1).
    """
    index = defaultdict(list)
    for entries in data.get("Empresa", {}).values():
        for e in entries:
            root = e.get("mer")
            if root:
                index[root].append(e)
    return index


def _entries_to_legs(entries):
    legs = []
    for e in entries:
        oi_total = e.get("posTo") or 0
        if oi_total <= 0:
            continue
        category = TMERC_CATEGORY.get(e.get("tMerc"))
        if category is None:
            continue
        legs.append({
            "strike": e.get("prEx"),
            "category": category,
            "due_date": e.get("dtVen"),  # string "AAAAMMDD"
            "oi_total": oi_total,
            "oi_covered": e.get("poCob") or 0,
            "oi_uncovered": e.get("posDe") or 0,
            "oi_locked": e.get("posTr") or 0,
            "symbol": e.get("ser"),
        })
    return legs


def extract_legs(data, root_ticker="BOVA"):
    """Extrai as pernas (call/put por strike/vencimento) de um ativo especifico."""
    entries = [e for entries in data.get("Empresa", {}).values() for e in entries if e.get("mer") == root_ticker]
    return _entries_to_legs(entries)


def extract_legs_from_index(index, root_ticker):
    """Mesma coisa que extract_legs, mas a partir do indice de build_root_index (O(1))."""
    return _entries_to_legs(index.get(root_ticker, []))


def classify_suffix(esp_pap):
    """Deduz o sufixo do ticker (3/4/5/6/11) a partir do campo espPap da B3.

    Isso evita depender de memoria pra mapear cada empresa pra sua classe de
    acao mais liquida -- vem direto do dado oficial de qual classe de acao
    as opcoes realmente referenciam.
    """
    s = (esp_pap or "").strip().upper()
    if s.startswith("PNA"):
        return "5"
    if s.startswith("PNB"):
        return "6"
    if s.startswith("PNC"):
        return "7"
    if s.startswith("PN"):
        return "4"
    if s.startswith("ON"):
        return "3"
    if s.startswith("UNT") or s.startswith("CI"):
        return "11"
    return None


def build_universe(index, top_n=30):
    """Ranqueia os ativos com opcoes por OI total e monta o ticker negociavel de cada um.

    Recebe o indice de build_root_index (root -> lista de entradas), nao o
    JSON bruto -- evita reescanear o arquivo inteiro de novo.
    """
    oi_by_root = defaultdict(float)
    name_by_root = {}
    esp_pap_votes = defaultdict(Counter)

    for root, entries in index.items():
        for e in entries:
            oi_by_root[root] += e.get("posTo") or 0
            name_by_root[root] = e.get("nmEmp")
            esp_pap_votes[root][e.get("espPap")] += 1

    ranked = sorted(oi_by_root.items(), key=lambda x: -x[1])

    universe = []
    for root, oi_total in ranked:
        if len(universe) >= top_n:
            break
        esp_pap = esp_pap_votes[root].most_common(1)[0][0]
        suffix = classify_suffix(esp_pap)
        if suffix is None:
            continue  # classe de acao nao identificavel, pula pro proximo
        ticker = f"{root}{suffix}"
        universe.append({
            "root": root,
            "ticker": ticker,
            "name": name_by_root[root],
            "oi_total": oi_total,
        })
    return universe


def count_active_strikes(index, root):
    """Numero de strikes distintos com OI>0 pro root, direto do indice de
    build_root_index -- nao depende da OpLab. Proxy de profundidade real da
    cadeia: uma cadeia com poucos strikes ativos nao sustenta um sweep de
    spot hipotetico +-30% confiavel (o Gamma Flip fica sensivel a cada ponto
    faltando em vez de suavizado por dezenas de strikes). Achado em
    03/ago/2026 comparando contra financial_volume/iv_current da OpLab: ativos
    com <30 strikes ativos quase sempre tambem tinham iv_current=0 (cadeia
    morta) ou volume do papel-base minusculo -- os tres sinais concordam.
    """
    strikes = set()
    for e in index.get(root, []):
        if (e.get("posTo") or 0) > 0:
            strikes.add(e.get("prEx"))
    return len(strikes)
