from app.services.balance_formatter import format_balances_response


def _sample_response(
    *,
    agreements: list | None = None,
    currency: str = "rub",
    mode: str = "prepay",
) -> dict:
    if agreements is None:
        agreements = [
            {
                "agreement_id": 263632,
                "available_billings": ["primary"],
                "billings": [
                    {
                        "available_balances": ["bonus", "vk_rub", "main"],
                        "balances": [
                            {"balance_id": 2509963, "balance_type": "bonus", "value": 3661464},
                            {"balance_id": 2509965, "balance_type": "vk_rub", "value": 0},
                            {"balance_id": 2509967, "balance_type": "main", "value": 514},
                        ],
                        "balances_values_sum": 3661978,
                        "billing_type": "primary",
                        "debt": [],
                        "debt_sum": 0,
                        "final_sum": 3661978,
                    }
                ],
            }
        ]

    return {
        "status": "success",
        "data": {
            "agreements": agreements,
            "settings": {
                "currency": currency,
                "full_user": True,
                "mode": mode,
            },
        },
    }


def test_successful_response() -> None:
    result = format_balances_response(_sample_response())

    assert "На аккаунте Selectel найдены балансы в валюте RUB." in result
    assert "ID договора: 263632, тип биллинга: primary" in result
    assert "• Бонусный баланс: 36 614,64 ₽" in result
    assert "• VK-баланс: 0 ₽" in result
    assert "• Основной баланс: 5,14 ₽" in result
    assert "Сумма балансов: 36 619,78 ₽" in result
    assert "Задолженность: 0 ₽" in result
    assert "Итоговый доступный баланс: 36 619,78 ₽" in result
    assert "Режим оплаты: prepay" in result


def test_multiple_balances() -> None:
    response = _sample_response()
    response["data"]["agreements"].append(
        {
            "agreement_id": 999999,
            "billings": [
                {
                    "billing_type": "secondary",
                    "balances": [
                        {"balance_type": "main", "value": 10000},
                    ],
                    "balances_values_sum": 10000,
                    "debt_sum": 0,
                    "final_sum": 10000,
                }
            ],
        }
    )

    result = format_balances_response(response)

    assert "ID договора: 263632" in result
    assert "ID договора: 999999, тип биллинга: secondary" in result
    assert "• Основной баланс: 100,00 ₽" in result


def test_empty_agreements() -> None:
    result = format_balances_response(_sample_response(agreements=[]))

    assert result == "По аккаунту не найдено договоров (agreement_id) с балансами."


def test_empty_balances() -> None:
    response = _sample_response(
        agreements=[
            {
                "agreement_id": 12345,
                "billings": [
                    {
                        "billing_type": "primary",
                        "balances": [],
                        "balances_values_sum": 0,
                        "debt_sum": 0,
                        "final_sum": 0,
                    }
                ],
            }
        ]
    )

    result = format_balances_response(response)

    assert "Для ID договора: 12345 не найдено доступных балансов." in result


def test_unknown_balance_type() -> None:
    response = _sample_response(
        agreements=[
            {
                "agreement_id": 1,
                "billings": [
                    {
                        "billing_type": "primary",
                        "balances": [{"balance_type": "custom_type", "value": 500}],
                        "balances_values_sum": 500,
                        "debt_sum": 0,
                        "final_sum": 500,
                    }
                ],
            }
        ]
    )

    result = format_balances_response(response)

    assert "• custom_type: 5,00 ₽" in result


def test_missing_currency() -> None:
    response = _sample_response()
    del response["data"]["settings"]["currency"]

    result = format_balances_response(response)

    assert "На аккаунте Selectel найдены балансы в валюте RUB." in result
    assert "• Бонусный баланс: 36 614,64 ₽" in result


def test_zero_value() -> None:
    response = _sample_response(
        agreements=[
            {
                "agreement_id": 1,
                "billings": [
                    {
                        "billing_type": "primary",
                        "balances": [{"balance_type": "main", "value": 0}],
                        "balances_values_sum": 0,
                        "debt_sum": 0,
                        "final_sum": 0,
                    }
                ],
            }
        ]
    )

    result = format_balances_response(response)

    assert "• Основной баланс: 0 ₽" in result


def test_debt_sum_greater_than_zero() -> None:
    response = _sample_response(
        agreements=[
            {
                "agreement_id": 1,
                "billings": [
                    {
                        "billing_type": "primary",
                        "balances": [{"balance_type": "main", "value": 100000}],
                        "balances_values_sum": 100000,
                        "debt_sum": 25000,
                        "final_sum": 75000,
                    }
                ],
            }
        ]
    )

    result = format_balances_response(response)

    assert "Задолженность: 250,00 ₽" in result
    assert "Итоговый доступный баланс: 750,00 ₽" in result
