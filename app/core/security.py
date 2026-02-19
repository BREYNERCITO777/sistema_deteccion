from __future__ import annotations

from typing import Any, Dict, Callable, Optional
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from motor.motor_asyncio import AsyncIOMotorDatabase
from jose import jwt, JWTError
from bson import ObjectId

from app.core.config import settings
from app.core.database import get_db


oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_PREFIX}/auth/login")


def create_access_token(*, sub: str, role: str, expires_minutes: Optional[int] = None) -> str:
    now = datetime.now(timezone.utc)
    exp_min = expires_minutes if expires_minutes is not None else settings.JWT_EXPIRE_MIN
    payload = {
        "sub": sub,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=exp_min)).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def _unauthorized(detail: str = "No autorizado") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def decode_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
    except JWTError:
        raise _unauthorized("Token inválido o expirado")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> Dict[str, Any]:
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise _unauthorized("Token sin 'sub'")

    try:
        oid = ObjectId(user_id)
    except Exception:
        raise _unauthorized("Token sub inválido")

    user = await db[settings.USERS_COL].find_one({"_id": oid})
    if not user:
        raise _unauthorized("Usuario no existe")

    user["_id"] = str(user["_id"])
    user.pop("password_hash", None)
    return user


def require_auth(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return user


def require_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Requiere rol admin")
    return user


def require_roles(*allowed: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    def _dep(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if user.get("role") not in allowed:
            raise HTTPException(status_code=403, detail="No tienes permisos")
        return user
    return _dep
