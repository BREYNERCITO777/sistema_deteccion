from __future__ import annotations

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_db
from app.repositories.incident_repository import IncidentRepository

router = APIRouter(prefix="/incidents", tags=["Incidents"])


@router.get("")
async def listar_incidentes(limit: int = 50, db: AsyncIOMotorDatabase = Depends(get_db)):
    return await IncidentRepository(db).list(limit=limit)


@router.delete("")
async def borrar_todo(db: AsyncIOMotorDatabase = Depends(get_db)):
    deleted = await IncidentRepository(db).delete_all()
    return {"deleted": deleted}
