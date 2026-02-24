from __future__ import annotations

import time
import asyncio
import cv2
from typing import Optional, Any, Dict

from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Depends, Query
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

from app.core.database import get_db
from app.core.websocket_manager import manager
from app.core.config import settings

from app.core.security import decode_token  # ✅ para validar JWT (query token o bearer)
from app.repositories.incident_repository import IncidentRepository
from app.repositories.alert_repository import alert_repo
from app.services.detection_service import DetectionService
from app.services.evidence_service import save_evidence

router = APIRouter(prefix="/inference", tags=["Inference"])
service = DetectionService()

# ==========================================
# CONFIGURACIÓN: Nivel de Confianza Mínimo
# ==========================================
MIN_CONFIDENCE = 0.70


def _severity_from_conf(conf: float) -> str:
    if conf >= 0.90:
        return "critical"
    if conf >= 0.80:
        return "high"
    if conf >= 0.70:
        return "medium"
    return "low"


def _alert_title(weapon_type: str, severity: str) -> str:
    if severity == "critical":
        return "Detección Crítica"
    if severity == "high":
        return "Detección Alta"
    return "Detección"


def _alert_message(weapon_type: str, confidence: float, camera_id: str | None) -> str:
    cam = camera_id or "—"
    return f'Se detectó "{weapon_type}" con {(confidence*100):.0f}% de confianza. Cámara: {cam}'


