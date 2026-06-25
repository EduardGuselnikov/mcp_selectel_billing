from app.services.top_up_formatter import (
    AMOUNT_PROMPT,
    format_bank_transfer_payment,
    format_new_card_payment,
    format_payment_status,
    format_saved_card_confirmation,
    format_saved_card_list,
    format_saved_card_payment_success,
    format_sbp_payment,
    get_active_cards,
    rubles_to_kopecks,
    validate_amount_rub,
)


def test_validate_amount_rub_missing() -> None:
    assert validate_amount_rub(None) == AMOUNT_PROMPT


def test_validate_amount_rub_invalid() -> None:
    assert validate_amount_rub(0) == "Сумма пополнения должна быть больше нуля. Укажите сумму в рублях."
    assert validate_amount_rub(-10) == "Сумма пополнения должна быть больше нуля. Укажите сумму в рублях."
    assert validate_amount_rub(100) == "Минимальная сумма пополнения — 200 ₽. Укажите сумму не меньше 200 руб."
    assert validate_amount_rub(199.99) == "Минимальная сумма пополнения — 200 ₽. Укажите сумму не меньше 200 руб."


def test_validate_amount_rub_valid() -> None:
    assert validate_amount_rub(200) is None
    assert validate_amount_rub(500) is None


def test_rubles_to_kopecks() -> None:
    assert rubles_to_kopecks(100) == 10000
    assert rubles_to_kopecks(5.14) == 514


def test_get_active_cards_filters_by_state() -> None:
    response = {
        "success": True,
        "data": [
            {
                "id": 60880,
                "mask": "xxxx-xxxx-xxxx-9769",
                "state": 1,
                "card_type": "MasterCard",
                "bank": "T-Bank (Tinkoff)",
            },
            {"id": 456, "mask": "xxxx-xxxx-xxxx-5678", "state": 0, "card_type": "VISA"},
        ],
    }
    active = get_active_cards(response)
    assert len(active) == 1
    assert active[0]["id"] == 60880


def test_get_active_cards_legacy_cards_key() -> None:
    response = {
        "cards": [
            {"id": 123, "masked_pan": "**** 1234", "state": 1, "card_type": "VISA"},
        ]
    }
    active = get_active_cards(response)
    assert len(active) == 1
    assert active[0]["id"] == 123


def test_format_saved_card_list() -> None:
    cards = [
        {
            "id": 60880,
            "mask": "xxxx-xxxx-xxxx-9769",
            "state": 1,
            "card_type": "MasterCard",
            "bank": "T-Bank (Tinkoff)",
        }
    ]
    result = format_saved_card_list(cards)
    assert "Доступные сохранённые карты:" in result
    assert "ID 60880" in result
    assert "9769" in result
    assert "T-Bank" in result


def test_format_saved_card_confirmation() -> None:
    card = {"id": 123, "masked_pan": "**** 1234"}
    result = format_saved_card_confirmation(card, 10000)
    assert "100,00 ₽" in result
    assert "confirm=true" in result


def test_format_saved_card_payment_success() -> None:
    result = format_saved_card_payment_success({"payment_id": "abc123"}, 10000)
    assert "успешно пополнен" in result
    assert "abc123" in result


def test_format_new_card_payment() -> None:
    result = format_new_card_payment(
        {"redirect": {"url": "https://pay.example.com/abc"}, "payment_id": "abc"},
        10000,
    )
    assert "https://pay.example.com/abc" in result
    assert "платёжного шлюза" in result


def test_format_sbp_payment() -> None:
    result = format_sbp_payment(
        {
            "modal_window": {
                "qrUrl": "https://qr.example.com/abc",
                "url_for_mobile_app": "bankapp://pay/abc",
                "transaction_id": "tx_123",
            }
        },
        10000,
    )
    assert "https://qr.example.com/abc" in result
    assert "bankapp://pay/abc" in result
    assert "tx_123" in result
    assert "check_payment_status" in result


def test_format_bank_transfer_payment() -> None:
    result = format_bank_transfer_payment(
        {
            "order": {
                "order_id": "863020759",
                "transaction_id": "863020759",
                "payment_qr": "base64data",
            }
        },
        100000,
    )
    assert "https://api.selectel.ru/v1/billing/bill/863020759" in result
    assert "863020759" in result
    assert "панели управления Selectel" in result
    assert "base64data" not in result
    assert "сохранён" not in result


def test_format_payment_status() -> None:
    result = format_payment_status({"external_info": {"status": "SUCCESS"}}, "tx_123")
    assert "успешно оплачен" in result
    assert "tx_123" in result

    result_new = format_payment_status({"external_info": {"status": "NEW"}}, "tx_456")
    assert "ожидает оплаты" in result_new

    result_failed = format_payment_status({"external_info": {"status": "FAILED"}}, "tx_789")
    assert "не удался" in result_failed
