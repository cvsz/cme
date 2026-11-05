from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from cme_api.auth import Principal
from cme_api.models import ChartAccount, JournalEntry, JournalLine


class AccountingError(ValueError):
    pass


_CENT = Decimal("0.01")


def _journal_request_signature(
    description: str, lines: Iterable[tuple[UUID, Decimal, Decimal]]
) -> tuple[str, tuple[tuple[str, Decimal, Decimal], ...]]:
    return description, tuple(
        sorted((str(account_id), debit, credit) for account_id, debit, credit in lines)
    )


def _money(value: Decimal) -> Decimal:
    if not value.is_finite() or value.quantize(_CENT) != value:
        raise AccountingError("journal amounts require at most two decimal places")
    return value


def list_accounts(db: Session, principal: Principal) -> list[ChartAccount]:
    if principal.organization_id is None:
        raise AccountingError("organization is required")
    statement = (
        select(ChartAccount)
        .where(
            ChartAccount.tenant_id == principal.tenant_id,
            ChartAccount.organization_id == principal.organization_id,
        )
        .order_by(ChartAccount.code)
    )
    return list(db.scalars(statement).all())


def assert_balanced(lines: list[tuple[Decimal, Decimal]]) -> None:
    if len(lines) < 2:
        raise AccountingError("journal entry requires at least two lines")
    debit = sum((_money(debit) for debit, _ in lines), Decimal(0))
    credit = sum((_money(credit) for _, credit in lines), Decimal(0))
    if debit != credit:
        raise AccountingError("journal entry is not balanced")


def post_journal(
    db: Session,
    principal: Principal,
    *,
    idempotency_key: str,
    description: str,
    lines: list[tuple[ChartAccount, Decimal, Decimal]],
) -> JournalEntry:
    if principal.organization_id is None:
        raise AccountingError("organization is required")
    if not idempotency_key or len(idempotency_key) > 128:
        raise AccountingError("invalid idempotency key")

    normalized = [(account, _money(debit), _money(credit)) for account, debit, credit in lines]
    assert_balanced([(debit, credit) for _, debit, credit in normalized])
    for account, debit, credit in normalized:
        if (
            account.tenant_id != principal.tenant_id
            or account.organization_id != principal.organization_id
        ):
            raise AccountingError("account is outside principal scope")
        if debit < 0 or credit < 0 or (debit == 0) == (credit == 0):
            raise AccountingError("each line must contain exactly one positive side")

    statement = (
        insert(JournalEntry)
        .values(
            tenant_id=principal.tenant_id,
            organization_id=principal.organization_id,
            idempotency_key=idempotency_key,
            description=description,
        )
        .on_conflict_do_nothing(index_elements=["tenant_id", "organization_id", "idempotency_key"])
        .returning(JournalEntry.id)
    )
    entry_id = db.scalar(statement)
    if entry_id is None:
        existing = db.scalar(
            select(JournalEntry).where(
                JournalEntry.tenant_id == principal.tenant_id,
                JournalEntry.organization_id == principal.organization_id,
                JournalEntry.idempotency_key == idempotency_key,
            )
        )
        if existing is None:
            raise AccountingError("idempotent journal lookup failed")
        existing_lines = db.scalars(
            select(JournalLine).where(
                JournalLine.tenant_id == principal.tenant_id,
                JournalLine.organization_id == principal.organization_id,
                JournalLine.entry_id == existing.id,
            )
        ).all()
        requested_signature = _journal_request_signature(
            description,
            ((account.id, debit, credit) for account, debit, credit in normalized),
        )
        existing_signature = _journal_request_signature(
            existing.description,
            ((line.account_id, line.debit, line.credit) for line in existing_lines),
        )
        if existing_signature != requested_signature:
            raise AccountingError("idempotency key reused with a different journal request")
        return existing

    entry = db.get(JournalEntry, entry_id)
    if entry is None:
        raise AccountingError("journal creation failed")
    for account, debit, credit in normalized:
        db.add(
            JournalLine(
                tenant_id=principal.tenant_id,
                organization_id=principal.organization_id,
                entry_id=entry.id,
                account_id=account.id,
                debit=debit,
                credit=credit,
            )
        )
    db.flush()
    entry.posted_at = datetime.now(UTC)
    db.flush()
    return entry
