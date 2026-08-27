import ssl

from app.config import Settings
from app.routers.vnc import _websocket_ssl_context


def test_websocket_ssl_context_verifies_certificates_when_enabled():
    context = _websocket_ssl_context(Settings(pve_verify_ssl=True))
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED


def test_websocket_ssl_context_skips_verification_when_disabled():
    context = _websocket_ssl_context(Settings(pve_verify_ssl=False))
    assert context.check_hostname is False
    assert context.verify_mode == ssl.CERT_NONE
