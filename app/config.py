from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/selectel_mcp"
    default_user_id: str | None = None
    selectel_account_id: str | None = None
    selectel_service_user_name: str | None = None
    selectel_service_user_password: str | None = None
    selectel_identity_url: str = "https://cloud.api.selcloud.ru/identity/v3/auth/tokens"
    selectel_balances_url: str = "https://api.selectel.ru/v4/balances"
    selectel_balance_prediction_url: str = "https://api.selectel.ru/v2/billing/prediction"
    selectel_cards_url: str = "https://api.selectel.ru/v2/billing/cards"
    selectel_payments_init_url: str = "https://api.selectel.ru/v3/payments/init"
    selectel_payment_external_info_url: str = "https://api.selectel.ru/v1/billing/payment/external_info"
    selectel_bill_order_url: str = "https://api.selectel.ru/v1/billing/bill"
    selectel_billing_report_by_project_url: str = (
        "https://api.selectel.ru/v1/billing/report/by_project/flat"
    )
    http_timeout_seconds: float = 30.0


settings = Settings()
