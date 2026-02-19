from __future__ import annotations

from ultralytics import YOLO
from app.core.config import settings


def load_yolo_model():
    # settings.MODEL_PATH: "app/models/best.pt"
    return YOLO(settings.MODEL_PATH)
