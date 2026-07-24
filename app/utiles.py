"""Utilidades compartidas por los routers."""

from bson import ObjectId
from fastapi import HTTPException


def oid(id_str: str) -> ObjectId:
    """Convierte el id de la URL/body a ObjectId, o responde 400 si es inválido."""
    if not ObjectId.is_valid(id_str):
        raise HTTPException(status_code=400, detail=f"Id inválido: {id_str}")
    return ObjectId(id_str)


def a_json(doc):
    """Convierte recursivamente ObjectId → str para que FastAPI pueda serializar.

    PyMongo devuelve ObjectId (tipo BSON) y JSON no lo conoce. Las fechas no se
    tocan: FastAPI ya las serializa a ISO 8601.
    """
    if isinstance(doc, ObjectId):
        return str(doc)
    if isinstance(doc, dict):
        return {k: a_json(v) for k, v in doc.items()}
    if isinstance(doc, list):
        return [a_json(v) for v in doc]
    return doc


def o_404(doc, nombre="documento"):
    """Devuelve el documento o responde 404 si la consulta no encontró nada."""
    if doc is None:
        raise HTTPException(status_code=404, detail=f"No existe el {nombre}")
    return doc
