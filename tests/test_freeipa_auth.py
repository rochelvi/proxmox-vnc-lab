from unittest.mock import MagicMock, patch

from sqlalchemy import select

from app.auth_providers import FreeIPAAuthProvider, get_auth_provider
from app.config import Settings
from app.models import User


def test_get_auth_provider_freeipa(db_session):
    provider = get_auth_provider("freeipa", db_session)
    assert isinstance(provider, FreeIPAAuthProvider)
    ldap_provider = get_auth_provider("ldap", db_session)
    assert isinstance(ldap_provider, FreeIPAAuthProvider)


@patch("app.auth_providers.Connection")
def test_freeipa_direct_bind_success(mock_conn_cls, db_session):
    mock_conn = MagicMock()
    mock_conn.bind.return_value = True
    mock_conn_cls.return_value = mock_conn

    settings = Settings(
        freeipa_server="ipa.test.local",
        freeipa_base_dn="dc=test,dc=local",
        freeipa_auto_create_user=False,
    )
    provider = FreeIPAAuthProvider(db_session, settings=settings)

    # "owner" exists in db_session fixture
    user = provider.authenticate("owner", "secret123")
    assert user is not None
    assert user.username == "owner"
    assert mock_conn_cls.called
    server_arg = mock_conn_cls.call_args[0][0]
    assert server_arg.host == "ipa.test.local"
    assert mock_conn_cls.call_args[1] == {
        "user": "uid=owner,cn=users,cn=accounts,dc=test,dc=local",
        "password": "secret123",
        "auto_bind": False,
    }
    mock_conn.bind.assert_called_once()


@patch("app.auth_providers.Connection")
def test_freeipa_direct_bind_invalid_password(mock_conn_cls, db_session):
    mock_conn = MagicMock()
    mock_conn.bind.return_value = False
    mock_conn.result = {"description": "invalidCredentials"}
    mock_conn_cls.return_value = mock_conn

    settings = Settings(
        freeipa_server="ipa.test.local",
        freeipa_base_dn="dc=test,dc=local",
        freeipa_auto_create_user=False,
    )
    provider = FreeIPAAuthProvider(db_session, settings=settings)

    user = provider.authenticate("owner", "wrongpassword")
    assert user is None


@patch("app.auth_providers.Connection")
def test_freeipa_nonexistent_local_user_rejected_when_auto_create_disabled(mock_conn_cls, db_session):
    settings = Settings(
        freeipa_server="ipa.test.local",
        freeipa_base_dn="dc=test,dc=local",
        freeipa_auto_create_user=False,
    )
    provider = FreeIPAAuthProvider(db_session, settings=settings)

    user = provider.authenticate("nonexistent", "secret123")
    assert user is None
    # Connection should not even be attempted if user is not in local DB
    mock_conn_cls.assert_not_called()


@patch("app.auth_providers.Connection")
def test_freeipa_auto_create_user_when_enabled(mock_conn_cls, db_session):
    mock_conn = MagicMock()
    mock_conn.bind.return_value = True
    mock_conn_cls.return_value = mock_conn

    settings = Settings(
        freeipa_server="ipa.test.local",
        freeipa_base_dn="dc=test,dc=local",
        freeipa_auto_create_user=True,
    )
    provider = FreeIPAAuthProvider(db_session, settings=settings)

    user = provider.authenticate("newuser", "secret123")
    assert user is not None
    assert user.username == "newuser"

    # Verify it was saved to db
    db_user = db_session.scalar(select(User).where(User.username == "newuser"))
    assert db_user is not None
    assert db_user.username == "newuser"


@patch("app.auth_providers.Connection")
def test_freeipa_service_bind_search_and_admin_group(mock_conn_cls, db_session):
    search_conn = MagicMock()
    search_conn.bind.return_value = True
    entry_mock = MagicMock()
    entry_mock.entry_dn = "uid=owner,cn=users,cn=accounts,dc=test,dc=local"
    member_of_mock = MagicMock()
    member_of_mock.values = ["cn=admins,cn=groups,cn=accounts,dc=test,dc=local"]
    entry_mock.memberOf = member_of_mock
    search_conn.entries = [entry_mock]

    user_conn = MagicMock()
    user_conn.bind.return_value = True

    mock_conn_cls.side_effect = [search_conn, user_conn]

    settings = Settings(
        freeipa_server="ipa.test.local",
        freeipa_base_dn="dc=test,dc=local",
        freeipa_bind_dn="uid=binduser,cn=sysaccounts,cn=etc,dc=test,dc=local",
        freeipa_bind_password="bindsecret",
        freeipa_admin_group="admins",
    )
    provider = FreeIPAAuthProvider(db_session, settings=settings)

    user = provider.authenticate("owner", "secret123")
    assert user is not None
    assert user.username == "owner"
    assert user.is_admin is True


@patch("app.auth_providers.Connection")
def test_freeipa_ldap_exception_handling(mock_conn_cls, db_session):
    from ldap3.core.exceptions import LDAPSocketOpenError

    mock_conn = MagicMock()
    mock_conn.bind.side_effect = LDAPSocketOpenError("Connection refused")
    mock_conn_cls.return_value = mock_conn

    settings = Settings(
        freeipa_server="ipa.test.local",
        freeipa_base_dn="dc=test,dc=local",
    )
    provider = FreeIPAAuthProvider(db_session, settings=settings)
    user = provider.authenticate("owner", "secret123")
    assert user is None


def test_freeipa_empty_credentials(db_session):
    provider = FreeIPAAuthProvider(db_session)
    assert provider.authenticate("", "") is None
    assert provider.authenticate("owner", "") is None
    assert provider.authenticate("", "password") is None


@patch("app.auth_providers.Connection")
def test_freeipa_start_tls(mock_conn_cls, db_session):
    mock_conn = MagicMock()
    mock_conn.bind.return_value = True
    mock_conn_cls.return_value = mock_conn

    settings = Settings(
        freeipa_server="ipa.test.local",
        freeipa_base_dn="dc=test,dc=local",
        freeipa_use_ssl=False,
        freeipa_start_tls=True,
    )
    provider = FreeIPAAuthProvider(db_session, settings=settings)
    user = provider.authenticate("owner", "secret123")
    assert user is not None
    mock_conn.open.assert_called_once()
    mock_conn.start_tls.assert_called_once()


@patch("app.auth_providers.Connection")
def test_freeipa_api_login_integration(mock_conn_cls, client):
    test_client, _, session_factory = client

    mock_conn = MagicMock()
    mock_conn.bind.return_value = True
    mock_conn_cls.return_value = mock_conn

    with patch("app.routers.auth.get_settings") as mock_get_settings:
        mock_get_settings.return_value = Settings(
            auth_provider="freeipa",
            freeipa_server="ipa.test.local",
            freeipa_base_dn="dc=test,dc=local",
        )
        response = test_client.post(
            "/api/auth/login",
            json={"username": "intern", "password": "ldap-password"},
        )
        assert response.status_code == 200
        assert "access_token" in response.json()
