import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import UserSelectelCredentials

logger = logging.getLogger(__name__)

TOKEN_TTL_HOURS = 23
TOKEN_REFRESH_BUFFER_HOURS = 1


@dataclass
class TokenPersistence:
    user_id: str
    credentials: UserSelectelCredentials
    db: Session


def calculate_token_expires_at(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current + timedelta(hours=TOKEN_TTL_HOURS)


def is_token_valid(expires_at: datetime | None, now: datetime | None = None) -> bool:
    if expires_at is None:
        return False

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)

    token_expires_at = expires_at
    if token_expires_at.tzinfo is None:
        token_expires_at = token_expires_at.replace(tzinfo=timezone.utc)

    return token_expires_at > current + timedelta(hours=TOKEN_REFRESH_BUFFER_HOURS)


def persist_token(
    credentials: UserSelectelCredentials,
    db: Session,
    token: str,
    expires_at: datetime,
) -> None:
    credentials.selectel_token = token
    credentials.selectel_token_expires_at = expires_at
    db.commit()


def clear_token(credentials: UserSelectelCredentials, db: Session) -> None:
    credentials.selectel_token = None
    credentials.selectel_token_expires_at = None
    db.commit()


def get_valid_selectel_token(
    *,
    credentials: UserSelectelCredentials,
    db: Session,
    user_id: str,
    refresh_callback,
) -> str:
    if credentials.selectel_token and is_token_valid(credentials.selectel_token_expires_at):
        logger.info("Using cached Selectel token for user %s", user_id)
        return credentials.selectel_token

    logger.info("Refreshing Selectel token for user %s", user_id)
    return refresh_callback()
