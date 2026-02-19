from __future__ import annotations

import time
from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.database import get_db
from app.core.websocket_manager import manager
from app.repositories.incident_repository import IncidentRepository
from app.services.detection_service import DetectionService
from app.services.evidence_service import save_evidence

# (opcional) proteger:
# from app.core.security import get_current_user

router = APIRouter(prefix="/inference", tags=["Inference"])
service = DetectionService()


@router.post("/detectar")
async def detectar(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
    # user=Depends(get_current_user),  # <-- descomenta si lo quieres protegido
):
    t0 = time.time()
    try:
        model = getattr(request.app.state, "yolo_model", None)
        if model is None:
            raise RuntimeError("Modelo no cargado")

        image_bytes = await file.read()
        frame, detections, infer_ms = service.detect(model, image_bytes)

        if not detections:
            return {
                "detections": [],
                "latency_infer_ms": infer_ms,
                "latency_e2e_ms": round((time.time() - t0) * 1000, 2),
                "evidence_url": None,
            }

        evidence_url = save_evidence(frame, detections)

        top = max(detections, key=lambda d: d["confidence"])

        incident_repo = IncidentRepository(db)
        incident = await incident_repo.create(
            weapon_type=top["class_name"],
            confidence=top["confidence"],
            evidence_url=evidence_url,
        )

        await manager.broadcast(
            {
                "type": "ALERTA",
                "weapon_type": incident["weapon_type"],
                "confidence": incident["confidence"],
                "evidence_url": incident["evidence_url"],
                "timestamp": incident["timestamp"],
            }
        )

        return {
            "detections": detections,
            "latency_infer_ms": infer_ms,
            "latency_e2e_ms": round((time.time() - t0) * 1000, 2),
            "evidence_url": evidence_url,
            "incident_id": incident["_id"],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
