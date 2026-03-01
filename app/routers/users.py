from __future__ import annotations

from typing import Literal, Optional

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


# =========================
# Schemas
# =========================
class UserCreate(BaseModel):
    name: str = Field(..., min_length=2)
    email: EmailStr
    password: str = Field(..., min_length=6)
    role: Literal["admin", "operator"] = "operator"
    estado: Literal[0, 1] = 1


class UserOut(BaseModel):
    _id: str
    id: str  # ✅ compat
    name: str
    email: EmailStr
    role: Literal["admin", "operator"]
    estado: Literal[0, 1] = 1
    created_at: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2)
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(default=None, min_length=6)
    role: Optional[Literal["admin", "operator"]] = None
    estado: Optional[Literal[0, 1]] = None


class UserEstadoUpdate(BaseModel):
    estado: Literal[0, 1]


def _to_user_out(u: dict) -> dict:
    sid = str(u["_id"])
    return {
        "_id": sid,       # ✅ frontend espera esto
        "id": sid,        # ✅ tu swagger ahora también coincide con tu JSON actual
        "name": u.get("name", ""),
        "email": u.get("email"),
        "role": u.get("role", "operator"),
        "estado": int(u.get("estado", 1)),
        "created_at": u.get("created_at"),
    }


def _str_id(x) -> str:
    try:
        return str(x)
    except Exception:
        return ""


@router.get("", response_model=list[UserOut])
async def list_users(
    limit: int = 500,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _user=Depends(require_roles("admin")),
):
    limit = max(1, min(int(limit), 2000))
    docs = await db[settings.USERS_COL].find({}).sort("email", 1).to_list(length=limit)
    return [_to_user_out(u) for u in docs]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _user=Depends(require_roles("admin")),
):
    email = payload.email.lower().strip()
    exists = await db[settings.USERS_COL].find_one({"email": email})
    if exists:
        raise HTTPException(status_code=409, detail="Ese email ya existe")

    doc = {
        "name": payload.name.strip(),
        "email": email,
        "password_hash": pwd_context.hash(payload.password),
        "role": payload.role,
        "estado": int(payload.estado),
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
    current_user=Depends(require_roles("admin")),
):
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="user_id inválido")

    me_id = _str_id(current_user.get("_id", ""))
    if me_id and me_id == user_id and role != "admin":
        raise HTTPException(status_code=400, detail="No puedes quitarte el rol admin a ti mismo")

    res = await db[settings.USERS_COL].update_one({"_id": oid}, {"$set": {"role": role}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    u = await db[settings.USERS_COL].find_one({"_id": oid})
    return _to_user_out(u)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user=Depends(require_roles("admin")),
):
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="user_id inválido")

    existing = await db[settings.USERS_COL].find_one({"_id": oid})
    if not existing:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    me_id = _str_id(current_user.get("_id", ""))
    update_doc: dict = {}

    if payload.name is not None:
        update_doc["name"] = payload.name.strip()

    if payload.email is not None:
        new_email = payload.email.lower().strip()
        if new_email != (existing.get("email") or "").lower():
            exists = await db[settings.USERS_COL].find_one({"email": new_email})
            if exists and str(exists.get("_id")) != user_id:
                raise HTTPException(status_code=409, detail="Ese email ya existe")
        update_doc["email"] = new_email

    if payload.password is not None:
        update_doc["password_hash"] = pwd_context.hash(payload.password)

    if payload.role is not None:
        if me_id and me_id == user_id and payload.role != "admin":
            raise HTTPException(status_code=400, detail="No puedes quitarte el rol admin a ti mismo")
        update_doc["role"] = payload.role

    if payload.estado is not None:
        if me_id and me_id == user_id and int(payload.estado) == 0:
            raise HTTPException(status_code=400, detail="No puedes desactivarte a ti mismo")
        update_doc["estado"] = int(payload.estado)

    if not update_doc:
        return _to_user_out(existing)

    await db[settings.USERS_COL].update_one({"_id": oid}, {"$set": update_doc})
    u = await db[settings.USERS_COL].find_one({"_id": oid})
    return _to_user_out(u)


@router.patch("/{user_id}/estado", response_model=UserOut)
async def set_estado(
    user_id: str,
    payload: UserEstadoUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user=Depends(require_roles("admin")),
):
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="user_id inválido")

    me_id = _str_id(current_user.get("_id", ""))
    if me_id and me_id == user_id and int(payload.estado) == 0:
        raise HTTPException(status_code=400, detail="No puedes desactivarte a ti mismo")

    res = await db[settings.USERS_COL].update_one({"_id": oid}, {"$set": {"estado": int(payload.estado)}})
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
    me_id = _str_id(current_user.get("_id", ""))
    if me_id and me_id == user_id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario")

    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="user_id inválido")

    res = await db[settings.USERS_COL].delete_one({"_id": oid})
    if res.deleted_count != 1:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    return {"deleted": True, "user_id": user_id}