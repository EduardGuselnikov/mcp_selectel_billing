from sqlalchemy.orm import Session

from app.config import settings
from app.models import UserSelectelCredentials
from app.selectel_client import SelectelClient, SelectelError
from app.services.selectel_token_service import TokenPersistence


class CredentialsNotConfiguredError(ValueError):
    """Учётные данные Selectel не настроены."""


def env_credentials_configured() -> bool:
    return all(
        [
            settings.default_user_id,
            settings.selectel_account_id,
            settings.selectel_service_user_name,
            settings.selectel_service_user_password,
        ]
    )


def resolve_user_id(user_id: str | None) -> str:
    resolved = user_id or settings.default_user_id
    if not resolved:
        raise CredentialsNotConfiguredError(
            "Не указан user_id. Передайте user_id или задайте DEFAULT_USER_ID в .env."
        )
    return resolved


def upsert_credentials(
    db: Session,
    *,
    user_id: str,
    account_id: str,
    service_user_name: str,
    service_user_password: str,
) -> UserSelectelCredentials:
    existing = db.query(UserSelectelCredentials).filter_by(user_id=user_id).one_or_none()

    if existing:
        existing.selectel_account_id = account_id
        existing.service_user_name = service_user_name
        existing.service_user_password = service_user_password
        existing.selectel_token = None
        existing.selectel_token_expires_at = None
        return existing

    credentials = UserSelectelCredentials(
        user_id=user_id,
        selectel_account_id=account_id,
        service_user_name=service_user_name,
        service_user_password=service_user_password,
    )
    db.add(credentials)
    return credentials


def validate_and_save_credentials(
    db: Session,
    *,
    user_id: str,
    account_id: str,
    service_user_name: str,
    service_user_password: str,
) -> UserSelectelCredentials:
    credentials = upsert_credentials(
        db,
        user_id=user_id,
        account_id=account_id,
        service_user_name=service_user_name,
        service_user_password=service_user_password,
    )
    db.flush()

    client = build_selectel_client(
        credentials=credentials,
        user_id=user_id,
        db=db,
    )

    try:
        client.get_balances()
    except SelectelError:
        db.rollback()
        raise

    db.commit()
    db.refresh(credentials)
    return credentials


def bootstrap_credentials_from_env(db: Session) -> bool:
    if not env_credentials_configured():
        return False

    user_id = settings.default_user_id
    assert user_id is not None

    account_id = settings.selectel_account_id
    service_user_name = settings.selectel_service_user_name
    service_user_password = settings.selectel_service_user_password
    assert account_id is not None
    assert service_user_name is not None
    assert service_user_password is not None

    existing = db.query(UserSelectelCredentials).filter_by(user_id=user_id).one_or_none()
    if existing is not None:
        credentials_changed = (
            existing.selectel_account_id != account_id
            or existing.service_user_name != service_user_name
            or existing.service_user_password != service_user_password
        )
        if not credentials_changed:
            return False

    upsert_credentials(
        db,
        user_id=user_id,
        account_id=account_id,
        service_user_name=service_user_name,
        service_user_password=service_user_password,
    )
    db.commit()
    return True


def get_credentials(db: Session, user_id: str) -> UserSelectelCredentials | None:
    return db.query(UserSelectelCredentials).filter_by(user_id=user_id).one_or_none()


def build_selectel_client(
    *,
    credentials: UserSelectelCredentials,
    user_id: str,
    db: Session,
) -> SelectelClient:
    return SelectelClient(
        account_id=credentials.selectel_account_id,
        service_user_name=credentials.service_user_name,
        service_user_password=credentials.service_user_password,
        token_persistence=TokenPersistence(
            user_id=user_id,
            credentials=credentials,
            db=db,
        ),
    )
