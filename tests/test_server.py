"""Server safety and health behavior."""

import logging

import pytest
from starlette.testclient import TestClient

from mcp_builder.server import create_app, validate_public_bind


@pytest.mark.parametrize("address", ["127.0.0.1", "127.10.20.30", "::1", "[::1]", "localhost"])
def test_public_bind_accepts_loopback_only(address):
    """Local OpenCode connections remain valid for IPv4, IPv6, and localhost."""
    assert validate_public_bind(address) == address


@pytest.mark.parametrize("address", ["0.0.0.0", "192.168.1.10", "example.test", ""])
def test_public_bind_rejects_non_loopback_or_invalid_values(address):
    """An unauthenticated service cannot be intentionally published to the network."""
    with pytest.raises(RuntimeError, match="loopback|Non-loopback"):
        validate_public_bind(address)


def test_direct_non_loopback_listener_is_rejected_without_public_override(monkeypatch):
    """A direct run cannot bypass the loopback guard by changing only the listen host."""
    monkeypatch.delenv("MCP_PUBLIC_BIND_IP", raising=False)
    monkeypatch.setenv("MCP_LISTEN_HOST", "0.0.0.0")
    with pytest.raises(RuntimeError, match="Non-loopback"):
        validate_public_bind()


def test_health_failure_logs_only_exception_type(caplog):
    """Health failures never copy exception messages or secrets into logs."""
    secret = "never-log-this-secret"

    class BrokenStore:
        """Raise a credential-bearing error from the sanitized health boundary."""

        @staticmethod
        def status():
            """Simulate a failed status probe."""
            raise RuntimeError(secret)

    with caplog.at_level(logging.ERROR), TestClient(create_app(BrokenStore())) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["status"] == "unready"
    assert "error_type=RuntimeError" in caplog.text
    assert secret not in caplog.text
