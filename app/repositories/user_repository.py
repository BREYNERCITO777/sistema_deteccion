from __future__ import annotations

from typing import Any, Dict, List, Optional
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings


def _oid(id_: str) -> ObjectId:
    return ObjectId(id_)


def _sanitize_user(doc: Dict[str, Any]) -> Dict[str, Any]:
    doc["_id"] = str(doc["_id"])
    doc.pop("password_hash", None)
    return doc


class UserRepository:
    """
    Repo con DB inyectada (SOLID).
    """
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.col = db[settings.USERS_COL]

    async def create(self, *, email: str, password_hash: str, role: str) -> Dict[str, Any]:
        doc = {"email": email, "password_hash": password_hash, "role": role}
        res = await self.col.insert_one(doc)
        doc["_id"] = res.inserted_id
        return _sanitize_user(doc)

    async def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        return await self.col.find_one({"email": email})

    async def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            doc = await self.col.find_one({"_id": _oid(user_id)})
            return _sanitize_user(doc) if doc else None
        except Exception:
            return None

    async def list(self, limit: int = 100) -> List[Dict[str, Any]]:
        cursor = self.col.find({}, {"password_hash": 0}).limit(limit)
        docs = await cursor.to_list(length=limit)
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs

    async def delete(self, user_id: str) -> bool:
        try:
            res = await self.col.delete_one({"_id": _oid(user_id)})
            return res.deleted_count == 1
        except Exception:
            return False
