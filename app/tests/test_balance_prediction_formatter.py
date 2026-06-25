from app.services.balance_formatter import (
    format_balance_prediction_response,
    format_prediction_hours,
)


def test_format_prediction_hours() -> None:
    assert format_prediction_hours(None) == "нет активных услуг"
    assert format_prediction_hours(0) == "средств недостаточно"
    assert format_prediction_hours(5) == "5 ч."
    assert format_prediction_hours(24) == "1 дн."
    assert format_prediction_hours(100) == "4 дн. 4 ч."


def test_format_balance_prediction_response() -> None:
    result = format_balance_prediction_response(
        {
            "status": "success",
            "data": {
                "primary": 100,
                "storage": None,
                "vmware": 24,
                "vpc": 5,
            },
        }
    )

    assert "Прогноз: на сколько хватит текущего баланса" in result
    assert "• Облачные серверы и основные услуги: 4 дн. 4 ч." in result
    assert "• Объектное хранилище: нет активных услуг" in result
    assert "• VMware: 1 дн." in result
    assert "• VPC: 5 ч." in result


def test_format_balance_prediction_empty_data() -> None:
    result = format_balance_prediction_response({"status": "success", "data": {}})

    assert result == "Прогноз расхода баланса недоступен."
