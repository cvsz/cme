from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, status

_hasher=PasswordHasher()

def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("password must contain at least 12 characters")
    return _hasher.hash(password)

def verify_password(password: str, encoded: str) -> bool:
    try:
        return _hasher.verify(encoded,password)
    except VerifyMismatchError:
        return False

def require_permission(granted: set[str], permission: str) -> None:
    if "*" not in granted and permission not in granted:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="forbidden")
