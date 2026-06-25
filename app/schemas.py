from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SelectelCredentialsCreate(BaseModel):
    account_id: str = Field(..., min_length=1)
    service_user_name: str = Field(..., min_length=1)
    service_user_password: str = Field(..., min_length=1)


class SelectelCredentialsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    selectel_account_id: str
    service_user_name: str
    created_at: datetime
    updated_at: datetime


class ErrorResponse(BaseModel):
    detail: str
