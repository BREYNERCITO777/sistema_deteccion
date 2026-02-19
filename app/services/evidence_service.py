from __future__ import annotations

import os
import uuid
import cv2

from app.core.config import settings


def draw_boxes(frame, detections):
    for d in detections:
        x1, y1, x2, y2 = d["box"]
        p1 = (int(x1), int(y1))
        p2 = (int(x2), int(y2))

        cv2.rectangle(frame, p1, p2, (0, 0, 255), 2)
        label = f'{d["class_name"]} {int(d["confidence"]*100)}%'
        cv2.putText(frame, label, (p1[0], max(p1[1] - 8, 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    return frame


def save_evidence(frame, detections) -> str:
    os.makedirs(settings.STATIC_DIR, exist_ok=True)

    frame2 = frame.copy()
    frame2 = draw_boxes(frame2, detections)

    filename = f"evidence_{uuid.uuid4().hex}.jpg"
    path = os.path.join(settings.STATIC_DIR, filename)

    ok = cv2.imwrite(path, frame2)
    if not ok:
        raise RuntimeError("No se pudo guardar la evidencia")

    return f"/static/{filename}"