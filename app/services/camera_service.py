from __future__ import annotations

from typing import Any, Dict, List, Optional


class CameraService:
    """
    SRP: toda la lógica de negocio de cámaras vive aquí.
    DIP: recibe repo + manager por constructor (no importa la implementación concreta).
    """

    def __init__(self, repo, manager) -> None:
        self._repo = repo
        self._manager = manager

    async def list(self) -> List[Dict[str, Any]]:
        return await self._repo.list()

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Aquí podrías aplicar reglas extra (validar RTSP, etc.)
        return await self._repo.create(**data)

    async def update(self, camera_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return await self._repo.update(camera_id, patch)

    async def delete(self, camera_id: str) -> bool:
        ok = await self._repo.delete(camera_id)
        if ok:
            # Regla de negocio: si se elimina, se detiene el stream
            self._manager.stop(camera_id)
        return ok

    async def start(self, camera_id: str) -> Dict[str, Any]:
        doc = await self._repo.get(camera_id)
        if not doc:
            return {"ok": False, "error": "not_found"}

        if not doc.get("enabled", True):
            return {"ok": False, "error": "disabled"}

        self._manager.start(
            camera_id=camera_id,
            rtsp_url=doc["rtsp_url"],
            fps_target=int(doc.get("fps_target", 5)),
            infer_every_n_frames=int(doc.get("infer_every_n_frames", 5)),
        )
        return {"ok": True, "camera_id": camera_id, "running": True}

    def stop(self, camera_id: str) -> Dict[str, Any]:
        self._manager.stop(camera_id)
        return {"camera_id": camera_id, "running": False}

    def status(self) -> Dict[str, Any]:
        return self._manager.status()
