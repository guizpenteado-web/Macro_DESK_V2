from datetime import date

from pydantic import BaseModel


class FundOut(BaseModel):
    id: int
    cnpj: str
    name: str
    fund_class_type: str | None = None
    net_asset_value: float | None = None  # patrimonio liquido, from the fund's latest available Informe Diario snapshot
    n_shareholders: int | None = None  # numero de cotistas, same source
    financials_ref_date: date | None = None  # date those two figures are as-of — NOT necessarily the same month as equity holdings
    return_pct_12m: float | None = None  # retorno real (valor da cota) nos ultimos ~12 meses ate financials_ref_date
    return_pct_mtd: float | None = None  # retorno do mes corrente (ultima cota vs cota do fechamento do mes anterior)
    return_pct_ytd: float | None = None  # retorno acumulado no ano (ultima cota vs fechamento de dezembro do ano anterior)

    class Config:
        from_attributes = True


class HoldingOut(BaseModel):
    asset_id: int
    ticker: str
    company_name: str | None = None
    quantity: float
    market_value: float
    pct_of_equity_book: float | None = None  # % relative to this fund's total equities-only book (Phase 1 caveat, see docs)
    ref_date: date  # which month this snapshot is from — may lag behind "now" if the fund hasn't filed recently


class MovementOut(BaseModel):
    asset_id: int
    ticker: str
    classification: str
    ref_date: date
    prior_ref_date: date | None
    qty_current: float
    qty_prior: float
    value_current: float
    value_prior: float
    qty_delta: float
    value_delta: float
    pct_delta: float | None


class AssetHistoryPoint(BaseModel):
    ref_date: date
    quantity: float
    market_value: float
    classification: str | None = None
    qty_delta: float | None = None
    pct_of_fund: float | None = None  # % do PL do fundo nessa data (mesma logica de get_asset_holders)
