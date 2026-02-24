from __future__ import annotations
from typing import Callable, Iterable
from fastapi import Depends, HTTPException, status

# importa tu dependencia actual que obtiene el usuario desde JWT
from app.core.security import get_current_user  # <- ajusta al nombre real

def require_roles(*allowed_roles: str) -> Callable:
    async def _guard(user=Depends(get_current_user)):
        role = getattr(user, "role", None) or user.get("role")
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para acceder a este recurso",
            )
        return user
    return _guard