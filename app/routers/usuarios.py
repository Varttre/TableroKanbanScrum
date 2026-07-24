"""CRUD de usuarios. Delete = borrado lógico (D-09). Administración: solo
moderadores (D-17) — la guarda vive en el servidor, no solo en la UI."""

from fastapi import APIRouter

from app.db import db
from app.modelos import UsuarioActualizar, UsuarioCrear
from app.servicios import exigir_moderador
from app.utiles import a_json, o_404, oid

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.get("")
def listar(incluirInactivos: bool = False):
    filtro = {} if incluirInactivos else {"activo": True}
    return a_json(list(db.usuarios.find(filtro).sort("nombre")))


@router.get("/{id}")
def obtener(id: str):
    return a_json(o_404(db.usuarios.find_one({"_id": oid(id)}), "usuario"))


@router.post("", status_code=201)
def crear(datos: UsuarioCrear):
    exigir_moderador(datos.usuarioId)
    doc = datos.model_dump(exclude={"usuarioId"}) | {"activo": True}
    db.usuarios.insert_one(doc)
    return a_json(doc)


@router.patch("/{id}")
def actualizar(id: str, datos: UsuarioActualizar):
    exigir_moderador(datos.usuarioId)
    uid = oid(id)
    cambios = datos.model_dump(exclude_unset=True, exclude={"usuarioId"})
    o_404(db.usuarios.find_one_and_update({"_id": uid}, {"$set": cambios}), "usuario")
    if "nombre" in cambios:
        # quien denormaliza, mantiene: el nombre vive copiado en tarjetas y proyectos
        db.tarjetas.update_many({"asignadoA": uid},
                                {"$set": {"asignadoNombre": cambios["nombre"]}})
        db.proyectos.update_many({"miembros.usuarioId": uid},
                                 {"$set": {"miembros.$.nombre": cambios["nombre"]}})
    return a_json(db.usuarios.find_one({"_id": uid}))


@router.delete("/{id}")
def desactivar(id: str, usuarioId: str):
    """Borrado lógico: el usuario desaparece de la app pero su historial persiste."""
    exigir_moderador(usuarioId)
    o_404(db.usuarios.find_one_and_update(
        {"_id": oid(id), "activo": True}, {"$set": {"activo": False}}), "usuario")
    return {"desactivado": id, "nota": "borrado lógico (D-09); el historial se conserva"}
