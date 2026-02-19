from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings


def _oid(id_str: str) -> ObjectId:
    return ObjectId(id_str)


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    doc["_id"] = str(doc["_id"])
    return doc


class CameraRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.col = db[settings.CAMERAS_COL]

    async def ensure_indexes(self) -> None:
        await self.col.create_index("rtsp_url", unique=True)
        await self.col.create_index("created_at")

    async def create(
        self,
        *,
        name: str,
        rtsp_url: str,
        enabled: bool = True,
        fps_target: int = 5,
        infer_every_n_frames: int = 5,
    ) -> Dict[str, Any]:
        doc = {
            "name": name,
            "rtsp_url": rtsp_url,
            "enabled": enabled,
            "fps_target": int(fps_target),
            "infer_every_n_frames": int(infer_every_n_frames),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        res = await self.col.insert_one(doc)
        doc["_id"] = res.inserted_id
        return _serialize(doc)

    async def list(self) -> List[Dict[str, Any]]:
        cursor = self.col.find({}).sort("created_at", -1)
        docs = await cursor.to_list(length=1000)
        return [_serialize(d) for d in docs]

    async def get(self, camera_id: str) -> Optional[Dict[str, Any]]:
        try:
            d = await self.col.find_one({"_id": _oid(camera_id)})
            return _serialize(d) if d else None
        except Exception:
            return None

    async def update(self, camera_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            await self.col.update_one({"_id": _oid(camera_id)}, {"$set": patch})
            return await self.get(camera_id)
        except Exception:
            return None

    async def delete(self, camera_id: str) -> bool:
        try:
            res = await self.col.delete_one({"_id": _oid(camera_id)})
            return res.deleted_count == 1
        except Exception:
            return False
