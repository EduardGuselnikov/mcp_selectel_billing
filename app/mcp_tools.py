from collections.abc import Callable

from mcp.server.fastmcp import FastMCP
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import AuditLog
from app.selectel_client import SelectelClient, SelectelError
from app.services.balance_formatter import (
    format_balance_prediction_response,
    format_balances_response,
)
from app.services.billing_report_formatter import (
    BillingReportParamsError,
    format_billing_report_by_project_response,
    validate_balance_filter,
    validate_report_params,
)
from app.services.credentials_service import (
    CredentialsNotConfiguredError,
    build_selectel_client,
    get_credentials,
    resolve_user_id,
    validate_and_save_credentials,
)
from app.services.top_up_formatter import (
    MIN_PAYMENT_RUB,
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

mcp = FastMCP(
    "Selectel MCP Server",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


def _log_audit(db: Session, user_id: str, tool_name: str, success: bool, error_message: str | None) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            tool_name=tool_name,
            success=success,
            error_message=error_message,
        )
    )
    db.commit()


def _run_billing_tool(
    *,
    tool_name: str,
    user_id: str | None,
    fetch: Callable,
    format_response: Callable[[dict], str],
) -> str:
    db = SessionLocal()

    try:
        try:
            resolved_user_id = resolve_user_id(user_id)
        except CredentialsNotConfiguredError as exc:
            message = str(exc)
            _log_audit(db, user_id or "unknown", tool_name, success=False, error_message=message)
            return message

        credentials = get_credentials(db, resolved_user_id)
        if credentials is None:
            message = (
                f"Для пользователя {resolved_user_id} не найдены учётные данные Selectel. "
                "Сначала вызовите connect_selectel_account или настройте .env."
            )
            _log_audit(db, resolved_user_id, tool_name, success=False, error_message=message)
            return message

        client = build_selectel_client(
            credentials=credentials,
            user_id=resolved_user_id,
            db=db,
        )

        try:
            raw_response = fetch(client)
            formatted = format_response(raw_response)
            _log_audit(db, resolved_user_id, tool_name, success=True, error_message=None)
            return formatted
        except SelectelError as exc:
            message = str(exc)
            _log_audit(db, resolved_user_id, tool_name, success=False, error_message=message)
            return message
    finally:
        db.close()


def _with_selectel_client(
    *,
    tool_name: str,
    user_id: str | None,
    action: Callable[[SelectelClient, str], str],
) -> str:
    db = SessionLocal()

    try:
        try:
            resolved_user_id = resolve_user_id(user_id)
        except CredentialsNotConfiguredError as exc:
            message = str(exc)
            _log_audit(db, user_id or "unknown", tool_name, success=False, error_message=message)
            return message

        credentials = get_credentials(db, resolved_user_id)
        if credentials is None:
            message = (
                f"Для пользователя {resolved_user_id} не найдены учётные данные Selectel. "
                "Сначала вызовите connect_selectel_account или настройте .env."
            )
            _log_audit(db, resolved_user_id, tool_name, success=False, error_message=message)
            return message

        client = build_selectel_client(
            credentials=credentials,
            user_id=resolved_user_id,
            db=db,
        )

        try:
            result = action(client, resolved_user_id)
            _log_audit(db, resolved_user_id, tool_name, success=True, error_message=None)
            return result
        except SelectelError as exc:
            message = str(exc)
            _log_audit(db, resolved_user_id, tool_name, success=False, error_message=message)
            return message
    finally:
        db.close()


@mcp.tool()
def connect_selectel_account(
    account_id: str,
    service_user_name: str,
    service_user_password: str,
    user_id: str | None = None,
) -> str:
    """Один раз сохранить учётные данные Selectel. Дальше авторизация выполняется автоматически."""
    db = SessionLocal()
    tool_name = "connect_selectel_account"

    try:
        resolved_user_id = resolve_user_id(user_id)
        validate_and_save_credentials(
            db,
            user_id=resolved_user_id,
            account_id=account_id,
            service_user_name=service_user_name,
            service_user_password=service_user_password,
        )
        message = (
            f"Аккаунт Selectel подключён для пользователя {resolved_user_id}. "
            "Теперь можно вызывать get_balance без повторной авторизации."
        )
        _log_audit(db, resolved_user_id, tool_name, success=True, error_message=None)
        return message
    except CredentialsNotConfiguredError as exc:
        message = str(exc)
        _log_audit(db, user_id or "unknown", tool_name, success=False, error_message=message)
        return message
    except SelectelError as exc:
        message = str(exc)
        _log_audit(db, user_id or "unknown", tool_name, success=False, error_message=message)
        return message
    finally:
        db.close()


