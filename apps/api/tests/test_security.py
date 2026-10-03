import pytest
from cme_api.security import hash_password, verify_password

def test_password_hash_round_trip():
    encoded=hash_password("CMe-development-password")
    assert encoded != "CMe-development-password"
    assert verify_password("CMe-development-password",encoded)
    assert not verify_password("wrong-password",encoded)

def test_short_password_rejected():
    with pytest.raises(ValueError): hash_password("short")
