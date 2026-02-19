from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from passlib.context import CryptContext

from app.core.database import get_db
from app.core.security import create_access_token, require_auth
from app.models.schemas import UserRegister, UserLogin, UserOut, TokenOut
from app.repositories.user_repository import UserRepository

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.post("/register", response_model=UserOut)
async def register(payload: UserRegister, db: AsyncIOMotorDatabase = Depends(get_db)):
    repo = UserRepository(db)

    existing = await repo.get_by_email(payload.email)
    if existing:
        raise HTTPException(400, "Email ya registrado")

    password_hash = pwd_context.hash(payload.password)
    created = await repo.create(email=payload.email, password_hash=password_hash, role=payload.role)
    return created


@router.post("/login", response_model=TokenOut)
async def login(payload: UserLogin, db: AsyncIOMotorDatabase = Depends(get_db)):
    repo = UserRepository(db)
    user = await repo.get_by_email(payload.email)
    if not user:
        raise HTTPException(401, "Credenciales inválidas")

    if not pwd_context.verify(payload.password, user.get("password_hash", "")):
        raise HTTPException(401, "Credenciales inválidas")

    token = create_access_token(sub=str(user["_id"]), role=user.get("role", "operator"))
    return TokenOut(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(user=Depends(require_auth)):
    return user
