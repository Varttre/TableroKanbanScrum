"""CRUD de tarjetas + operaciones de negocio (mover, bloquear, comentar).

Toda mutación escribe su evento — eso ocurre en app/servicios.py, que es
la única puerta de entrada a los cambios de estado de una tarjeta.
"""

from fastapi import APIRouter
from pymongo import ASCENDING

from app import servicios
from app.db import db
from app.modelos import (BloquearTarjeta, ComentarioCrear, DesbloquearTarjeta,
                         MoverTarjeta, TarjetaActualizar, TarjetaCrear)
from app.utiles import a_json, o_404, oid

router = APIRouter(prefix="/tarjetas", tags=["tarjetas"])


@router.get("")
def listar(proyectoId: str | None = None, sprintId: str | None = None,
           asignadoA: str | None = None, columna: str | None = None,
           soloRaiz: bool = False, incluirInactivas: bool = False):
    """Listado con los filtros de la matriz de acceso.

    `sprintId="backlog"` filtra las tarjetas sin sprint (el backlog del proyecto).
    """
    filtro: dict = {} if incluirInactivas else {"activo": True}
    if proyectoId:
        filtro["proyectoId"] = oid(proyectoId)
    if sprintId == "backlog":
        filtro["sprintId"] = None
    elif sprintId:
        filtro["sprintId"] = oid(sprintId)
    if asignadoA:
        filtro["asignadoA"] = oid(asignadoA)
    if columna:
        filtro["columna"] = columna
    if soloRaiz:
        filtro["padreId"] = None
    return a_json(list(db.tarjetas.find(filtro).sort([("asignadoA", ASCENDING),
                                                      ("columna", ASCENDING),
                                                      ("orden", ASCENDING)])))


@router.get("/{id}")
def obtener(id: str):
    return a_json(o_404(db.tarjetas.find_one({"_id": oid(id)}), "tarjeta"))


@router.get("/{id}/hijos")
def hijos(id: str):
    """Hijos directos: un nivel del drill-down."""
    return a_json(list(db.tarjetas.find({"padreId": oid(id), "activo": True}).sort("orden")))


@router.get("/{id}/subarbol")
def subarbol(id: str):
    """Subárbol completo a cualquier profundidad — la consulta estrella del
    materialized path (D-03): un find indexado, sin recursión ni $graphLookup."""
    return a_json(list(db.tarjetas.find({"ancestros": oid(id), "activo": True})
                       .sort([("profundidad", ASCENDING), ("orden", ASCENDING)])))


@router.get("/{id}/permisos")
def permisos(id: str, usuarioId: str):
    """El permiso de líder de D-07 en vivo: una sola consulta indexada sobre
    `ancestros` responde si el usuario manda en esta rama, a cualquier profundidad."""
    t = o_404(db.tarjetas.find_one({"_id": oid(id)}), "tarjeta")
    u = o_404(db.usuarios.find_one({"_id": oid(usuarioId)}), "usuario")
    lider = servicios.es_lider(u["_id"], t)
    return {"usuario": u["nombre"], "rol": u["rol"], "esLiderDeLaRama": lider,
            "puedeArchivar": u["rol"] == "moderador" or lider}


@router.post("", status_code=201)
def crear(datos: TarjetaCrear):
    return a_json(servicios.crear_tarjeta(datos))


@router.patch("/{id}")
def actualizar(id: str, datos: TarjetaActualizar):
    return a_json(servicios.actualizar_tarjeta(oid(id), datos))


@router.delete("/{id}")
def archivar(id: str, usuarioId: str):
    """Borrado lógico del subárbol (D-09) con evento `archivado`."""
    return servicios.archivar_tarjeta(oid(id), usuarioId)


@router.post("/{id}/mover")
def mover(id: str, datos: MoverTarjeta):
    """Movimiento en el tablero 2D con guarda WIP atómica (D-11).
    Responde 409 si la columna destino está en su límite."""
    return a_json(servicios.mover_tarjeta(oid(id), datos))


@router.post("/{id}/bloquear")
def bloquear(id: str, datos: BloquearTarjeta):
    tid = oid(id)
    t = o_404(db.tarjetas.find_one({"_id": tid}), "tarjeta")
    servicios.exigir_miembro(datos.usuarioId, t["proyectoId"])
    ts = servicios.ahora()
    o_404(db.tarjetas.find_one_and_update(
        {"_id": tid, "activo": True, "bloqueado.estado": False},
        {"$set": {"bloqueado": {"estado": True, "motivo": datos.motivo, "desde": ts},
                  "updatedAt": ts}}), "tarjeta desbloqueada")
    servicios.registrar_evento(tid, "bloqueo", None, None, oid(datos.usuarioId),
                               {"motivo": datos.motivo})
    return a_json(db.tarjetas.find_one({"_id": tid}))


@router.post("/{id}/desbloquear")
def desbloquear(id: str, datos: DesbloquearTarjeta):
    tid = oid(id)
    t = o_404(db.tarjetas.find_one({"_id": tid}), "tarjeta")
    servicios.exigir_miembro(datos.usuarioId, t["proyectoId"])
    o_404(db.tarjetas.find_one_and_update(
        {"_id": tid, "activo": True, "bloqueado.estado": True},
        {"$set": {"bloqueado": {"estado": False, "motivo": None, "desde": None},
                  "updatedAt": servicios.ahora()}}), "tarjeta bloqueada")
    servicios.registrar_evento(tid, "desbloqueo", None, None, oid(datos.usuarioId))
    return a_json(db.tarjetas.find_one({"_id": tid}))


@router.post("/{id}/comentarios", status_code=201)
def comentar(id: str, datos: ComentarioCrear):
    from bson import ObjectId
    tid = oid(id)
    t = o_404(db.tarjetas.find_one({"_id": tid}), "tarjeta")
    servicios.exigir_miembro(datos.usuarioId, t["proyectoId"])
    comentario = {
        "_id": ObjectId(), "usuarioId": oid(datos.usuarioId),
        "nombre": servicios.nombre_usuario(oid(datos.usuarioId)),
        "texto": datos.texto, "fecha": servicios.ahora(),
    }
    o_404(db.tarjetas.find_one_and_update(
        {"_id": tid, "activo": True}, {"$push": {"comentarios": comentario}}), "tarjeta")
    return a_json(comentario)


@router.delete("/{id}/comentarios/{comentarioId}")
def eliminar_comentario(id: str, comentarioId: str, usuarioId: str):
    """Borrado FÍSICO del comentario ($pull): el subdocumento desaparece de la BD.
    Es la excepción deliberada al borrado lógico: un comentario no alimenta
    ninguna métrica, así que eliminarlo no rompe el historial."""
    t = o_404(db.tarjetas.find_one({"_id": oid(id)}), "tarjeta")
    servicios.exigir_miembro(usuarioId, t["proyectoId"])
    r = db.tarjetas.update_one({"_id": oid(id)},
                               {"$pull": {"comentarios": {"_id": oid(comentarioId)}}})
    o_404(None if r.modified_count == 0 else r, "comentario")
    return {"eliminado": comentarioId, "nota": "borrado físico del subdocumento"}
