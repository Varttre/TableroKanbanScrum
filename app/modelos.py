"""Modelos Pydantic: validación de entrada de la API (primera línea de defensa).

La segunda línea es el $jsonSchema de cada colección (scripts/crear_colecciones.py):
protege la BD de escrituras hechas por fuera de la app.

Los ids viajan como str en el JSON y se convierten a ObjectId en los routers.
Como no hay autenticación (D-08), cada mutación de tarjeta recibe `usuarioId`:
el usuario elegido en el selector de cabecera, que firma el evento (D-04).
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Rol = Literal["moderador", "desarrollador"]
TipoTarjeta = Literal["historia", "bug", "tarea", "spike", "nodo"]
EstadoProyecto = Literal["activo", "pausado", "cerrado"]
EstadoSprint = Literal["planificacion", "activo", "cerrado"]
Puntos = Literal[1, 2, 3, 5, 8, 13, 21]  # Fibonacci (D-06)


# --- usuarios ---------------------------------------------------------------

class UsuarioCrear(BaseModel):
    nombre: str = Field(min_length=1)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    rol: Rol
    usuarioId: str                    # actor: debe ser moderador (D-17)


class UsuarioActualizar(BaseModel):
    nombre: Optional[str] = None
    email: Optional[str] = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    rol: Optional[Rol] = None
    usuarioId: str                    # actor: debe ser moderador (D-17)


# --- proyectos --------------------------------------------------------------

class ProyectoCrear(BaseModel):
    nombre: str = Field(min_length=1)
    cliente: str = Field(min_length=1)
    miembros: list[str] = []          # ids de usuarios; el nombre se denormaliza al crear
    usuarioId: str                    # actor: debe ser moderador (D-17)


class ProyectoActualizar(BaseModel):
    nombre: Optional[str] = None
    cliente: Optional[str] = None
    estado: Optional[EstadoProyecto] = None
    miembros: Optional[list[str]] = None
    # {"doing": 4} cambia el límite WIP de una columna; None = sin límite
    limitesWip: Optional[dict[str, Optional[int]]] = None
    usuarioId: str                    # actor: debe ser moderador (D-17)


# --- sprints ----------------------------------------------------------------

class SprintCrear(BaseModel):
    proyectoId: str
    nombre: str = Field(min_length=1)
    objetivo: str = ""
    fechaInicio: datetime
    fechaFin: datetime
    estado: EstadoSprint = "planificacion"
    usuarioId: str                    # actor: debe ser moderador (D-17)


class SprintActualizar(BaseModel):
    nombre: Optional[str] = None
    objetivo: Optional[str] = None
    fechaInicio: Optional[datetime] = None
    fechaFin: Optional[datetime] = None
    estado: Optional[EstadoSprint] = None
    usuarioId: str                    # actor: debe ser moderador (D-17)


# --- tarjetas ---------------------------------------------------------------

class ChecklistItem(BaseModel):
    texto: str
    hecho: bool = False


class TarjetaCrear(BaseModel):
    titulo: str = Field(min_length=1)
    descripcion: str = ""
    tipo: TipoTarjeta = "historia"
    proyectoId: str
    sprintId: Optional[str] = None    # None = nace en el backlog
    asignadoA: Optional[str] = None
    puntos: Optional[Puntos] = None
    padreId: Optional[str] = None     # el servicio calcula ancestros y profundidad
    liderId: Optional[str] = None     # solo tipo "nodo" (D-07)
    etiquetas: list[str] = []
    checklist: list[ChecklistItem] = []
    usuarioId: str                    # actor: firma el evento de creación


class TarjetaActualizar(BaseModel):
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    tipo: Optional[TipoTarjeta] = None
    puntos: Optional[Puntos] = None
    etiquetas: Optional[list[str]] = None
    diaPrevisto: Optional[datetime] = None
    checklist: Optional[list[ChecklistItem]] = None
    sprintId: Optional[str] = None    # "backlog" = sacar del sprint (volver al backlog)
    asignadoA: Optional[str] = None
    liderId: Optional[str] = None
    usuarioId: str


class MoverTarjeta(BaseModel):
    """Movimiento en el tablero 2D: columna destino y, opcionalmente, otra fila.

    El orden se calcula con los vecinos (D-05): el frontend manda entre qué dos
    tarjetas cayó la que se arrastra; el backend pone el punto medio.
    """
    columna: str
    asignadoA: Optional[str] = None       # cambiar de fila (reasigna)
    vecinoAnteriorId: Optional[str] = None
    vecinoSiguienteId: Optional[str] = None
    usuarioId: str


class BloquearTarjeta(BaseModel):
    motivo: str = Field(min_length=1)
    usuarioId: str


class DesbloquearTarjeta(BaseModel):
    usuarioId: str


class ComentarioCrear(BaseModel):
    texto: str = Field(min_length=1)
    usuarioId: str


# --- dailies ----------------------------------------------------------------

class Participacion(BaseModel):
    usuarioId: str
    hice: str
    hare: str
    bloqueo: Optional[str] = None


class DailyCrear(BaseModel):
    sprintId: str
    fecha: datetime
    participaciones: list[Participacion] = []
    usuarioId: str                    # quien abre la ceremonia: miembro (D-18)


class ParticipacionUpsert(BaseModel):
    """Agrega o reemplaza la participación de un usuario en la daily."""
    participacion: Participacion
