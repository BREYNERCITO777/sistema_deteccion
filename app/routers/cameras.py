from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.repositories.camera_repository import CameraRepository
from app.services.camera_manager import camera_manager
from app.repositories.incident_repository import IncidentRepository

# (opcional) proteger:
# from app.core.security import get_current_user

router = APIRouter(prefix="/cameras", tags=["Cameras"])


class CameraCreate(BaseModel):
    name: str = Field(..., min_length=2)
    rtsp_url: str = Field(..., min_length=5)
    enabled: bool = True
    fps_target: int = 5
    infer_every_n_frames: int = 5


class CameraPatch(BaseModel):
    name: Optional[str] = None
    rtsp_url: Optional[str] = None
    enabled: Optional[bool] = None
    fps_target: Optional[int] = None
    infer_every_n_frames: Optional[int] = None


@router.get("")
async def list_cameras(
    db: AsyncIOMotorDatabase = Depends(get_db),
    # user=Depends(get_current_user),
):
    return await CameraRepository(db).list()


@router.post("")
async def create_camera(
    payload: CameraCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    # user=Depends(get_current_user),
):
    return await CameraRepository(db).create(**payload.model_dump())


@router.patch("/{camera_id}")
async def update_camera(
    camera_id: str,
    payload: CameraPatch,
    db: AsyncIOMotorDatabase = Depends(get_db),
    # user=Depends(get_current_user),
):
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    doc = await CameraRepository(db).update(camera_id, patch)
    if not doc:
        raise HTTPException(404, "Cámara no encontrada")
    return doc


@router.delete("/{camera_id}")
async def delete_camera(
    camera_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    # user=Depends(get_current_user),
):
    ok = await CameraRepository(db).delete(camera_id)
    if not ok:
        raise HTTPException(404, "Cámara no encontrada")
    camera_manager.stop(camera_id)
    return {"deleted": True}


@router.post("/{camera_id}/start")
async def start_camera(camera_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    cam = await CameraRepository(db).get(camera_id)
    if not cam:
        raise HTTPException(404, "Cámara no encontrada")
    if not cam.get("enabled", True):
        raise HTTPException(400, "Cámara deshabilitada")

    incident_repo = IncidentRepository(db)

    async def on_incident(payload: dict):
        # aquí guardarías incidente real cuando detectes en stream
        await incident_repo.create(
            weapon_type=payload["weapon_type"],
            confidence=payload["confidence"],
            evidence_url=payload.get("evidence_url"),
            camera_id=payload.get("camera_id"),
        )

    camera_manager.start(
        camera_id=camera_id,
        rtsp_url=cam["rtsp_url"],
        fps_target=int(cam.get("fps_target", 5)),
        infer_every_n_frames=int(cam.get("infer_every_n_frames", 5)),
        on_incident=on_incident,
    )

    return {"camera_id": camera_id, "running": True}



@router.post("/{camera_id}/stop")
async def stop_camera(
    camera_id: str,
    # user=Depends(get_current_user),
):
    camera_manager.stop(camera_id)
    return {"camera_id": camera_id, "running": False}


@router.get("/status")
async def cameras_status(
    # user=Depends(get_current_user),
):
    return camera_manager.status()
