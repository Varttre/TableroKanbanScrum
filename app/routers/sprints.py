"""CRUD de sprints. Regla: un solo sprint activo por proyecto.
Administración: solo moderadores."""

from fastapi import APIRouter

from app.db import db
from app.modelos import SprintActualizar, SprintCrear
from app.servicios import exigir_miembro, exigir_moderador, reconciliar_wip
from app.utiles import a_json, o_404, oid

router = APIRouter(prefix="/sprints", tags=["sprints"])


@router.get("")
def listar(proyectoId: str | None = None, estado: str | None = None):
    filtro: dict = {"activo": {"$ne": False}}
    if proyectoId:
        filtro["proyectoId"] = oid(proyectoId)
    if estado:
        filtro["estado"] = estado
    return a_json(list(db.sprints.find(filtro).sort("fechaInicio", -1)))


@router.get("/{id}")
def obtener(id: str):
    return a_json(o_404(db.sprints.find_one({"_id": oid(id)}), "sprint"))


@router.post("", status_code=201)
def crear(datos: SprintCrear):
    exigir_moderador(datos.usuarioId)
    proyecto = o_404(db.proyectos.find_one(
        {"_id": oid(datos.proyectoId), "activo": True}), "proyecto")
    exigir_miembro(datos.usuarioId, proyecto["_id"])
    doc = (datos.model_dump(exclude={"usuarioId"})
           | {"proyectoId": proyecto["_id"], "activo": True})
    if doc["estado"] == "activo":
        _desactivar_otros(proyecto["_id"])
    db.sprints.insert_one(doc)
    reconciliar_wip(proyecto["_id"])
    return a_json(doc)


def _desactivar_otros(proyecto_id):
    """Cierra cualquier otro sprint activo: el tablero muestra UN sprint a la vez."""
    db.sprints.update_many({"proyectoId": proyecto_id, "estado": "activo"},
                           {"$set": {"estado": "cerrado"}})


@router.patch("/{id}")
def actualizar(id: str, datos: SprintActualizar):
    exigir_moderador(datos.usuarioId)
    sid = oid(id)
    sprint = o_404(db.sprints.find_one({"_id": sid}), "sprint")
    exigir_miembro(datos.usuarioId, sprint["proyectoId"])
    cambios = datos.model_dump(exclude_unset=True, exclude={"usuarioId"})
    if cambios.get("estado") == "activo":
        _desactivar_otros(sprint["proyectoId"])
    if cambios:
        db.sprints.update_one({"_id": sid}, {"$set": cambios})
    if "estado" in cambios:
        # activar o cerrar un sprint cambia qué tarjetas cuentan para el WIP
        reconciliar_wip(sprint["proyectoId"])
    return a_json(db.sprints.find_one({"_id": sid}))


@router.delete("/{id}")
def desactivar(id: str, usuarioId: str):
    exigir_moderador(usuarioId)
    s0 = o_404(db.sprints.find_one({"_id": oid(id)}), "sprint")
    exigir_miembro(usuarioId, s0["proyectoId"])
    s = o_404(db.sprints.find_one_and_update(
        {"_id": oid(id), "activo": {"$ne": False}}, {"$set": {"activo": False}}), "sprint")
    reconciliar_wip(s["proyectoId"])
    return {"desactivado": id, "nota": "borrado lógico (D-09)"}
