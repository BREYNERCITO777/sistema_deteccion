from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from motor.motor_asyncio import AsyncIOMotorDatabase
from passlib.context import CryptContext

from app.core.database import get_db
from app.core.config import settings
from app.core.security import create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def allowed_modules_for(role: str) -> list[str]:
    # ✅ Fuente de verdad de permisos por rol (para tu tesis)
    if role == "admin":
        return [
            "dashboard",
            "cameras",
            "incidents",
            "evidence",
            "alerts",
            "settings",
            "users",
        ]
    # operator
    return [
        "dashboard",
        "incidents",
        "evidence",
        "alerts",
    ]


@router.post("/login")
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    # OAuth2PasswordRequestForm usa: username, password (aunque sea email)
    user = await db[settings.USERS_COL].find_one({"email": form.username})
    if not user:
        raise HTTPException(401, "Credenciales inválidas")

    if not verify_password(form.password, user.get("password_hash", "")):
        raise HTTPException(401, "Credenciales inválidas")

    role = user.get("role", "operator")
    token = create_access_token(sub=str(user["_id"]), role=role)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "_id": str(user["_id"]),
            "email": user.get("email"),
            "name": user.get("name", ""),
            "role": role,
        },
        "allowed_modules": allowed_modules_for(role),
    }


@router.get("/me")
async def me(user=Depends(get_current_user)):
    role = user.get("role", "operator")
    return {
        "user": {
            "_id": user["_id"],
            "email": user.get("email"),
            "name": user.get("name", ""),
            "role": role,
        },
        "allowed_modules": allowed_modules_for(role),
    }