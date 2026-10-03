from decimal import Decimal
import pytest
from cme_api.accounting import AccountingError, assert_balanced

def test_balanced_journal():
    assert_balanced([(Decimal("100"),Decimal("0")),(Decimal("0"),Decimal("100"))])

def test_unbalanced_journal_rejected():
    with pytest.raises(AccountingError): assert_balanced([(Decimal("100"),Decimal("0")),(Decimal("0"),Decimal("99"))])
