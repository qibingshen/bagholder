from datetime import UTC, datetime, timedelta

import pytest


def test_有效签名通过且_nonce_不能重放() -> None:
    from bagholder.integrations.vnpy_protocol import AuthenticatedProtocol, ReplayDetected

    protocol = AuthenticatedProtocol(secret=b"0123456789abcdef0123456789abcdef")
    now = datetime.now(UTC)
    message = protocol.sign(
        command="HEALTH",
        payload={},
        nonce="nonce-0001",
        now=now,
    )

    assert protocol.verify(message, now) == {}
    with pytest.raises(ReplayDetected):
        protocol.verify(message, now)


def test_超过十秒的请求被拒绝() -> None:
    from bagholder.integrations.vnpy_protocol import AuthenticatedProtocol

    protocol = AuthenticatedProtocol(secret=b"0123456789abcdef0123456789abcdef")
    signed_at = datetime.now(UTC)
    message = protocol.sign(
        command="HEALTH",
        payload={},
        nonce="nonce-0002",
        now=signed_at,
    )

    with pytest.raises(PermissionError, match="时间窗口"):
        protocol.verify(message, signed_at + timedelta(seconds=11))
