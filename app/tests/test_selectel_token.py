from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import httpx
import pytest

from app.selectel_client import SelectelAuthError, SelectelClient
from app.services.selectel_token_service import (
    TokenPersistence,
    calculate_token_expires_at,
    is_token_valid,
)


BALANCES_URL = "https://api.selectel.ru/v4/balances"
IDENTITY_URL = "https://cloud.api.selcloud.ru/identity/v3/auth/tokens"
BALANCES_PAYLOAD = {"status": "success", "data": {"agreements": [], "settings": {}}}


def _is_identity_request(request: httpx.Request) -> bool:
    url = httpx.URL(IDENTITY_URL)
    return (
        request.url.scheme == url.scheme
        and request.url.host == url.host
        and request.url.path == url.path
    )


def _make_client(
    *,
    credentials: MagicMock,
    db: MagicMock,
    handler,
    user_id: str = "user-1",
) -> SelectelClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return SelectelClient(
        account_id="12345",
        service_user_name="svc-user",
        service_user_password="password",
        identity_url=IDENTITY_URL,
        balances_url=BALANCES_URL,
        token_persistence=TokenPersistence(
            user_id=user_id,
            credentials=credentials,
            db=db,
        ),
        http_client=http_client,
    )


def test_uses_cached_token() -> None:
    db = MagicMock()
    credentials = MagicMock()
    credentials.selectel_token = "cached-token"
    credentials.selectel_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=10)
    identity_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal identity_calls
        if _is_identity_request(request):
            identity_calls += 1
            return httpx.Response(200, headers={"X-Subject-Token": "new-token"})
        assert request.headers["x-auth-token"] == "cached-token"
        return httpx.Response(200, json=BALANCES_PAYLOAD)

    client = _make_client(credentials=credentials, db=db, handler=handler)
    result = client.get_balances()

    assert identity_calls == 0
    assert result == BALANCES_PAYLOAD


def test_refreshes_when_token_missing() -> None:
    db = MagicMock()
    credentials = MagicMock()
    credentials.selectel_token = None
    credentials.selectel_token_expires_at = None
    identity_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal identity_calls
        if _is_identity_request(request):
            identity_calls += 1
            return httpx.Response(200, headers={"X-Subject-Token": "fresh-token"})
        assert request.headers["x-auth-token"] == "fresh-token"
        return httpx.Response(200, json=BALANCES_PAYLOAD)

    client = _make_client(credentials=credentials, db=db, handler=handler)
    client.get_balances()

    assert identity_calls == 1
    assert credentials.selectel_token is not None
    assert credentials.selectel_token_expires_at is not None
    db.commit.assert_called()


def test_refreshes_when_token_expires_soon() -> None:
    db = MagicMock()
    credentials = MagicMock()
    credentials.selectel_token = "old-token"
    credentials.selectel_token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    identity_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal identity_calls
        if _is_identity_request(request):
            identity_calls += 1
            return httpx.Response(200, headers={"X-Subject-Token": "fresh-token"})
        assert request.headers["x-auth-token"] == "fresh-token"
        return httpx.Response(200, json=BALANCES_PAYLOAD)

    client = _make_client(credentials=credentials, db=db, handler=handler)
    client.get_balances()

    assert identity_calls == 1


def test_auto_refresh_after_401() -> None:
    db = MagicMock()
    credentials = MagicMock()
    credentials.selectel_token = "stale-token"
    credentials.selectel_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=10)
    balance_calls = 0
    identity_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal balance_calls, identity_calls
        if _is_identity_request(request):
            identity_calls += 1
            return httpx.Response(200, headers={"X-Subject-Token": "fresh-token"})
        balance_calls += 1
        if balance_calls == 1:
            assert request.headers["x-auth-token"] == "stale-token"
            return httpx.Response(401)
        assert request.headers["x-auth-token"] == "fresh-token"
        return httpx.Response(200, json=BALANCES_PAYLOAD)

    client = _make_client(credentials=credentials, db=db, handler=handler)
    result = client.get_balances()

    assert identity_calls == 1
    assert balance_calls == 2
    assert result == BALANCES_PAYLOAD


def test_error_when_401_after_refresh() -> None:
    db = MagicMock()
    credentials = MagicMock()
    credentials.selectel_token = "stale-token"
    credentials.selectel_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=10)

    def handler(request: httpx.Request) -> httpx.Response:
        if _is_identity_request(request):
            return httpx.Response(200, headers={"X-Subject-Token": "fresh-token"})
        return httpx.Response(401)

    client = _make_client(credentials=credentials, db=db, handler=handler)

    with pytest.raises(SelectelAuthError):
        client.get_balances()


def test_adds_utm_source_to_all_requests() -> None:
    db = MagicMock()
    credentials = MagicMock()
    credentials.selectel_token = None
    credentials.selectel_token_expires_at = None
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if _is_identity_request(request):
            return httpx.Response(200, headers={"X-Subject-Token": "fresh-token"})
        return httpx.Response(200, json=BALANCES_PAYLOAD)

    client = _make_client(credentials=credentials, db=db, handler=handler)
    client.get_balances()

    assert len(requests) == 2
    for request in requests:
        assert dict(request.url.params) == {"utm_source": "mcp_ed"}


def test_calculate_token_expires_at() -> None:
    now = datetime(2026, 6, 9, 12, 0, 0, tzinfo=timezone.utc)
    expires_at = calculate_token_expires_at(now)

    assert expires_at == now + timedelta(hours=23)
    assert is_token_valid(expires_at, now=now) is True
    assert is_token_valid(now + timedelta(minutes=30), now=now) is False
    assert is_token_valid(None, now=now) is False
