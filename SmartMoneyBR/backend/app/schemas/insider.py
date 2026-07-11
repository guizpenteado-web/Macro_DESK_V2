from datetime import date

from pydantic import BaseModel


class InsiderTradeOut(BaseModel):
    id: int
    cnpj_companhia: str
    company_name: str
    ticker: str | None = None
    data_referencia: date
    tipo_empresa: str | None = None
    empresa: str | None = None
    tipo_cargo: str | None = None
    tipo_movimentacao: str
    direction: str | None = None
    tipo_operacao: str | None = None
    tipo_ativo: str | None = None
    intermediario: str | None = None
    data_movimentacao: date | None = None
    quantidade: float | None = None
    preco_unitario: float | None = None
    volume: float | None = None

    class Config:
        from_attributes = True
