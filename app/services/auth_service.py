from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from jose import jwt, JWTError
from passlib.context import CryptContext
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.repositories.user_repository import UserRepository


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.users = UserRepository(db)

    def _hash_password(self, password: str) -> str:
        return pwd_context.hash(password)

    def _verify_password(self, password: str, hashed: str) -> bool:
        return pwd_context.verify(password, hashed)

    def _create_access_token(self, sub: str, role: str) -> str:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MIN)
        payload = {
            "sub": sub,
            "role": role,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
        }
        return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)

    def _decode_token(self, token: str) -> Dict[str, Any]:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])

    async def register(self, email: str, password: str, role: str = "admin") -> Dict[str, Any]:
        email = email.strip().lower()

        existing = await self.users.get_by_email(email)
        if existing:
            raise ValueError("El email ya está registrado")

        password_hash = self._hash_password(password)
        return await self.users.create(email=email, password_hash=password_hash, role=role)

    async def login(self, email: str, password: str) -> Dict[str, Any]:
        email = email.strip().lower()

        user = await self.users.get_by_email(email)
        if not user:
            raise ValueError("Credenciales inválidas")

        if not self._verify_password(password, user["password_hash"]):
            raise ValueError("Credenciales inválidas")

        token = self._create_access_token(sub=str(user["_id"]), role=user.get("role", "admin"))
        return {"access_token": token, "token_type": "bearer"}

    async def me(self, token: str) -> Dict[str, Any]:
        try:
            payload = self._decode_token(token)
            user_id = payload.get("sub")
            if not user_id:
                raise ValueError("Token inválido")
        except JWTError:
            raise ValueError("Token inválido o expirado")

        user = await self.users.get_by_id(user_id)
        if not user:
            raise ValueError("Usuario no encontrado")
        return user
