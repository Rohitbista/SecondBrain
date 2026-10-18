from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from secondbrain.app.routes.auth import DB, CurrentUser, MessageResponse, UserOut
from secondbrain.service import user_service

router = APIRouter(prefix="/users", tags=["users"])


# ---------- schemas ----------
class UpdateProfileRequest(BaseModel):
    """All fields optional. Email is intentionally not editable here."""

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    username: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_]{3,30}$")


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


# ---------- routes ----------
@router.patch("/me", response_model=UserOut)
async def update_profile(body: UpdateProfileRequest, db: DB, user: CurrentUser):
    return await user_service.update_profile(
        db, user, **body.model_dump(exclude_none=True)
    )


@router.post("/me/change-password", response_model=MessageResponse)
async def change_password(body: ChangePasswordRequest, db: DB, user: CurrentUser):
    await user_service.change_password(
        db, user, body.current_password, body.new_password
    )
    return MessageResponse(message="Password updated.")


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(body: DeleteAccountRequest, db: DB, user: CurrentUser):
    await user_service.delete_account(db, user, body.password)