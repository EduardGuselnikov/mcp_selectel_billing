from unittest.mock import MagicMock

import httpx

from app.selectel_client import SelectelClient


def _make_client() -> SelectelClient:
    http_client = MagicMock(spec=httpx.Client)
    client = SelectelClient(
        account_id="12345",
        service_user_name="svc-user",
        service_user_password="password",
        http_client=http_client,
    )
    client.get_valid_token = MagicMock(return_value="test-token")
    return client


def _mock_response(status_code: int, json_data: dict) -> httpx.Response:
    return httpx.Response(status_code=status_code, json=json_data)


def test_get_cards() -> None:
    client = _make_client()
    client._http_client.request.return_value = _mock_response(
        200,
        {"success": True, "data": [{"id": 60880, "state": 1}]},
    )

    result = client.get_cards()

    assert result["data"][0]["id"] == 60880
    client._http_client.request.assert_called_once()
    call_kwargs = client._http_client.request.call_args.kwargs
    assert call_kwargs["headers"]["x-auth-token"] == "test-token"
    assert call_kwargs["headers"]["User-Agent"] == "selectel-mcp-billing/mcp_ed"
    assert call_kwargs["headers"]["X-Client-Source"] == "mcp_ed"


def test_pay_with_saved_card() -> None:
    client = _make_client()
    client._http_client.request.return_value = _mock_response(
        200,
        {"status": "success", "payment_id": "abc123"},
    )

    result = client.pay_with_saved_card(123, 10000)

    assert result["payment_id"] == "abc123"
    call_args = client._http_client.request.call_args
    assert call_args.args[0] == "POST"
    assert call_args.args[1].endswith("/123/pay")
    assert call_args.kwargs["json"] == {"amount": 10000}
    assert call_args.kwargs["headers"]["X-Client-Source"] == "mcp_ed"


def test_init_payment_form_encoded() -> None:
    client = _make_client()
    client._http_client.request.return_value = _mock_response(
        200,
        {"redirect": {"url": "https://pay.example.com"}},
    )

    result = client.init_payment(
        payment_id=38,
        payment_type=38,
        amount_kopecks=10000,
        bind=1,
        pay="by_blank",
    )

    assert result["redirect"]["url"] == "https://pay.example.com"
    call_kwargs = client._http_client.request.call_args.kwargs
    assert call_kwargs["data"] == {
        "id": "38",
        "type": "38",
        "amount": "10000",
        "bind": "1",
        "pay": "by_blank",
    }
    assert call_kwargs["headers"]["Content-Type"] == "application/x-www-form-urlencoded"


def test_check_payment_external_status() -> None:
    client = _make_client()
    client._http_client.request.return_value = _mock_response(
        200,
        {"external_info": {"status": "SUCCESS"}},
    )

    result = client.check_payment_external_status("tx_123")

    assert result["external_info"]["status"] == "SUCCESS"
    call_kwargs = client._http_client.request.call_args.kwargs
    assert call_kwargs["json"] == {"transaction_id": "tx_123"}


def test_save_bill_email() -> None:
    client = _make_client()
    client._http_client.request.return_value = _mock_response(200, {"status": "updated"})

    result = client.save_bill_email("order_123", "user@example.com")

    assert result["status"] == "updated"
    call_args = client._http_client.request.call_args
    assert call_args.args[0] == "PUT"
    assert call_args.args[1].endswith("/order_123")
    assert call_args.kwargs["json"] == {"email": "user@example.com"}
