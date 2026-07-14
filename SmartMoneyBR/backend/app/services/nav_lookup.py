"""Logica compartilhada de "qual e' o PL do fundo numa data" — usada em
qualquer lugar que calcule "% do PL" de uma posicao (assets.py::get_asset_holders,
funds.py::get_fund_position_history). Extraida pra um so lugar depois de um
bug real (achado 13/07/2026): NAV_STALENESS_MAX_DAYS nao existia, e um FundNav
de varios meses atras (mas ainda dentro do teto de razao carteira/PL) gerava
%PL de milhares de % pra fundos em captacao rapida. Ter duas copias dessa
logica e' o tipo de coisa que rediverge silenciosamente se so uma for
corrigida no futuro — daqui em diante so existe uma.
"""
from __future__ import annotations

from datetime import date

# Teto de sanidade generoso pro FundNav — so pra pegar o caso degenerado de
# patrimonio essencialmente zero (achado 12/jul/2026: SKOPOS TOP TRADES
# EQUITY HEDGE tinha FundNav=R$0,03 num mes, contra uma carteira de R$300mi+
# em 20 ativos — razao ~10,6 MILHOES de vezes). Auditoria completa mostrou
# que casos genuinamente concentrados/alavancados (ex: GENERALE em SMFT3,
# validado contra a referencia) ficam ate ~46x no maximo — 200x da uma folga
# enorme sem esconder concentracao real.
NAV_SANITY_MAX_RATIO = 200.0

# Achado 13/07/2026 (investigacao dos "302% do PL"): a checagem de
# plausibilidade acima (razao carteira/PL) so pega patrimonio ABSURDAMENTE
# baixo, mas nao pega patrimonio ANTIGO — fundo que cresce rapido (captacao
# forte) pode ter o ultimo FundNav/FundQuota disponivel de varios meses
# atras, ainda "razoavel" pela razao mas ja completamente desatualizado.
# Caso confirmado: ITAU MASTER VALE ACOES (fundo essencialmente 100%
# VALE3), FundNav so tinha 2021-01-31 (R$33mi) pra uma posicao em
# 2021-05-31 (carteira ja em R$1bi) — razao 30x passava no teto de 200x e
# retornava %PL de 3026%, quando o FundQuota exato dessa data (R$1,000bi)
# da ~99,97%. Com o teto de 45 dias, exige que o NAV usado seja de fato
# contemporaneo aa posicao.
NAV_STALENESS_MAX_DAYS = 45

PORTFOLIO_TO_NAV_MAX_RATIO = 5.0
FLOOR_TOLERANCE = 1.10


def nav_as_of(
    holding_date: date,
    portfolio_total: float,
    exact_nav: float | None,
    navs_sorted: list[tuple[date, float]],
) -> float | None:
    """navs_sorted: (ref_date, net_asset_value) do FundNav, UM fundo, ordem
    ascendente. exact_nav: valor ja resolvido para (fundo, holding_date), se
    existir (evita repetir o dict lookup em cada chamador)."""

    def is_sane(nav: float) -> bool:
        if nav <= 0:
            return False
        if portfolio_total > 0 and portfolio_total / nav > NAV_SANITY_MAX_RATIO:
            return False
        return True

    if exact_nav is not None and is_sane(exact_nav):
        return exact_nav
    for rd, nav in reversed(navs_sorted):
        if rd > holding_date:
            continue
        if (holding_date - rd).days > NAV_STALENESS_MAX_DAYS:
            break
        if is_sane(nav):
            return nav
    return None


def quota_fallback(
    holding_date: date,
    position_value: float,
    portfolio_total: float,
    quotas_sorted: list[tuple[date, float]],
) -> float | None:
    """quotas_sorted: (ref_date, net_asset_value) do FundQuota, UM fundo,
    ordem ascendente."""
    best = None
    for rd, nav in quotas_sorted:
        if rd > holding_date:
            break
        if (holding_date - rd).days > NAV_STALENESS_MAX_DAYS:
            continue
        if position_value > 0 and nav * FLOOR_TOLERANCE < position_value:
            continue
        if portfolio_total > 0 and nav * PORTFOLIO_TO_NAV_MAX_RATIO < portfolio_total:
            continue
        best = nav
    return best
