from __future__ import annotations

from typing import Any, Dict, Optional
from bson import ObjectId


def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception as e:
        raise ValueError("ObjectId inválido") from e


def normalize_id(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not doc:
        return None
    doc["_id"] = str(doc["_id"])
    return doc


def normalize_many(items):
    return [normalize_id(x) for x in items if x]
