from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.core.config import settings
from fastapi import Depends

class Mongo:
    client: AsyncIOMotorClient | None = None
    db: AsyncIOMotorDatabase | None = None


mongo = Mongo()


def connect_db() -> None:
    if mongo.client is not None and mongo.db is not None:
        return
    mongo.client = AsyncIOMotorClient(settings.MONGO_URL)
    mongo.db = mongo.client[settings.MONGO_DB]


def close_db() -> None:
    if mongo.client is not None:
        mongo.client.close()
    mongo.client = None
    mongo.db = None


def get_db() -> AsyncIOMotorDatabase:
    if mongo.db is None:
        raise RuntimeError("DB no inicializada")
    return mongo.db
