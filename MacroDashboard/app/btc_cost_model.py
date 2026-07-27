"""
Bitcoin Production Cost (modelo Capriole) — reconstrução ancorada em prints reais.

Metodologia: Capriole Investments (Charles Edwards), capriole.com/bitcoins-production-cost.
Formula:
    Elec. cost / BTC = (hashrate 7d-avg * eficiência J/TH * PUE * 24h / 1000) * $/kWh / (144 * block reward)
    Custo total       = Custo elétrico / ratio elétrico-total

A curva de eficiência de fleet (J/TH) não é publicada pela Capriole. Em vez de assumir uma
média de rede "crua" (que roda mais ineficiente que o modelo real deles, já que a Capriole
filtra para hardware lucrativo), 6 pontos foram retirados diretamente do site/newsletter/X
da própria Capriole e resolvidos "de trás pra frente" pela fórmula acima para recuperar a
eficiência implícita em cada data. Ver ANCHORS abaixo — cada um tem a fonte primária citada.
Entre esses pontos, interpolação log-linear. Antes do primeiro ancora real (2022-11-15), a
curva é reconstrução própria baseada em specs conhecidos de ASIC (ver bridge_pre2022).
"""
from __future__ import annotations
import math
from datetime import date, datetime, timedelta

ELEC_PRICE = 0.05      # USD/kWh — premissa da própria Capriole, cross-checada contra 10-Q
                        # reais de mineradoras públicas Q1/2026 (Riot 3.0c, CleanSpark/Hut8 4-5c)
PUE = 1.1               # premissa da própria Capriole
ELEC_TO_TOTAL = 0.79    # substituído do doc de metodologia de 2019 (0.60) pelos prints reais
                        # de 2025-2026 da Capriole, que implicam ~0.79
BLOCKS_PER_DAY = 144

HALVINGS = [
    (date(2012, 11, 28), 50.0),
    (date(2016, 7, 9), 25.0),
    (date(2020, 5, 11), 12.5),
    (date(2024, 4, 20), 6.25),
]
# reward vigente ANTES do primeiro halving listado = 50; a lista acima já cobre 25/12.5/6.25.
# ajuste: reward após cada data listada passa a ser o valor seguinte (ver block_reward()).
_REWARD_SCHEDULE = [
    (date(2012, 11, 28), 25.0),
    (date(2016, 7, 9), 12.5),
    (date(2020, 5, 11), 6.25),
    (date(2024, 4, 20), 3.125),
]

# Âncoras reais de Bitcoin Electrical Cost (BEC), publicadas pela própria Capriole / Charles
# Edwards, resolvidas para eficiência de fleet (J/TH) implícita via a fórmula acima.
#   2022-11-15  BEC ~$16,900   -> 43.96 J/TH   (cobertura do colapso da FTX, nov/2022)
#   2023-09-07  BEC = preço*0.85 -> 37.49 J/TH (newsletter Capriole, "elétrico 15% abaixo do preço")
#   2024-04-22  BEC=$77,400    -> 42.17 J/TH   (@caprioleio no X, 2 dias pós-halving)
#   2025-11-07  BEC=$71,000    -> 22.16 J/TH   (Capriole Update #67)
#   2026-06-09  BEC=$50,000    -> 19.74 J/TH   (Charles Edwards via news.bitcoin.com)
#   2026-07-20  BEC=$49,000    -> 18.15 J/TH   (indicador TradingView da Capriole)
EFF_ANCHORS: list[tuple[date, float]] = [
    (date(2013, 1, 1), 3300), (date(2013, 7, 1), 2200), (date(2014, 1, 1), 1300), (date(2014, 7, 1), 800),
    (date(2015, 1, 1), 500), (date(2015, 7, 1), 350), (date(2016, 1, 1), 250), (date(2016, 7, 1), 180),
    (date(2017, 1, 1), 140), (date(2017, 7, 1), 115), (date(2018, 1, 1), 95), (date(2018, 7, 1), 82),
    (date(2019, 1, 1), 72), (date(2019, 7, 1), 62), (date(2020, 1, 1), 52), (date(2020, 7, 1), 46),
    (date(2021, 1, 1), 44), (date(2021, 7, 1), 43), (date(2022, 1, 1), 43), (date(2022, 7, 1), 44),
    (date(2022, 11, 15), 43.96), (date(2023, 9, 7), 37.49), (date(2024, 4, 22), 42.17),
    (date(2025, 11, 7), 22.16), (date(2026, 6, 9), 19.74), (date(2026, 7, 20), 18.15),
]


