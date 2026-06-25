from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import UserSelectelCredentials
from app.schemas import ErrorResponse, SelectelCredentialsCreate, SelectelCredentialsResponse
from app.selectel_client import (
    SelectelAccessError,
    SelectelAuthError,
    SelectelError,
    SelectelNetworkError,
)
from app.services.credentials_service import validate_and_save_credentials

router = APIRouter(prefix="/users", tags=["users"])


def _map_selectel_error(exc: SelectelError) -> HTTPException:
    if isinstance(exc, SelectelAuthError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный логин или пароль сервисного пользователя.",
        )
    if isinstance(exc, SelectelAccessError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Сервисный пользователь не имеет доступа к балансу.",
        )
    if isinstance(exc, SelectelNetworkError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось подключиться к Selectel API.",
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=str(exc),
    )


@router.post(
    "/{user_id}/selectel-credentials",
    response_model=SelectelCredentialsResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
def save_selectel_credentials(
    user_id: str,
    payload: SelectelCredentialsCreate,
    db: Session = Depends(get_db),
) -> UserSelectelCredentials:
    try:
        return validate_and_save_credentials(
            db,
            user_id=user_id,
            account_id=payload.account_id,
            service_user_name=payload.service_user_name,
            service_user_password=payload.service_user_password,
        )
    except SelectelError as exc:
        raise _map_selectel_error(exc) from exc
