from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from secondbrain.app.routes.auth import DB, CurrentUser, UserOut
from secondbrain.database.models import User
from secondbrain.service import admin_service


async def require_admin(user: CurrentUser) -> User:
    """Dependency: 403 unless the caller is an admin, else returns the user."""
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


Admin = Annotated[User, Depends(require_admin)]

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------- schemas ----------
class UserListResponse(BaseModel):
    items: list[UserOut]
    total: int
    limit: int
    offset: int


class AdminUserDetail(UserOut):
    notes_count: int


class AdminUpdateUserRequest(BaseModel):
    is_admin: bool | None = None
    is_verified: bool | None = None


class StatsResponse(BaseModel):
    total_users: int
    verified_users: int
    total_notes: int
    avg_notes_per_user: float


# ---------- routes ----------
@router.get("/users", response_model=UserListResponse)
async def list_users(
    db: DB,
    admin: Admin,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    is_verified: bool | None = None,
    is_admin: bool | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
):
    return await admin_service.list_users(
        db,
        limit=limit,
        offset=offset,
        is_verified=is_verified,
        is_admin=is_admin,
        search=search,
    )


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def get_user(user_id: int, db: DB, admin: Admin):
    user, notes_count = await admin_service.get_user(db, user_id)
    return AdminUserDetail(
        **UserOut.model_validate(user).model_dump(), notes_count=notes_count
    )


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int, body: AdminUpdateUserRequest, db: DB, admin: Admin
):
    return await admin_service.update_user(
        db, admin, user_id, **body.model_dump(exclude_none=True)
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: DB, admin: Admin):
    await admin_service.delete_user(db, admin, user_id)


@router.get("/stats", response_model=StatsResponse)
async def stats(db: DB, admin: Admin):
    return await admin_service.get_stats(db)