from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest

from cme_api.accounting import (
    AccountingError,
    _journal_request_signature,
    assert_balanced,
    post_journal,
)
from cme_api.auth import Principal


def test_balanced_journal():
    assert_balanced([(Decimal(100), Decimal(0)), (Decimal(0), Decimal(100))])


def test_unbalanced_journal_rejected():
    with pytest.raises(AccountingError):
        assert_balanced([(Decimal(100), Decimal(0)), (Decimal(0), Decimal(99))])


def test_journal_idempotency_signature_accepts_reordered_equivalent_lines():
    description = "Invoice 123"
    debit_account = UUID("00000000-0000-0000-0000-000000000001")
    credit_account = UUID("00000000-0000-0000-0000-000000000002")
    debit = (debit_account, Decimal("100.00"), Decimal("0.00"))
    credit = (credit_account, Decimal("0.00"), Decimal("100.00"))

    assert _journal_request_signature(description, [debit, credit]) == _journal_request_signature(
        description, [credit, debit]
    )


def test_journal_idempotency_signature_rejects_changed_payload():
    original = _journal_request_signature(
        "Invoice 123",
        [(UUID(int=1), Decimal("100.00"), Decimal("0.00"))],
    )
    changed_description = _journal_request_signature(
        "Invoice 124",
        [(UUID(int=1), Decimal("100.00"), Decimal("0.00"))],
    )
    changed_amount = _journal_request_signature(
        "Invoice 123",
        [(UUID(int=1), Decimal("99.00"), Decimal("0.00"))],
    )

    assert original != changed_description
    assert original != changed_amount


def test_post_journal_rejects_reused_key_with_different_request():
    tenant_id = UUID(int=1)
    organization_id = UUID(int=2)
    debit_account = SimpleNamespace(
        id=UUID(int=3), tenant_id=tenant_id, organization_id=organization_id
    )
    credit_account = SimpleNamespace(
        id=UUID(int=4), tenant_id=tenant_id, organization_id=organization_id
    )
    existing = SimpleNamespace(id=UUID(int=5), description="Original request")
    db = Mock()
    db.scalar.side_effect = (None, existing)
    db.scalars.return_value.all.return_value = [
        SimpleNamespace(account_id=debit_account.id, debit=Decimal(100), credit=Decimal(0)),
        SimpleNamespace(account_id=credit_account.id, debit=Decimal(0), credit=Decimal(100)),
    ]
    principal = Principal(
        user_id=UUID(int=6),
        tenant_id=tenant_id,
        organization_id=organization_id,
        roles=frozenset(),
        permissions=frozenset(),
    )

    with pytest.raises(AccountingError, match="different journal request"):
        post_journal(
            db,
            principal,
            idempotency_key="request-1",
            description="Changed request",
            lines=[
                (debit_account, Decimal(100), Decimal(0)),
                (credit_account, Decimal(0), Decimal(100)),
            ],
        )