def _eff_j_per_th(d: date) -> float:
    anchors = EFF_ANCHORS
    if d <= anchors[0][0]:
        return anchors[0][1]
    if d >= anchors[-1][0]:
        return anchors[-1][1]
    for (d0, v0), (d1, v1) in zip(anchors, anchors[1:]):
        if d0 <= d <= d1:
            span = (d1 - d0).days
            if span == 0:
                return v0
            f = (d - d0).days / span
            return math.exp(math.log(v0) + f * (math.log(v1) - math.log(v0)))
    return anchors[-1][1]


def _block_reward(d: date) -> float:
    reward = 50.0
    for hd, r in _REWARD_SCHEDULE:
        if d >= hd:
            reward = r
    return reward


def _parse(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


def compute_prodcost_series(price_rows: list[tuple], hash_rows: list[tuple]) -> dict | None:
    """
    price_rows: [(date_str, close_usd)] de get_prices("BTC-USD"), ordenado por data.
    hash_rows:  [(date_str, hashrate_THs)] de get_prices("BTC-HASHRATE"), ordenado por data.
    Retorna série semanal (dict de listas) ou None se dados insuficientes.
    """
    if not price_rows or not hash_rows or len(price_rows) < 30 or len(hash_rows) < 30:
        return None

    price_by_date: dict[date, float] = {_parse(d): v for d, v in price_rows if v is not None}
    hash_by_date: dict[date, float] = {_parse(d): v for d, v in hash_rows if v is not None}

    sorted_hash_dates = sorted(hash_by_date.keys())

    def smoothed_hash(d: date) -> float | None:
        vals = []
        for i in range(7):
            dd = d - timedelta(days=i)
            v = hash_by_date.get(dd)
            if v is not None:
                vals.append(v)
        return sum(vals) / len(vals) if vals else None

    start = min(price_by_date.keys())
    end = max(price_by_date.keys())

    rows = []
    d = start
    while d <= end:
        p = price_by_date.get(d)
        h_ths = smoothed_hash(d)  # TH/s, média móvel 7d
        if p is not None and h_ths is not None and h_ths > 0:
            eff_j_th = _eff_j_per_th(d)
            eff_j_h = eff_j_th / 1e12
            hash_hs = h_ths * 1e12
            power_w = hash_hs * eff_j_h * PUE
            daily_kwh = power_w * 24 / 1000
            daily_elec_cost = daily_kwh * ELEC_PRICE
            btc_per_day = BLOCKS_PER_DAY * _block_reward(d)
            elec_cost = daily_elec_cost / btc_per_day
            prod_cost = elec_cost / ELEC_TO_TOTAL
            margin_pct = ((p - elec_cost) / elec_cost) * 100
            rows.append({
                "date": d.isoformat(), "price": p, "elec": elec_cost, "prod": prod_cost,
                "margin": margin_pct, "hashEH": hash_hs / 1e18,
            })
        d += timedelta(days=1)

    if len(rows) < 30:
        return None

    weekly = rows[::7]
    if weekly[-1]["date"] != rows[-1]["date"]:
        weekly.append(rows[-1])

    r2 = lambda x: round(x, 2)
    return {
        "dates":  [r["date"] for r in weekly],
        "price":  [r2(r["price"]) for r in weekly],
        "elec":   [r2(r["elec"]) for r in weekly],
        "prod":   [r2(r["prod"]) for r in weekly],
        "margin": [round(r["margin"], 1) for r in weekly],
        "hashEH": [r2(r["hashEH"]) for r in weekly],
        "meta": {
            "elec_price_kwh": ELEC_PRICE, "pue": PUE, "elec_to_total": ELEC_TO_TOTAL,
            "last_eff_jth": round(_eff_j_per_th(end), 2),
        },
    }
