"""Consulta del historial. SOLO LECTURA: la colección es append-only (D-04).

Los eventos los escribe el sistema en cada mutación de tarjeta (app/servicios.py).
No hay POST, PATCH ni DELETE: exponerlos destruiría la garantía de la que dependen
burndown, cycle time y velocity. La justificación completa está en el informe.
"""

from fastapi import APIRouter
from pymongo import DESCENDING

from app.db import db
from app.utiles import a_json, oid

router = APIRouter(prefix="/eventos", tags=["eventos"])


@router.get("")
def listar(tarjetaId: str | None = None, tipo: str | None = None, limite: int = 100):
    filtro: dict = {}
    if tarjetaId:
        filtro["tarjetaId"] = oid(tarjetaId)
    if tipo:
        filtro["tipo"] = tipo
    return a_json(list(db.eventos.find(filtro)
                       .sort("timestamp", DESCENDING).limit(min(limite, 500))))


@router.get("/tarjeta/{tarjetaId}")
def historial(tarjetaId: str):
    """Historial cronológico completo de una tarjeta (C14): su auditoría."""
    return a_json(list(db.eventos.find({"tarjetaId": oid(tarjetaId)}).sort("timestamp")))