# ==========================================================
# ✅ Auth helper: acepta Bearer header o ?token=...
# ==========================================================
def _extract_bearer(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth:
        return None
    auth = auth.strip()
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return None


async def _get_user_from_token(token: str, db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token sin 'sub'")

    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=401, detail="Token sub inválido")

    user = await db[settings.USERS_COL].find_one({"_id": oid})
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no existe")

    # normalizar
    user["_id"] = str(user["_id"])
    user.pop("password_hash", None)
    return user


async def require_roles_stream(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    token: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """
    ✅ Para streaming: permite autenticar por:
    - Header Authorization: Bearer <jwt>
    - Query param ?token=<jwt> (para <img src="...">)
    """
    jwt_token = _extract_bearer(request) or token
    if not jwt_token:
        raise HTTPException(status_code=401, detail="No autorizado")

    user = await _get_user_from_token(jwt_token, db)
    if user.get("role") not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="No tienes permisos")

    return user


# ==========================================
# ENDPOINT 1: Detección por foto estática
# (si quieres, puedes restringirlo solo a admin)
# ==========================================
@router.post("/detectar")
async def detectar(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
    _user: Dict[str, Any] = Depends(require_roles_stream),  # ✅ admin/operator ok
):
    t0 = time.time()
    try:
        model = getattr(request.app.state, "yolo_model", None)
        if model is None:
            raise RuntimeError("Modelo no cargado en el servidor")

        image_bytes = await file.read()
        frame, raw_detections, infer_ms = service.detect(model, image_bytes)
        detections = [d for d in raw_detections if d.get("confidence", 0.0) >= MIN_CONFIDENCE]

        if not detections:
            return {
                "detections": [],
                "latency_infer_ms": infer_ms,
                "latency_e2e_ms": round((time.time() - t0) * 1000, 2),
                "evidence_url": None,
            }

        # Guardar evidencia (imagen con cajas)
        evidence_url = save_evidence(frame, detections)

        # top detection
        top = max(detections, key=lambda d: d["confidence"])
        weapon_type = top["class_name"]
        confidence = float(top["confidence"])
        severity = _severity_from_conf(confidence)

        # Crear incidente
        incident_repo = IncidentRepository(db)
        incident = await incident_repo.create(
            weapon_type=weapon_type,
            confidence=confidence,
            evidence_url=evidence_url,
            camera_id=None,
        )

        # Crear alerta en BD
        await alert_repo.create(
            db,
            title=_alert_title(weapon_type, severity),
            message=_alert_message(weapon_type, confidence, None),
            severity=severity,
            weapon_type=weapon_type,
            confidence=confidence,
            evidence_url=evidence_url,
            camera_id=None,
            read=False,
        )

        # WebSocket broadcast
        await manager.broadcast(
            {
                "type": "ALERTA",
                "weapon_type": weapon_type,
                "confidence": confidence,
                "evidence_url": evidence_url,
                "camera_id": None,
                "timestamp": incident.get("timestamp", time.time()),
                "severity": severity,
            }
        )

        return {
            "detections": detections,
            "latency_infer_ms": infer_ms,
            "latency_e2e_ms": round((time.time() - t0) * 1000, 2),
            "evidence_url": evidence_url,
            "incident_id": str(incident["_id"]),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================================
# ✅ Resolver fuente real: camera_id -> rtsp_url en Mongo
# ==========================================================
async def _resolve_camera_source(camera_id: str, db: AsyncIOMotorDatabase) -> int | str:
    # Caso especial: webcam local
    if camera_id == "0":
        return 0

    # Buscar en colección CAMERAS por _id
    try:
        oid = ObjectId(camera_id)
    except Exception:
        raise HTTPException(status_code=400, detail="camera_id inválido")

    cam = await db[settings.CAMERAS_COL].find_one({"_id": oid})
    if not cam:
        raise HTTPException(status_code=404, detail="Cámara no encontrada")

    rtsp = cam.get("rtsp_url")
    if not rtsp:
        raise HTTPException(status_code=400, detail="La cámara no tiene rtsp_url")

    # Si guardaste "0", "1", etc en string, lo convertimos a int
    if isinstance(rtsp, str) and rtsp.isdigit():
        return int(rtsp)

    return str(rtsp)


# ==========================================
# Generador de Video en Vivo con Control de Estado
# ==========================================
async def generar_frames(
    request: Request,
    camera_id: str,
    camera_source: int | str,
    model,
    db: AsyncIOMotorDatabase,
):
    cap = cv2.VideoCapture(camera_source)
    last_alert_time = 0
    COOLDOWN_SECONDS = 5.0

    active_streams = getattr(request.app.state, "active_streams", {})

    try:
        while cap.isOpened() and active_streams.get(camera_id, False):
            success, frame = cap.read()
            if not success:
                await asyncio.sleep(0.1)
                continue

            ret, buffer = cv2.imencode(".jpg", frame)
            if not ret:
                continue
            image_bytes = buffer.tobytes()

            procesado_frame, raw_detections, infer_ms = service.detect(model, image_bytes)
            detections = [d for d in raw_detections if d.get("confidence", 0.0) >= MIN_CONFIDENCE]

            frame_para_dibujar = frame.copy()

            if detections:
                for det in detections:
                    box = det.get("box", [])
                    if len(box) == 4:
                        x1, y1, x2, y2 = map(int, box)
                        cv2.rectangle(frame_para_dibujar, (x1, y1), (x2, y2), (0, 0, 255), 2)

                        etiqueta = f"{det['class_name']} {(det['confidence']*100):.0f}%"
                        (tw, th), baseline = cv2.getTextSize(
                            etiqueta, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2
                        )
                        y_text = max(y1 - 10, th + 10)
                        cv2.rectangle(
                            frame_para_dibujar,
                            (x1, y_text - th - 8),
                            (x1 + tw + 8, y_text + baseline),
                            (0, 0, 0),
                            -1,
                        )
                        cv2.putText(
                            frame_para_dibujar,
                            etiqueta,
                            (x1 + 4, y_text - 4),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (0, 0, 255),
                            2,
                            cv2.LINE_AA,
                        )

                current_time = time.time()
                if (current_time - last_alert_time) > COOLDOWN_SECONDS:
                    top = max(detections, key=lambda d: d["confidence"])
                    weapon_type = top["class_name"]
                    confidence = float(top["confidence"])
                    severity = _severity_from_conf(confidence)

                    evidence_url = save_evidence(frame_para_dibujar, detections)

                    incident_repo = IncidentRepository(db)
                    incident = await incident_repo.create(
                        weapon_type=weapon_type,
                        confidence=confidence,
                        evidence_url=evidence_url,
                        camera_id=camera_id,
                    )

                    await alert_repo.create(
                        db,
                        title=_alert_title(weapon_type, severity),
                        message=_alert_message(weapon_type, confidence, camera_id),
                        severity=severity,
                        weapon_type=weapon_type,
                        confidence=confidence,
                        evidence_url=evidence_url,
                        camera_id=camera_id,
                        read=False,
                    )

                    await manager.broadcast(
                        {
                            "type": "ALERTA",
                            "weapon_type": weapon_type,
                            "confidence": confidence,
                            "evidence_url": evidence_url,
                            "camera_id": camera_id,
                            "timestamp": incident.get("timestamp", current_time),
                            "severity": severity,
                        }
                    )

                    last_alert_time = current_time

            ret2, buffer2 = cv2.imencode(".jpg", frame_para_dibujar)
            if not ret2:
                continue
            frame_listo = buffer2.tobytes()

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame_listo + b"\r\n"
            )

            await asyncio.sleep(0.01)

    finally:
        cap.release()
        active_streams[camera_id] = False
        print(f"--- CONEXIÓN CERRADA Y RECURSOS LIBERADOS PARA CÁMARA {camera_id} ---")


@router.get("/stream/{camera_id}")
async def video_stream(
    camera_id: str,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _user: Dict[str, Any] = Depends(require_roles_stream),  # ✅ admin/operator pueden VER
):
    model = getattr(request.app.state, "yolo_model", None)
    if model is None:
        raise HTTPException(status_code=500, detail="Modelo YOLO no cargado")

    # ✅ activar semáforo
    request.app.state.active_streams[camera_id] = True

    # ✅ ahora sí: rtsp_url real desde Mongo (o 0)
    camera_source = await _resolve_camera_source(camera_id, db)

    return StreamingResponse(
        generar_frames(request, camera_id, camera_source, model, db),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )