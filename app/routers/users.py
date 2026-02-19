from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_db
from app.core.security import require_admin
from app.models.schemas import UserOut
from app.repositories.user_repository import UserRepository

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/", response_model=list[UserOut], dependencies=[Depends(require_admin)])
async def list_users(db: AsyncIOMotorDatabase = Depends(get_db)):
    repo = UserRepository(db)
    return await repo.list(limit=200)


@router.delete("/{user_id}", dependencies=[Depends(require_admin)])
async def delete_user(user_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    repo = UserRepository(db)
    ok = await repo.delete(user_id)
    if not ok:
        raise HTTPException(404, "Usuario no encontrado")
    return {"deleted": True, "user_id": user_id}
