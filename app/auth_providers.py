from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.security import verify_password


class AuthProvider(Protocol):
    def authenticate(self, username: str, password: str) -> User | None:
        """Return a local user for valid credentials, or None."""


class LocalAuthProvider:
    def __init__(self, db: Session):
        self.db = db

    def authenticate(self, username: str, password: str) -> User | None:
        user = self.db.scalar(select(User).where(User.username == username))
        if user and verify_password(password, user.password_hash):
            return user
        return None


# LDAP/OAuth providers can implement AuthProvider and be selected here later.
def get_auth_provider(name: str, db: Session) -> AuthProvider:
    if name.lower() == "local":
        return LocalAuthProvider(db)
    raise ValueError(f"Unsupported auth provider: {name}")
