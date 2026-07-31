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

import requests
from collections import Counter, defaultdict
from datetime import date, timedelta

URL_TEMPLATE = "https://www.b3.com.br/json/{d}/Posicoes/Empresa/SI_C_OPCPOSABEMP.json"

TMERC_CATEGORY = {"70": "CALL", "80": "PUT"}


def _try_fetch(d):
    url = URL_TEMPLATE.format(d=d.strftime("%Y%m%d"))
    r = requests.get(url, timeout=60, allow_redirects=False)
    if r.status_code == 200:
        return r.json()
    return None


def fetch_latest_oi(max_days_back=10):
    """Retorna (data_json, data_referencia) do dia mais recente disponivel."""
    d = date.today()
    for _ in range(max_days_back):
        data = _try_fetch(d)
        if data is not None:
            return data, d
        d -= timedelta(days=1)
    raise RuntimeError("Nao encontrei arquivo de posicoes em aberto da B3 nos ultimos dias")


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
