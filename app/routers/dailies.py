"""CRUD de dailies (qué hice / qué haré / qué me bloquea).

Aquí vive el `deleteOne` FÍSICO del proyecto: una daily registrada por error se
elimina de verdad y se vuelve a registrar. Es seguro porque las dailies no
alimentan ningún pipeline (las métricas salen de `eventos` y `tarjetas`).
"""

from fastapi import APIRouter, HTTPException
from pymongo.errors import DuplicateKeyError

from app.db import db
from app.modelos import DailyCrear, ParticipacionUpsert
from app.servicios import exigir_miembro, nombre_usuario
from app.utiles import a_json, o_404, oid

router = APIRouter(prefix="/dailies", tags=["dailies"])


def _participacion_doc(p):
    uid_ = oid(p.usuarioId)
    return {"usuarioId": uid_, "nombre": nombre_usuario(uid_),
            "hice": p.hice, "hare": p.hare, "bloqueo": p.bloqueo}


@router.get("")
def listar(sprintId: str | None = None):
    filtro: dict = {}
    if sprintId:
        filtro["sprintId"] = oid(sprintId)
    return a_json(list(db.dailies.find(filtro).sort("fecha", -1)))


@router.get("/{id}")
def obtener(id: str):
    return a_json(o_404(db.dailies.find_one({"_id": oid(id)}), "daily"))


@router.post("", status_code=201)
def crear(datos: DailyCrear):
    sprint = o_404(db.sprints.find_one({"_id": oid(datos.sprintId)}), "sprint")
    exigir_miembro(datos.usuarioId, sprint["proyectoId"])  # la abre el equipo (D-18)
    dia = datos.fecha.date()
    # una sola daily por (sprint, día): la ceremonia ocurre una vez al día
    for d in db.dailies.find({"sprintId": sprint["_id"]}, {"fecha": 1}):
        if d["fecha"].date() == dia:
            raise HTTPException(409, f"Ya existe la daily del {dia} para este sprint")
    doc = {"sprintId": sprint["_id"], "fecha": datos.fecha,
           "participaciones": [_participacion_doc(p) for p in datos.participaciones]}
    try:
        db.dailies.insert_one(doc)
    except DuplicateKeyError:
        # el índice único {sprintId, fecha} (C11) atrapa la carrera que el
        # chequeo de arriba no ve: dos registros simultáneos del mismo momento
        raise HTTPException(409, f"Ya existe la daily del {dia} para este sprint")
    return a_json(doc)


@router.patch("/{id}/participacion")
def registrar_participacion(id: str, datos: ParticipacionUpsert):
    """Agrega (o reemplaza) la participación de un usuario en la daily: cada
    integrante registra su parte cuando le toca hablar."""
    did = oid(id)
    daily = o_404(db.dailies.find_one({"_id": did}), "daily")
    sprint = o_404(db.sprints.find_one({"_id": daily["sprintId"]}), "sprint")
    exigir_miembro(datos.participacion.usuarioId, sprint["proyectoId"])
    p = _participacion_doc(datos.participacion)
    # Primero intenta REEMPLAZAR en el sitio (arrayFilters): una sola escritura
    # atómica, sin la ventana pull→push en la que la participación no existe.
    r = db.dailies.update_one(
        {"_id": did, "participaciones.usuarioId": p["usuarioId"]},
        {"$set": {"participaciones.$[misma]": p}},
        array_filters=[{"misma.usuarioId": p["usuarioId"]}],
    )
    if r.matched_count == 0:  # aún no había participado: se agrega
        db.dailies.update_one({"_id": did}, {"$push": {"participaciones": p}})
    return a_json(db.dailies.find_one({"_id": did}))


@router.delete("/{id}")
def eliminar(id: str, usuarioId: str):
    """Borrado FÍSICO con deleteOne: la D literal del CRUD, demostrable en vivo."""
    daily = o_404(db.dailies.find_one({"_id": oid(id)}), "daily")
    sprint = o_404(db.sprints.find_one({"_id": daily["sprintId"]}), "sprint")
    exigir_miembro(usuarioId, sprint["proyectoId"])
    r = db.dailies.delete_one({"_id": oid(id)})
    if r.deleted_count == 0:
        raise HTTPException(404, "No existe la daily")
    return {"eliminada": id, "nota": "deleteOne físico: la daily no alimenta métricas"}
