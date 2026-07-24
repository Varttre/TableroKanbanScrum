"""CRUD de proyectos. Las columnas (con límite y contador WIP) viven embebidas.
Administración: solo moderadores (D-17)."""

from fastapi import APIRouter, HTTPException

from app.db import db
from app.modelos import ProyectoActualizar, ProyectoCrear
from app.servicios import exigir_miembro, exigir_moderador
from app.utiles import a_json, o_404, oid

router = APIRouter(prefix="/proyectos", tags=["proyectos"])

COLUMNAS_DEFECTO = [
    {"clave": "backlog", "nombre": "Backlog", "orden": 1, "limiteWip": None, "wip": 0},
    {"clave": "todo",    "nombre": "To Do",   "orden": 2, "limiteWip": None, "wip": 0},
    {"clave": "doing",   "nombre": "Doing",   "orden": 3, "limiteWip": 5,    "wip": 0},
    {"clave": "done",    "nombre": "Done",    "orden": 4, "limiteWip": None, "wip": 0},
]


def resolver_miembros(ids: list[str]):
    """Convierte ids en {usuarioId, nombre}: el nombre se denormaliza aquí."""
    miembros = []
    for id_str in ids:
        u = o_404(db.usuarios.find_one({"_id": oid(id_str), "activo": True}), "usuario")
        miembros.append({"usuarioId": u["_id"], "nombre": u["nombre"]})
    return miembros


@router.get("")
def listar(incluirInactivos: bool = False):
    filtro = {} if incluirInactivos else {"activo": True}
    return a_json(list(db.proyectos.find(filtro).sort("nombre")))


@router.get("/{id}")
def obtener(id: str):
    return a_json(o_404(db.proyectos.find_one({"_id": oid(id)}), "proyecto"))


@router.post("", status_code=201)
def crear(datos: ProyectoCrear):
    creador = exigir_moderador(datos.usuarioId)
    miembros = resolver_miembros(datos.miembros)
    # el creador entra al equipo automáticamente: sin membresía no podría ni
    # administrar el proyecto que acaba de crear (D-18)
    if all(m["usuarioId"] != creador["_id"] for m in miembros):
        miembros.append({"usuarioId": creador["_id"], "nombre": creador["nombre"]})
    doc = {
        "nombre": datos.nombre, "cliente": datos.cliente, "estado": "activo",
        "columnas": [dict(c) for c in COLUMNAS_DEFECTO],
        "miembros": miembros, "activo": True,
    }
    db.proyectos.insert_one(doc)
    return a_json(doc)


@router.patch("/{id}")
def actualizar(id: str, datos: ProyectoActualizar):
    exigir_moderador(datos.usuarioId)
    pid = oid(id)
    exigir_miembro(datos.usuarioId, pid)  # administra quien está en el equipo (D-18)
    proyecto = o_404(db.proyectos.find_one({"_id": pid, "activo": True}), "proyecto")
    cambios = {}
    enviados = datos.model_dump(exclude_unset=True)

    for campo in ("nombre", "cliente", "estado"):
        if campo in enviados:
            cambios[campo] = enviados[campo]
    if "miembros" in enviados:
        cambios["miembros"] = resolver_miembros(enviados["miembros"])

    if cambios:
        db.proyectos.update_one({"_id": pid}, {"$set": cambios})
    if "nombre" in cambios:
        # mantener la denormalización de proyectoNombre en las tarjetas
        db.tarjetas.update_many({"proyectoId": pid},
                                {"$set": {"proyectoNombre": cambios["nombre"]}})

    # límites WIP por columna: {"doing": 4} o {"doing": null} para quitar el límite
    if "limitesWip" in enviados:
        claves = {c["clave"] for c in proyecto["columnas"]}
        for clave, limite in enviados["limitesWip"].items():
            if clave not in claves:
                raise HTTPException(400, f"Columna inexistente: {clave}")
            db.proyectos.update_one({"_id": pid, "columnas.clave": clave},
                                    {"$set": {"columnas.$.limiteWip": limite}})
    return a_json(db.proyectos.find_one({"_id": pid}))


@router.delete("/{id}")
def desactivar(id: str, usuarioId: str):
    exigir_moderador(usuarioId)
    exigir_miembro(usuarioId, oid(id))
    o_404(db.proyectos.find_one_and_update(
        {"_id": oid(id), "activo": True}, {"$set": {"activo": False}}), "proyecto")
    return {"desactivado": id, "nota": "borrado lógico (D-09)"}
