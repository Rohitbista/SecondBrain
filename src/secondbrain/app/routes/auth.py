from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from secondbrain.database.models import User
from secondbrain.database.session import get_db
from secondbrain.service import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

DB = Annotated[AsyncSession, Depends(get_db)]


# ---------- schemas ----------
class RegisterRequest(BaseModel):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    username: str = Field(pattern=r"^[A-Za-z0-9_]{3,30}$")
    password: str = Field(min_length=8, max_length=128)


class EmailRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10)
    new_password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    first_name: str
    last_name: str
    username: str
    is_admin: bool
    is_verified: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    message: str


# ---------- dependency used by every protected route ----------
async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], db: DB
) -> User:
    return await auth_service.get_user_from_token(db, token)


CurrentUser = Annotated[User, Depends(get_current_user)]


# ---------- routes ----------
@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, background_tasks: BackgroundTasks, db: DB):
    return await auth_service.register(db, background_tasks, **body.model_dump())


@router.post("/login", response_model=TokenResponse)
async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DB):
    # OAuth2 form field is called "username" but accepts username OR email
    token = await auth_service.login(db, form.username, form.password)
    return TokenResponse(access_token=token)


@router.get("/verify-email", response_model=MessageResponse)
async def verify_email(db: DB, token: Annotated[str, Query(min_length=10)]):
    await auth_service.verify_email(db, token)
    return MessageResponse(message="Email verified. You can now log in.")


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    body: EmailRequest, background_tasks: BackgroundTasks, db: DB
):
    await auth_service.resend_verification(db, background_tasks, body.email)
    return MessageResponse(
        message="If that account exists and is unverified, a new email has been sent."
    )


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(body: EmailRequest, background_tasks: BackgroundTasks, db: DB):
    await auth_service.forgot_password(db, background_tasks, body.email)
    return MessageResponse(
        message="If that email is registered, a password reset message has been sent."
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(body: ResetPasswordRequest, db: DB):
    await auth_service.reset_password(db, body.token, body.new_password)
    return MessageResponse(message="Password updated. You can now log in.")


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user