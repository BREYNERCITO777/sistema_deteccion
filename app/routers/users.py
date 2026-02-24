from __future__ import annotations

from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field

from app.core.config import settings
from app.core.database import get_db
from app.core.security import require_roles

router = APIRouter(prefix="/users", tags=["Users"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserCreate(BaseModel):
    name: str = Field(..., min_length=2)
    email: EmailStr
    password: str = Field(..., min_length=6)
    role: Literal["admin", "operator"] = "operator"


class UserOut(BaseModel):
    _id: str
    name: str
    email: EmailStr
    role: str


def _to_user_out(u: dict) -> dict:
    return {
        "_id": str(u["_id"]),
        "name": u.get("name", ""),
        "email": u.get("email"),
        "role": u.get("role", "operator"),
    }


@router.get("", response_model=list[UserOut])
async def list_users(
    db: AsyncIOMotorDatabase = Depends(get_db),
    _user=Depends(require_roles("admin")),
):
    docs = await db[settings.USERS_COL].find({}).sort("email", 1).to_list(length=500)
    return [_to_user_out(u) for u in docs]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _user=Depends(require_roles("admin")),
):
    exists = await db[settings.USERS_COL].find_one({"email": payload.email})
    if exists:
        raise HTTPException(status_code=409, detail="Ese email ya existe")

    password_hash = pwd_context.hash(payload.password)
    doc = {
        "name": payload.name,
        "email": payload.email,
        "password_hash": password_hash,
        "role": payload.role,
        "created_at": __import__("datetime").datetime.utcnow().isoformat(),
    }
    res = await db[settings.USERS_COL].insert_one(doc)
    doc["_id"] = res.inserted_id
    return _to_user_out(doc)


@router.patch("/{user_id}/role", response_model=UserOut)
async def set_role(
    user_id: str,
    role: Literal["admin", "operator"],
    db: AsyncIOMotorDatabase = Depends(get_db),
    _user=Depends(require_roles("admin")),
):
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="user_id inválido")

    res = await db[settings.USERS_COL].update_one({"_id": oid}, {"$set": {"role": role}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    u = await db[settings.USERS_COL].find_one({"_id": oid})
    return _to_user_out(u)


@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def delete_user(
    user_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user=Depends(require_roles("admin")),
):
    """
    ✅ Solo ADMIN puede borrar usuarios por ID.
    Protección extra: no permitir que un admin se borre a sí mismo.
    """
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="user_id inválido")

    # current_user normalmente trae _id como string u ObjectId dependiendo tu implementación.
    # Ajuste defensivo:
    me_id = str(current_user.get("_id", ""))

    if me_id and me_id == user_id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario")

    res = await db[settings.USERS_COL].delete_one({"_id": oid})
    if res.deleted_count != 1:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    return {"deleted": True, "user_id": user_id}