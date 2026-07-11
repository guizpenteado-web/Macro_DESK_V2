from datetime import date

from pydantic import BaseModel


class AssetOut(BaseModel):
    id: int
    ticker: str
    company_name: str | None = None
    asset_type: str = "equity"  # "equity" | "bdr"
    total_market_value: float | None = None  # valor total em carteira, somado entre todos os fundos que detem o ativo
    financials_ref_date: date | None = None  # mes de referencia desse valor
    return_pct_12m: float | None = None  # retorno implicito do preco (valor/qtd agregados) nos ultimos ~12 meses

    class Config:
        from_attributes = True


class AssetHolderOut(BaseModel):
    fund_id: int
    fund_name: str
    fund_cnpj: str
    quantity: float
    market_value: float
    classification: str | None = None
    qty_delta: float | None = None
    ref_date: date  # data de divulgacao desta posicao especifica
    fund_net_asset_value: float | None = None  # patrimonio liquido total do fundo (nao so a posicao neste ativo)
    fund_n_shareholders: int | None = None


class AssetTimelinePoint(BaseModel):
    ref_date: date
    n_holders: int
    total_quantity: float
    total_value: float


class RankingRow(BaseModel):
    asset_id: int
    ticker: str
    company_name: str | None = None
    n_funds: int
    net_qty_delta: float
    net_value_delta: float
