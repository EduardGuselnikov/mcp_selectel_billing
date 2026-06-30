import logging
from typing import Any

import httpx

from app.config import settings
from app.services.selectel_token_service import (
    TokenPersistence,
    calculate_token_expires_at,
    clear_token,
    get_valid_selectel_token,
    persist_token,
)

logger = logging.getLogger(__name__)

UTM_SOURCE = "mcp_ed"


class SelectelError(Exception):
    """Base Selectel API error."""


class SelectelAuthError(SelectelError):
    """Authentication failed."""


class SelectelAccessError(SelectelError):
    """Service user lacks required permissions."""


class SelectelNetworkError(SelectelError):
    """Network or connectivity error."""


class SelectelAPIError(SelectelError):
    """Unexpected API response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SelectelValidationError(SelectelAPIError):
    """Request validation failed (422)."""


class SelectelClient:
    def __init__(
        self,
        account_id: str,
        service_user_name: str,
        service_user_password: str,
        *,
        identity_url: str | None = None,
        balances_url: str | None = None,
        balance_prediction_url: str | None = None,
        cards_url: str | None = None,
        payments_init_url: str | None = None,
        payment_external_info_url: str | None = None,
        bill_order_url: str | None = None,
        billing_report_by_project_url: str | None = None,
        timeout: float | None = None,
        token_persistence: TokenPersistence | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.account_id = account_id
        self.service_user_name = service_user_name
        self.service_user_password = service_user_password
        self.identity_url = identity_url or settings.selectel_identity_url
        self.balances_url = balances_url or settings.selectel_balances_url
        self.balance_prediction_url = balance_prediction_url or settings.selectel_balance_prediction_url
        self.cards_url = cards_url or settings.selectel_cards_url
        self.payments_init_url = payments_init_url or settings.selectel_payments_init_url
        self.payment_external_info_url = (
            payment_external_info_url or settings.selectel_payment_external_info_url
        )
        self.bill_order_url = bill_order_url or settings.selectel_bill_order_url
        self.billing_report_by_project_url = (
            billing_report_by_project_url or settings.selectel_billing_report_by_project_url
        )
        self.timeout = timeout if timeout is not None else settings.http_timeout_seconds
        self._token_persistence = token_persistence
        self._http_client = http_client

    def _build_auth_payload(self) -> dict:
        return {
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": self.service_user_name,
                            "domain": {"name": self.account_id},
                            "password": self.service_user_password,
                        }
                    },
                },
                "scope": {"domain": {"name": self.account_id}},
            }
        }

    def _get_http_client(self) -> httpx.Client:
        if self._http_client is not None:
            return self._http_client
        return httpx.Client(timeout=self.timeout)

    def _merge_tracking_params(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        params = kwargs.get("params")
        if params is None:
            kwargs["params"] = [("utm_source", UTM_SOURCE)]
            return kwargs

        if isinstance(params, dict):
            if "utm_source" not in params:
                kwargs["params"] = {**params, "utm_source": UTM_SOURCE}
            return kwargs

        param_names = {name for name, _ in params}
        if "utm_source" not in param_names:
            kwargs["params"] = [*params, ("utm_source", UTM_SOURCE)]
        return kwargs

    def _request_identity_api(self) -> str:
        try:
            client = self._get_http_client()
            owns_client = self._http_client is None
            try:
                response = client.post(
                    self.identity_url,
                    json=self._build_auth_payload(),
                    **self._merge_tracking_params({}),
                )
            finally:
                if owns_client:
                    client.close()
        except httpx.TimeoutException as exc:
            raise SelectelNetworkError(
                "Не удалось подключиться к Selectel API: превышено время ожидания."
            ) from exc
        except httpx.RequestError as exc:
            raise SelectelNetworkError("Не удалось подключиться к Selectel API.") from exc

        if response.status_code == 401:
            raise SelectelAuthError("Неверный логин или пароль сервисного пользователя.")
        if response.status_code >= 500:
            raise SelectelAPIError(
                "Selectel API временно недоступен.",
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            raise SelectelAuthError("Неверный логин или пароль сервисного пользователя.")

        token = response.headers.get("X-Subject-Token")
        if not token:
            raise SelectelAPIError("Selectel API не вернул токен авторизации.")

        return token

    def refresh_token(self) -> str:
        token = self._request_identity_api()

        if self._token_persistence is not None:
            expires_at = calculate_token_expires_at()
            persist_token(
                self._token_persistence.credentials,
                self._token_persistence.db,
                token,
                expires_at,
            )
            logger.info("Selectel token refreshed successfully")

        return token

    def invalidate_token(self) -> None:
        if self._token_persistence is None:
            return

        logger.warning(
            "Selectel token expired or invalid for user %s",
            self._token_persistence.user_id,
        )
        clear_token(self._token_persistence.credentials, self._token_persistence.db)

    def get_valid_token(self) -> str:
        if self._token_persistence is None:
            return self.refresh_token()

        persistence = self._token_persistence
        return get_valid_selectel_token(
            credentials=persistence.credentials,
            db=persistence.db,
            user_id=persistence.user_id,
            refresh_callback=self.refresh_token,
        )

    def request_with_auto_refresh(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        token = self.get_valid_token()
        response = self._execute_request(method, url, token, headers=headers, **kwargs)

        if response.status_code == 401 and self._token_persistence is not None:
            self.invalidate_token()
            token = self.refresh_token()
            response = self._execute_request(method, url, token, headers=headers, **kwargs)
            if response.status_code == 401:
                raise SelectelAuthError("Неверный логин или пароль сервисного пользователя.")

        return response

    def _execute_request(
        self,
        method: str,
        url: str,
        token: str,
        *,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        request_headers = {"x-auth-token": token}
        if headers:
            request_headers.update(headers)

        try:
            client = self._get_http_client()
            owns_client = self._http_client is None
            try:
                request_kwargs = self._merge_tracking_params(kwargs)
                return client.request(method, url, headers=request_headers, **request_kwargs)
            finally:
                if owns_client:
                    client.close()
        except httpx.TimeoutException as exc:
            raise SelectelNetworkError(
                "Не удалось подключиться к Selectel API: превышено время ожидания."
            ) from exc
        except httpx.RequestError as exc:
            raise SelectelNetworkError("Не удалось подключиться к Selectel API.") from exc

    def _parse_billing_response(self, response: httpx.Response, *, resource_name: str) -> dict:
        if response.status_code == 401:
            raise SelectelAuthError("Неверный логин или пароль сервисного пользователя.")
        if response.status_code == 403:
            raise SelectelAccessError(f"Сервисный пользователь не имеет доступа к {resource_name}.")
        if response.status_code >= 500:
            raise SelectelAPIError(
                "Selectel API временно недоступен.",
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            raise SelectelAPIError(
                f"Selectel API вернул ошибку: {response.status_code}.",
                status_code=response.status_code,
            )

        try:
            return response.json()
        except ValueError as exc:
            raise SelectelAPIError("Selectel API вернул некорректный ответ.") from exc

    def _parse_billing_report_response(self, response: httpx.Response) -> list[dict]:
        if response.status_code == 401:
            raise SelectelAuthError("Неверный логин или пароль сервисного пользователя.")
        if response.status_code == 403:
            raise SelectelAccessError(
                "Сервисный пользователь не имеет доступа к отчёту по проектам."
            )
        if response.status_code == 422:
            try:
                body = response.json()
            except ValueError as exc:
                raise SelectelAPIError("Selectel API вернул некорректный ответ.") from exc

            lines = ["Не удалось получить отчёт: ошибка в параметрах запроса."]
            error = body.get("error")
            if isinstance(error, dict):
                for field, messages in error.items():
                    if isinstance(messages, list):
                        for message in messages:
                            lines.append(f"Поле {field}: {message}")
                    else:
                        lines.append(f"Поле {field}: {messages}")
            raise SelectelValidationError("\n".join(lines), status_code=422)

        if response.status_code >= 500:
            raise SelectelAPIError(
                "Selectel API временно недоступен.",
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            reason = response.text
            try:
                body = response.json()
                reason = body.get("error") or body.get("message") or reason
            except ValueError:
                pass
            raise SelectelAPIError(
                f"Не удалось получить отчёт по проектам.\nПричина: {reason}",
                status_code=response.status_code,
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise SelectelAPIError("Selectel API вернул некорректный ответ.") from exc

        if isinstance(body, list):
            return body

        if isinstance(body, dict):
            status = body.get("status")
            if status == "success":
                data = body.get("data")
                return data if isinstance(data, list) else []
            if status == "error":
                reason = body.get("error") or body.get("message") or "неизвестная ошибка"
                raise SelectelAPIError(
                    f"Не удалось получить отчёт по проектам.\nПричина: {reason}"
                )

        raise SelectelAPIError("Selectel API вернул некорректный ответ.")

    def get_billing_report_by_project(
        self,
        *,
        start: str,
        end: str,
        locale: str,
        project_ids: list[str] | None = None,
    ) -> list[dict]:
        params: list[tuple[str, str]] = [
            ("start", start),
            ("end", end),
            ("locale", locale),
        ]
        if project_ids:
            for project_id in project_ids:
                params.append(("project_ids", project_id))

        response = self.request_with_auto_refresh(
            "GET",
            self.billing_report_by_project_url,
            params=params,
        )
        return self._parse_billing_report_response(response)

    def get_balances(self) -> dict:
        response = self.request_with_auto_refresh("GET", self.balances_url)
        return self._parse_billing_response(response, resource_name="балансу")

    def get_balance_prediction(self) -> dict:
        response = self.request_with_auto_refresh("GET", self.balance_prediction_url)
        return self._parse_billing_response(response, resource_name="прогнозу баланса")

    def get_cards(self) -> dict:
        response = self.request_with_auto_refresh("GET", self.cards_url)
        return self._parse_billing_response(response, resource_name="сохранённым картам")

    def pay_with_saved_card(self, card_id: int, amount_kopecks: int) -> dict:
        response = self.request_with_auto_refresh(
            "POST",
            f"{self.cards_url}/{card_id}/pay",
            headers={"Content-Type": "application/json"},
            json={"amount": amount_kopecks},
        )
        return self._parse_billing_response(response, resource_name="оплате сохранённой картой")

    def init_payment(
        self,
        *,
        payment_id: int,
        payment_type: int,
        amount_kopecks: int,
        bind: int,
        pay: str,
    ) -> dict:
        response = self.request_with_auto_refresh(
            "POST",
            self.payments_init_url,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "id": str(payment_id),
                "type": str(payment_type),
                "amount": str(amount_kopecks),
                "bind": str(bind),
                "pay": pay,
            },
        )
        return self._parse_billing_response(response, resource_name="инициализации платежа")

    def check_payment_external_status(self, transaction_id: str) -> dict:
        response = self.request_with_auto_refresh(
            "PUT",
            self.payment_external_info_url,
            headers={"Content-Type": "application/json"},
            json={"transaction_id": transaction_id},
        )
        return self._parse_billing_response(response, resource_name="статусу платежа")

    def save_bill_email(self, order_id: str, email: str) -> dict:
        response = self.request_with_auto_refresh(
            "PUT",
            f"{self.bill_order_url}/{order_id}",
            headers={"Content-Type": "application/json"},
            json={"email": email},
        )
        return self._parse_billing_response(response, resource_name="сохранению email для счёта")

    def get_token(self) -> str:
        """Backward-compatible alias for refresh_token()."""
        return self.refresh_token()
