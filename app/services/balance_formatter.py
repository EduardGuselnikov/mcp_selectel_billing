BALANCE_TYPE_LABELS: dict[str, str] = {
    "main": "Основной баланс",
    "bonus": "Бонусный баланс",
    "vk_rub": "VK-баланс",
}

CURRENCY_SYMBOLS: dict[str, str] = {
    "rub": "₽",
}


def _balance_label(balance_type: str) -> str:
    return BALANCE_TYPE_LABELS.get(balance_type, balance_type)


def _format_agreement_id(agreement_id: object) -> str:
    return f"ID договора: {agreement_id}"


def _format_agreement_billing_header(agreement_id: object, billing_type: str) -> str:
    return f"ID договора: {agreement_id}, тип биллинга: {billing_type}"


def format_money(kopecks: int, currency: str | None = "rub") -> str:
    if kopecks == 0:
        amount = "0"
    else:
        sign = "-" if kopecks < 0 else ""
        rubles_abs = abs(kopecks) / 100
        integer_part = int(rubles_abs)
        decimal_part = int(round((rubles_abs - integer_part) * 100))

        int_str = f"{integer_part:,}".replace(",", " ")
        amount = f"{sign}{int_str},{decimal_part:02d}"

    symbol = CURRENCY_SYMBOLS.get((currency or "rub").lower())
    if symbol:
        return f"{amount} {symbol}"
    return amount


SERVICE_PREDICTION_LABELS: dict[str, str] = {
    "primary": "Облачные серверы и основные услуги",
    "storage": "Объектное хранилище",
    "vmware": "VMware",
    "vpc": "VPC",
}


def _prediction_label(service_type: str) -> str:
    return SERVICE_PREDICTION_LABELS.get(service_type, service_type)


def format_prediction_hours(hours: int | float | None) -> str:
    if hours is None:
        return "нет активных услуг"
    if hours <= 0:
        return "средств недостаточно"

    total_hours = int(hours)
    days, remaining_hours = divmod(total_hours, 24)

    if days == 0:
        return f"{remaining_hours} ч."

    if remaining_hours == 0:
        return f"{days} дн."

    return f"{days} дн. {remaining_hours} ч."


def format_balance_prediction_response(raw_response: dict) -> str:
    data = raw_response.get("data") or {}

    if not data:
        return "Прогноз расхода баланса недоступен."

    lines = [
        "Прогноз: на сколько хватит текущего баланса при текущем потреблении.",
        "",
    ]

    for service_type, hours in data.items():
        label = _prediction_label(service_type)
        lines.append(f"• {label}: {format_prediction_hours(hours)}")

    return "\n".join(lines).rstrip()


def format_balances_response(raw_response: dict) -> str:
    data = raw_response.get("data") or {}
    agreements = data.get("agreements") or []
    settings_data = data.get("settings") or {}
    currency = settings_data.get("currency", "rub")

    if not agreements:
        return "По аккаунту не найдено договоров (agreement_id) с балансами."

    currency_label = currency.upper() if currency else "RUB"
    lines: list[str] = [f"На аккаунте Selectel найдены балансы в валюте {currency_label}.", ""]

    for agreement in agreements:
        agreement_id = agreement.get("agreement_id", "неизвестен")
        billings = agreement.get("billings") or []

        if not billings:
            lines.append(f"Для {_format_agreement_id(agreement_id)} не найдено доступных балансов.")
            lines.append("")
            continue

        for billing in billings:
            billing_type = billing.get("billing_type", "unknown")
            balances = billing.get("balances") or []

            lines.append(_format_agreement_billing_header(agreement_id, billing_type))
            lines.append("")

            if not balances:
                lines.append(f"Для {_format_agreement_id(agreement_id)} не найдено доступных балансов.")
                lines.append("")
                continue

            for balance in balances:
                balance_type = balance.get("balance_type", "unknown")
                value = balance.get("value", 0)
                label = _balance_label(balance_type)
                lines.append(f"• {label}: {format_money(value, currency)}")

            lines.append("")
            lines.append(f"Сумма балансов: {format_money(billing.get('balances_values_sum', 0), currency)}")
            lines.append(f"Задолженность: {format_money(billing.get('debt_sum', 0), currency)}")
            lines.append(
                f"Итоговый доступный баланс: {format_money(billing.get('final_sum', 0), currency)}"
            )
            lines.append("")

    mode = settings_data.get("mode")
    if mode:
        lines.append(f"Режим оплаты: {mode}")

    return "\n".join(lines).rstrip()
