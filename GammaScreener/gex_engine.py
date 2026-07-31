"""Calculo de GEX (Gamma Exposure) real para BOVA11.

Peso de posicionamento = Open Interest oficial da B3 (via b3_oi_client),
publicado com defasagem de D-1/D-2 (fechamento do ultimo pregao disponivel) --
mesma pratica de qualquer ferramenta de GEX, inclusive nos EUA. Spot e
volatilidade implicita vem ao vivo da OpLab.
"""

import math
import numpy as np

SELIC_RATE = 0.1425  # taxa Selic vigente (ver fonte no momento do deploy)


def gamma_bs(S, K, T, sigma, r=SELIC_RATE):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi) / (S * sigma * math.sqrt(T))


def flatten_legs_from_oi(oi_legs, ref_date):
    """Converte pernas do arquivo oficial de OI da B3 pro formato comum, pesadas por Open Interest real."""
    legs = []
    for e in oi_legs:
        due = e.get("due_date")
        if not due:
            continue
        due_dt = _parse_yyyymmdd(due)
        dtm = (due_dt - ref_date).days
        if dtm <= 0:
            continue
        weight = e.get("oi_total") or 0
        if weight <= 0:
            continue
        legs.append({
            "strike": e["strike"],
            "T": dtm / 365.0,
            "sign": 1.0 if e["category"] == "CALL" else -1.0,
            "category": e["category"],
            "weight": weight,
            "symbol": e.get("symbol"),
        })
    return legs


def _parse_yyyymmdd(s):
    from datetime import date
    return date(int(s[0:4]), int(s[4:6]), int(s[6:8]))


def gex_by_strike(legs, spot, iv):
    """GEX liquido por strike, avaliado no spot atual (para o cockpit)."""
    by_strike = {}
    for leg in legs:
        g = gamma_bs(spot, leg["strike"], leg["T"], iv)
        if g <= 0:
            continue
        exposure = g * leg["weight"] * spot ** 2 * 0.01
        signed = exposure * leg["sign"]
        k = leg["strike"]
        acc = by_strike.setdefault(k, {"strike": k, "gex_call": 0.0, "gex_put": 0.0,
                                        "gex_net": 0.0, "weight_call": 0, "weight_put": 0})
        acc["gex_net"] += signed
        if leg["category"] == "CALL":
            acc["gex_call"] += signed  # magnitude positiva pro lado call
            acc["weight_call"] += leg["weight"]
        else:
            acc["gex_put"] += -signed  # magnitude positiva pro lado put
            acc["weight_put"] += leg["weight"]
    return sorted(by_strike.values(), key=lambda r: r["strike"])


def gex_profile_sweep(legs, spot, iv, pct_range=0.30, n_points=121):
    """Sweep de spot hipotetico (+/- pct_range) com posicionamento/vol/prazo constantes.

    Isso responde: "para qual preco do BOVA11 a exposicao liquida de gamma
    dos dealers muda de sinal?" -- essa e a definicao de Gamma Flip.
    """
    lo = spot * (1 - pct_range)
    hi = spot * (1 + pct_range)
    spots = np.linspace(lo, hi, n_points)
    net = np.zeros(n_points)
    pos = np.zeros(n_points)
    neg = np.zeros(n_points)

    for leg in legs:
        gammas = np.array([gamma_bs(s, leg["strike"], leg["T"], iv) for s in spots])
        exposure = gammas * leg["weight"] * spots ** 2 * 0.01 * leg["sign"]
        net += exposure
        pos += np.clip(exposure, 0, None)
        neg += np.clip(exposure, None, 0)

    # Cadeias reais podem ter mais de um cruzamento de sinal dentro do range
    # (OI concentrado de forma irregular por strike). O flip que importa pro
    # regime atual e o mais PROXIMO do spot -- pegar sempre o primeiro (mais
    # distante, na ponta de baixo do range) pode reportar um nivel que nao
    # tem nada a ver com pra onde o preco precisaria ir pra mudar de regime.
    flip = None
    sign_changes = np.where(np.diff(np.signbit(net)))[0]
    if len(sign_changes) > 0:
        crossings = []
        for i in sign_changes:
            x0, x1 = spots[i], spots[i + 1]
            y0, y1 = net[i], net[i + 1]
            crossings.append(x0 + (0 - y0) * (x1 - x0) / (y1 - y0))
        flip = float(min(crossings, key=lambda cx: abs(cx - spot)))

    return {
        "spots": spots.tolist(),
        "net": net.tolist(),
        "pos": pos.tolist(),
        "neg": neg.tolist(),
        "flip": flip,
    }


def build_gex_payload(spot, iv, legs, methodology_note, weight_label):
    by_strike = gex_by_strike(legs, spot, iv)
    profile = gex_profile_sweep(legs, spot, iv)

    gex_net_total = sum(r["gex_net"] for r in by_strike)

    within_range = [r for r in by_strike if abs(r["strike"] / spot - 1) <= 0.30]
    within_sorted = sorted(within_range, key=lambda r: r["strike"])

    cum = np.cumsum([r["gex_net"] for r in within_sorted])
    strikes_sorted = [r["strike"] for r in within_sorted]
    zero_gamma_strike = None
    cross = np.where(np.diff(np.signbit(cum)))[0]
    if len(cross) > 0:
        # Mesmo caso do gamma_flip: o cumulativo pode cruzar zero mais de uma
        # vez com OI real espalhado de forma irregular. O primeiro cruzamento
        # (ponta de baixo do range) nao e necessariamente o relevante -- pega
        # o mais proximo do spot.
        candidates = [strikes_sorted[i] for i in cross]
        zero_gamma_strike = float(min(candidates, key=lambda k: abs(k - spot)))

    above_spot = [r for r in within_range if r["strike"] >= spot]
    below_spot = [r for r in within_range if r["strike"] <= spot]
    call_wall = max(above_spot, key=lambda r: r["gex_net"])["strike"] if above_spot else None
    put_wall = min(below_spot, key=lambda r: r["gex_net"])["strike"] if below_spot else None

    return {
        "spot": spot,
        "iv_current": iv * 100,
        "gex_net_total": gex_net_total,
        "regime": "NEGATIVO (vol amplifica)" if gex_net_total < 0 else "POSITIVO (vol estabiliza)",
        "gamma_flip": profile["flip"],
        "zero_gamma_strike": zero_gamma_strike,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "by_strike": within_range,
        "profile": profile,
        "n_legs": len(legs),
        "weight_label": weight_label,
        "methodology_note": methodology_note,
    }
