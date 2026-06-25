from app.config import settings
from app.services.balance_formatter import format_money

AMOUNT_PROMPT = "На какую сумму пополнить баланс?"
MIN_PAYMENT_RUB = 200


def rubles_to_kopecks(amount_rub: float) -> int:
    return int(round(amount_rub * 100))


def validate_amount_rub(amount_rub: float | None) -> str | None:
    if amount_rub is None:
        return AMOUNT_PROMPT
    if amount_rub <= 0:
        return "Сумма пополнения должна быть больше нуля. Укажите сумму в рублях."
    if amount_rub < MIN_PAYMENT_RUB:
        return f"Минимальная сумма пополнения — {MIN_PAYMENT_RUB} ₽. Укажите сумму не меньше {MIN_PAYMENT_RUB} руб."
    return None


def get_active_cards(raw_response: dict) -> list[dict]:
    cards = raw_response.get("data") or raw_response.get("cards") or []
    return [card for card in cards if card.get("state") == 1]


def _card_mask(card: dict) -> str:
    return card.get("mask") or card.get("masked_pan") or "****"


def format_card_line(card: dict) -> str:
    card_id = card.get("id")
    mask = _card_mask(card)
    card_type = card.get("card_type", "")
    bank = card.get("bank", "")
    details = ", ".join(part for part in (card_type, bank) if part)
    suffix = f" ({details})" if details else ""
    return f"• ID {card_id}: {mask}{suffix}"


def format_saved_card_list(cards: list[dict]) -> str:
    lines = ["Доступные сохранённые карты:", ""]
    lines.extend(format_card_line(card) for card in cards)
    lines.append("")
    lines.append("Укажите card_id выбранной карты для продолжения.")
    return "\n".join(lines)


def format_saved_card_confirmation(card: dict, amount_kopecks: int) -> str:
    return (
        f"Подтвердите пополнение баланса на {format_money(amount_kopecks)} "
        f"с карты {_card_mask(card)} "
        f"(ID {card.get('id')}).\n\n"
        "Для выполнения оплаты вызовите инструмент повторно с confirm=true."
    )


def format_saved_card_payment_success(raw_response: dict, amount_kopecks: int) -> str:
    payment_id = raw_response.get("payment_id")
    lines = [
        f"Баланс успешно пополнен на {format_money(amount_kopecks)}.",
    ]
    if payment_id:
        lines.append(f"ID платежа: {payment_id}")
    return "\n".join(lines)


def format_new_card_payment(raw_response: dict, amount_kopecks: int) -> str:
    redirect = raw_response.get("redirect") or {}
    url = redirect.get("url")
    payment_id = raw_response.get("payment_id")

    if not url:
        return "Не удалось получить ссылку для оплаты новой картой."

    lines = [
        f"Платёж на {format_money(amount_kopecks)} создан.",
        "",
        "Перейдите по ссылке и введите данные карты на стороне платёжного шлюза:",
        url,
    ]
    if payment_id:
        lines.append(f"\nID платежа: {payment_id}")
    return "\n".join(lines)


def format_sbp_payment(raw_response: dict, amount_kopecks: int) -> str:
    modal = raw_response.get("modal_window") or {}
    qr_url = modal.get("qrUrl")
    mobile_url = modal.get("url_for_mobile_app")
    transaction_id = modal.get("transaction_id")

    if not qr_url and not mobile_url:
        return "Не удалось получить данные для оплаты через СБП."

    lines = [
        f"Платёж через СБП на {format_money(amount_kopecks)} создан.",
        "",
    ]
    if qr_url:
        lines.append(f"QR-код для оплаты: {qr_url}")
    if mobile_url:
        lines.append(f"Открыть в приложении банка: {mobile_url}")
    if transaction_id:
        lines.append("")
        lines.append(
            f"Для проверки статуса используйте check_payment_status "
            f"с transaction_id={transaction_id!r}."
        )
    return "\n".join(lines)


def format_bank_transfer_payment(raw_response: dict, amount_kopecks: int) -> str:
    order = raw_response.get("order") or {}
    transaction_id = order.get("transaction_id") or order.get("order_id")

    if not transaction_id:
        return "Не удалось получить реквизиты для банковского перевода."

    pdf_url = f"{settings.selectel_bill_order_url}/{transaction_id}"

    lines = [
        f"Счёт на банковский перевод на {format_money(amount_kopecks)} создан.",
        "",
        f"Скачать PDF платёжного поручения: {pdf_url}",
        f"ID заказа: {transaction_id}",
        "",
        "Письмо со счётом отправлено на email, указанный в панели управления Selectel.",
    ]
    return "\n".join(lines)


PAYMENT_STATUS_LABELS = {
    "NEW": "ожидает оплаты",
    "SUCCESS": "успешно оплачен",
    "FAILED": "не удался",
}


def format_payment_status(raw_response: dict, transaction_id: str) -> str:
    external_info = raw_response.get("external_info") or {}
    status = external_info.get("status", "UNKNOWN")
    label = PAYMENT_STATUS_LABELS.get(status, status.lower())

    lines = [
        f"Статус платежа (transaction_id={transaction_id}): {label}.",
    ]
    if status == "NEW":
        lines.append("Платёж ещё не завершён. Повторите проверку позже.")
    elif status == "SUCCESS":
        lines.append("Средства зачислены на баланс.")
    elif status == "FAILED":
        lines.append("Платёж не прошёл. Создайте новый платёж.")
    return "\n".join(lines)