@mcp.tool()
def get_balance(user_id: str | None = None) -> str:
    """Получить балансы Selectel. Учётные данные берутся из БД, токен обновляется автоматически."""
    return _run_billing_tool(
        tool_name="get_balance",
        user_id=user_id,
        fetch=lambda client: client.get_balances(),
        format_response=format_balances_response,
    )


@mcp.tool()
def get_balance_prediction(user_id: str | None = None) -> str:
    """Оценить, на сколько хватит текущего баланса при текущем потреблении."""
    return _run_billing_tool(
        tool_name="get_balance_prediction",
        user_id=user_id,
        fetch=lambda client: client.get_balance_prediction(),
        format_response=format_balance_prediction_response,
    )


@mcp.tool()
def top_up_balance_saved_card(
    amount_rub: float | None = None,
    card_id: int | None = None,
    confirm: bool = False,
    user_id: str | None = None,
) -> str:
    f"""Пополнить баланс с сохранённой банковской карты.

    Сначала укажите amount_rub (сумма в рублях, минимум {MIN_PAYMENT_RUB} ₽).
    При нескольких картах выберите card_id. Оплата выполняется только после confirm=true.
    """

    def action(client: SelectelClient, _resolved_user_id: str) -> str:
        amount_error = validate_amount_rub(amount_rub)
        if amount_error:
            return amount_error

        assert amount_rub is not None
        amount_kopecks = rubles_to_kopecks(amount_rub)

        cards_response = client.get_cards()
        active_cards = get_active_cards(cards_response)

        if not active_cards:
            return "Сохранённых активных карт не найдено. Используйте top_up_balance_new_card."

        if card_id is None:
            if len(active_cards) == 1:
                card = active_cards[0]
                return format_saved_card_confirmation(card, amount_kopecks)
            return format_saved_card_list(active_cards)

        selected_card = next((card for card in active_cards if card.get("id") == card_id), None)
        if selected_card is None:
            return (
                f"Карта с ID {card_id} не найдена среди активных сохранённых карт.\n\n"
                + format_saved_card_list(active_cards)
            )

        if not confirm:
            return format_saved_card_confirmation(selected_card, amount_kopecks)

        payment_response = client.pay_with_saved_card(card_id, amount_kopecks)
        return format_saved_card_payment_success(payment_response, amount_kopecks)

    return _with_selectel_client(
        tool_name="top_up_balance_saved_card",
        user_id=user_id,
        action=action,
    )


@mcp.tool()
def top_up_balance_new_card(
    amount_rub: float | None = None,
    user_id: str | None = None,
) -> str:
    f"""Пополнить баланс новой банковской картой через платёжный шлюз.

    Укажите amount_rub (сумма в рублях, минимум {MIN_PAYMENT_RUB} ₽).
    Вернёт ссылку для ввода данных карты на стороне шлюза. MCP не принимает реквизиты карты.
    """

    def action(client: SelectelClient, _resolved_user_id: str) -> str:
        amount_error = validate_amount_rub(amount_rub)
        if amount_error:
            return amount_error

        assert amount_rub is not None
        amount_kopecks = rubles_to_kopecks(amount_rub)

        payment_response = client.init_payment(
            payment_id=38,
            payment_type=38,
            amount_kopecks=amount_kopecks,
            bind=1,
            pay="by_blank",
        )
        return format_new_card_payment(payment_response, amount_kopecks)

    return _with_selectel_client(
        tool_name="top_up_balance_new_card",
        user_id=user_id,
        action=action,
    )


@mcp.tool()
def top_up_balance_sbp(
    amount_rub: float | None = None,
    user_id: str | None = None,
) -> str:
    f"""Пополнить баланс через СБП (Систему быстрых платежей).

    Укажите amount_rub (сумма в рублях, минимум {MIN_PAYMENT_RUB} ₽).
    Вернёт QR-код и ссылку для приложения банка.
    """

    def action(client: SelectelClient, _resolved_user_id: str) -> str:
        amount_error = validate_amount_rub(amount_rub)
        if amount_error:
            return amount_error

        assert amount_rub is not None
        amount_kopecks = rubles_to_kopecks(amount_rub)

        payment_response = client.init_payment(
            payment_id=6,
            payment_type=6,
            amount_kopecks=amount_kopecks,
            bind=0,
            pay="by_modal",
        )
        return format_sbp_payment(payment_response, amount_kopecks)

    return _with_selectel_client(
        tool_name="top_up_balance_sbp",
        user_id=user_id,
        action=action,
    )


@mcp.tool()
def top_up_balance_bank_transfer(
    amount_rub: float | None = None,
    user_id: str | None = None,
) -> str:
    f"""Пополнить баланс банковским переводом.

    Укажите amount_rub (сумма в рублях, минимум {MIN_PAYMENT_RUB} ₽).
    Вернёт ссылку на PDF платёжного поручения.
    """

    def action(client: SelectelClient, _resolved_user_id: str) -> str:
        amount_error = validate_amount_rub(amount_rub)
        if amount_error:
            return amount_error

        assert amount_rub is not None
        amount_kopecks = rubles_to_kopecks(amount_rub)

        payment_response = client.init_payment(
            payment_id=1,
            payment_type=1,
            amount_kopecks=amount_kopecks,
            bind=0,
            pay="by_modal",
        )

        return format_bank_transfer_payment(payment_response, amount_kopecks)

    return _with_selectel_client(
        tool_name="top_up_balance_bank_transfer",
        user_id=user_id,
        action=action,
    )


@mcp.tool()
def check_payment_status(
    transaction_id: str,
    user_id: str | None = None,
) -> str:
    """Проверить статус асинхронного платежа (СБП).

    Передайте transaction_id из ответа top_up_balance_sbp.
    """

    def action(client: SelectelClient, _resolved_user_id: str) -> str:
        if not transaction_id.strip():
            return "Укажите transaction_id из ответа top_up_balance_sbp."

        status_response = client.check_payment_external_status(transaction_id.strip())
        return format_payment_status(status_response, transaction_id.strip())

    return _with_selectel_client(
        tool_name="check_payment_status",
        user_id=user_id,
        action=action,
    )


@mcp.tool()
def get_billing_report_by_project(
    start: str,
    end: str,
    locale: str,
    project_ids: list[str] | None = None,
    project_name: str | None = None,
    product_name: str | None = None,
    resource_name: str | None = None,
    resource_type: str | None = None,
    metric_id: str | None = None,
    metric_name: str | None = None,
    balance: str | None = None,
    location_region: str | None = None,
    group: bool = True,
    user_id: str | None = None,
) -> str:
    """Получить отчёт по оказанным и оплаченным услугам Selectel за период.

    Обязательные параметры: start (YYYY-MM-DD, включительно), end (YYYY-MM-DD, исключительно),
    locale (ru или en). Опционально можно ограничить проекты через project_ids и отфильтровать
    результат по project_name, product_name, resource_name, resource_type, metric_id,
    metric_name, balance (main/bonus) и location_region. При group=true вернёт иерархию
    Проект → Продукт → Объект → Метрики с итогами.
    """

    def action(client: SelectelClient, _resolved_user_id: str) -> str:
        try:
            validate_report_params(start=start, end=end, locale=locale)
            validate_balance_filter(balance)
        except BillingReportParamsError as exc:
            return str(exc)

        raw_rows = client.get_billing_report_by_project(
            start=start,
            end=end,
            locale=locale,
            project_ids=project_ids or None,
        )
        return format_billing_report_by_project_response(
            raw_rows,
            start=start,
            end=end,
            group=group,
            project_name=project_name,
            product_name=product_name,
            resource_name=resource_name,
            resource_type=resource_type,
            metric_id=metric_id,
            metric_name=metric_name,
            balance=balance,
            location_region=location_region,
        )

    return _with_selectel_client(
        tool_name="get_billing_report_by_project",
        user_id=user_id,
        action=action,
    )
