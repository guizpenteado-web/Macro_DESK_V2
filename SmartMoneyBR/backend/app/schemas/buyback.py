from datetime import date

from pydantic import BaseModel


class BuybackOut(BaseModel):
    id: int
    cnpj: str
    company_name: str
    ticker: str | None = None
    declared_at: date
    deadline: date | None = None
    status: str
    operation_type: str | None = None
    reason: str | None = None
    purpose: str | None = None
    qty_common_shares: float | None = None
    qty_preferred_shares: float | None = None

    class Config:
        from_attributes = True
