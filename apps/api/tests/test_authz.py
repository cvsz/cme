from uuid import uuid4
import pytest
from fastapi import HTTPException
from cme_api.auth import Principal, require_permission

def test_permission_is_tenant_principal_scoped():
    p=Principal(uuid4(),uuid4(),None,frozenset({"viewer"}),frozenset({"inventory.read"}))
    assert require_permission(p,"inventory.read") is p
    with pytest.raises(HTTPException): require_permission(p,"inventory.write")
