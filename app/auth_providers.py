import logging
import ssl
from typing import Protocol

import ldap3
from ldap3 import ALL, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import User
from app.security import verify_password

logger = logging.getLogger(__name__)


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


class FreeIPAAuthProvider:
    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()

    def _get_server(self) -> Server:
        tls = None
        if self.settings.freeipa_use_ssl or self.settings.freeipa_start_tls:
            tls = Tls(
                validate=ssl.CERT_REQUIRED if self.settings.freeipa_verify_ssl else ssl.CERT_NONE
            )
        return Server(
            host=self.settings.freeipa_server,
            port=self.settings.freeipa_port,
            use_ssl=self.settings.freeipa_use_ssl,
            tls=tls,
            get_info=ALL,
            connect_timeout=10,
        )

    def _check_admin(self, member_of_list: list[str]) -> bool:
        admin_group = self.settings.freeipa_admin_group
        if not admin_group:
            return False
        admin_group_lower = admin_group.lower()
        base_dn = self.settings.freeipa_base_dn
        group_base_dn = (
            self.settings.freeipa_group_base_dn or f"cn=groups,cn=accounts,{base_dn}"
        ).lower()
        full_admin_dn = (
            admin_group_lower
            if admin_group_lower.startswith("cn=")
            else f"cn={admin_group_lower},{group_base_dn}"
        )
        for member in member_of_list:
            m_lower = str(member).lower()
            if m_lower == full_admin_dn or m_lower == admin_group_lower or f"cn={admin_group_lower}," in m_lower:
                return True
        return False

    def authenticate(self, username: str, password: str) -> User | None:
        if not username or not password:
            return None

        user = self.db.scalar(select(User).where(User.username == username))
        if user is None and not self.settings.freeipa_auto_create_user:
            logger.warning("FreeIPA auth rejected: user '%s' does not exist in local database", username)
            return None

        server = self._get_server()
        base_dn = self.settings.freeipa_base_dn
        user_base_dn = self.settings.freeipa_user_base_dn or f"cn=users,cn=accounts,{base_dn}"
        user_dn = None
        member_of: list[str] = []

        try:
            if self.settings.freeipa_bind_dn and self.settings.freeipa_bind_password:
                # 1. Search for user using service account bind
                search_conn = Connection(
                    server,
                    user=self.settings.freeipa_bind_dn,
                    password=self.settings.freeipa_bind_password,
                    auto_bind=False,
                )
                if self.settings.freeipa_start_tls:
                    search_conn.open()
                    search_conn.start_tls()
                if not search_conn.bind():
                    logger.error("FreeIPA service bind failed: %s", search_conn.result)
                    return None

                escaped_user = escape_filter_chars(username)
                user_filter = self.settings.freeipa_user_filter.format(username=escaped_user)
                search_conn.search(
                    search_base=user_base_dn,
                    search_filter=user_filter,
                    attributes=["dn", "memberOf"],
                )
                if not search_conn.entries:
                    logger.warning("FreeIPA user '%s' not found in search", username)
                    search_conn.unbind()
                    return None

                entry = search_conn.entries[0]
                user_dn = entry.entry_dn
                if hasattr(entry, "memberOf") and entry.memberOf:
                    member_of = list(entry.memberOf.values)
                search_conn.unbind()
            else:
                # 2. Derive user DN directly
                if self.settings.freeipa_user_dn_template:
                    user_dn = self.settings.freeipa_user_dn_template.format(
                        username=username,
                        base_dn=base_dn,
                        user_base_dn=user_base_dn,
                    )
                else:
                    user_dn = f"uid={username},{user_base_dn}"

            # 3. Authenticate user credentials by binding with user DN
            user_conn = Connection(
                server,
                user=user_dn,
                password=password,
                auto_bind=False,
            )
            if self.settings.freeipa_start_tls:
                user_conn.open()
                user_conn.start_tls()
            if not user_conn.bind():
                logger.warning("FreeIPA user bind failed for '%s': %s", username, user_conn.result)
                return None

            # If service bind wasn't used and admin group is configured, read user's memberOf
            if not member_of and self.settings.freeipa_admin_group:
                user_conn.search(
                    search_base=user_dn,
                    search_filter="(objectClass=*)",
                    search_scope=ldap3.BASE,
                    attributes=["memberOf"],
                )
                if user_conn.entries and hasattr(user_conn.entries[0], "memberOf"):
                    member_of = list(user_conn.entries[0].memberOf.values)

            user_conn.unbind()

        except LDAPException as exc:
            logger.error("FreeIPA LDAP error during authentication for '%s': %s", username, exc)
            return None
        except Exception as exc:
            logger.error("Unexpected error during FreeIPA authentication for '%s': %s", username, exc)
            return None

        is_admin = self._check_admin(member_of) if self.settings.freeipa_admin_group else None

        # Manage local database user record
        if user is None:
            user = User(
                username=username,
                password_hash="",
                is_admin=bool(is_admin),
            )
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
        elif is_admin is not None and user.is_admin != is_admin:
            user.is_admin = is_admin
            self.db.commit()
            self.db.refresh(user)

        return user


def get_auth_provider(name: str, db: Session) -> AuthProvider:
    provider_name = name.lower()
    if provider_name == "local":
        return LocalAuthProvider(db)
    if provider_name in ("freeipa", "ldap"):
        return FreeIPAAuthProvider(db)
    raise ValueError(f"Unsupported auth provider: {name}")

