# app/routers/ws.py
from __future__ import annotations

from typing import Optional, Any, Dict

from bson import ObjectId
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_token
from app.core.websocket_manager import manager

router = APIRouter(tags=["ws"])


def _extract_bearer_from_headers(websocket: WebSocket) -> Optional[str]:
    auth = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    if not auth:
        return None
    auth = auth.strip()
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return None


async def ws_auth(
    websocket: WebSocket,
    db: AsyncIOMotorDatabase = Depends(get_db),
    token: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """
    Autentica WS usando:
    - Query: ?token=...
    - Header: Authorization: Bearer ...
    """
    jwt_token = _extract_bearer_from_headers(websocket) or token
    if not jwt_token:
        # OJO: todavía NO se acepta el websocket aquí → FastAPI responde 403
        raise Exception("No token")

    payload = decode_token(jwt_token)
    user_id = payload.get("sub")
    role = payload.get("role")

    if not user_id:
        raise Exception("Token sin sub")

    if role not in ("admin", "operator"):
        raise Exception("Sin permisos")

    try:
        oid = ObjectId(user_id)
    except Exception:
        raise Exception("sub inválido")

    user = await db[settings.USERS_COL].find_one({"_id": oid})
    if not user:
        raise Exception("Usuario no existe")

    user["_id"] = str(user["_id"])
    user.pop("password_hash", None)
    return user


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    user: Dict[str, Any] = Depends(ws_auth),
):
    # ✅ Solo si autentica, aceptamos conexión
    await manager.connect(websocket)

    try:
        while True:
            # ✅ Mantener viva la conexión leyendo frames
            # (si el cliente no manda nada, esto queda esperando)
            await websocket.receive()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)