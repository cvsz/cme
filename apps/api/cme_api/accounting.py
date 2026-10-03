from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from cme_api.auth import Principal
from cme_api.models import ChartAccount

class AccountingError(ValueError):
    pass

def list_accounts(db: Session, principal: Principal) -> list[ChartAccount]:
    if principal.organization_id is None:
        raise AccountingError("organization is required")
    return list(db.scalars(select(ChartAccount).where(ChartAccount.tenant_id==principal.tenant_id,ChartAccount.organization_id==principal.organization_id).order_by(ChartAccount.code)).all())

def assert_balanced(lines: list[tuple[Decimal,Decimal]]) -> None:
    if len(lines)<2:
        raise AccountingError("journal entry requires at least two lines")
    debit=sum((d for d,_ in lines),Decimal("0"))
    credit=sum((c for _,c in lines),Decimal("0"))
    if debit!=credit:
        raise AccountingError("journal entry is not balanced")
