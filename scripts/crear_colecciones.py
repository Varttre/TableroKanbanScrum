"""Crea las 6 colecciones con su validador $jsonSchema. Idempotente.

Uso:  python -m scripts.crear_colecciones

La validación a nivel de colección es la segunda línea de defensa (la primera es
Pydantic en la API): protege la BD de escrituras hechas por fuera de la app, por
ejemplo desde mongosh o Compass durante la demo.

Nota: $jsonSchema usa `bsonType` (tipos BSON: objectId, date, double...) en lugar
del `type` de JSON Schema estándar, porque valida documentos BSON, no JSON.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import db  # noqa: E402

# --- fragmentos reutilizables -------------------------------------------------

# Escala Fibonacci (D-06). null = sin estimar o tipo "nodo" (los nodos no puntúan).
PUNTOS_FIBONACCI = {"enum": [1, 2, 3, 5, 8, 13, 21, None]}

OBJECT_ID = {"bsonType": "objectId"}
OBJECT_ID_O_NULL = {"bsonType": ["objectId", "null"]}
TEXTO = {"bsonType": "string"}
FECHA = {"bsonType": "date"}
FECHA_O_NULL = {"bsonType": ["date", "null"]}
BOOLEANO = {"bsonType": "bool"}

# --- los 6 esquemas -----------------------------------------------------------

ESQUEMAS = {
    "usuarios": {
        "bsonType": "object",
        "required": ["nombre", "email", "rol", "activo"],
        "properties": {
            "nombre": TEXTO,
            "email": TEXTO,
            "rol": {"enum": ["moderador", "desarrollador"]},
            "activo": BOOLEANO,
        },
    },
    "proyectos": {
        "bsonType": "object",
        "required": ["nombre", "cliente", "estado", "columnas", "miembros", "activo"],
        "properties": {
            "nombre": TEXTO,
            "cliente": TEXTO,
            "estado": {"enum": ["activo", "pausado", "cerrado"]},
            "columnas": {
                "bsonType": "array",
                "minItems": 1,
                "items": {
                    "bsonType": "object",
                    "required": ["clave", "nombre", "orden", "limiteWip", "wip"],
                    "properties": {
                        "clave": TEXTO,
                        "nombre": TEXTO,
                        "orden": {"bsonType": "int"},
                        # null = sin límite; el contador wip nunca baja de 0 (D-11)
                        "limiteWip": {"bsonType": ["int", "null"], "minimum": 1},
                        "wip": {"bsonType": "int", "minimum": 0},
                    },
                },
            },
            "miembros": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["usuarioId", "nombre"],
                    "properties": {"usuarioId": OBJECT_ID, "nombre": TEXTO},
                },
            },
            "activo": BOOLEANO,
        },
    },
    "sprints": {
        "bsonType": "object",
        "required": ["proyectoId", "nombre", "fechaInicio", "fechaFin", "estado"],
        "properties": {
            "proyectoId": OBJECT_ID,
            "nombre": TEXTO,
            "objetivo": TEXTO,
            "fechaInicio": FECHA,
            "fechaFin": FECHA,
            "estado": {"enum": ["planificacion", "activo", "cerrado"]},
        },
    },
    "tarjetas": {
        "bsonType": "object",
        "required": [
            "titulo", "tipo", "proyectoId", "proyectoNombre", "sprintId",
            "asignadoA", "asignadoNombre", "columna", "orden", "puntos",
            "bloqueado", "padreId", "ancestros", "profundidad",
            "activo", "createdAt", "updatedAt", "doneAt",
        ],
        "properties": {
            "titulo": TEXTO,
            "descripcion": TEXTO,
            "tipo": {"enum": ["historia", "bug", "tarea", "spike", "nodo"]},
            "proyectoId": OBJECT_ID,
            "proyectoNombre": TEXTO,          # denormalizado (C1: tablero sin $lookup)
            "sprintId": OBJECT_ID_O_NULL,     # null = backlog
            "asignadoA": OBJECT_ID_O_NULL,
            "asignadoNombre": {"bsonType": ["string", "null"]},
            "columna": TEXTO,
            "orden": {"bsonType": ["double", "int"]},  # fraccionario (D-05)
            "puntos": PUNTOS_FIBONACCI,
            "diaPrevisto": FECHA_O_NULL,
            "bloqueado": {
                "bsonType": "object",
                "required": ["estado", "motivo", "desde"],
                "properties": {
                    "estado": BOOLEANO,
                    "motivo": {"bsonType": ["string", "null"]},
                    "desde": FECHA_O_NULL,
                },
            },
            "padreId": OBJECT_ID_O_NULL,      # null = raíz
            "ancestros": {"bsonType": "array", "items": OBJECT_ID},  # mat. path (D-03)
            "profundidad": {"bsonType": "int", "minimum": 0},
            "liderId": OBJECT_ID_O_NULL,      # solo nodos (D-07)
            "etiquetas": {"bsonType": "array", "items": TEXTO},
            "checklist": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["texto", "hecho"],
                    "properties": {"texto": TEXTO, "hecho": BOOLEANO},
                },
            },
            "comentarios": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["_id", "usuarioId", "nombre", "texto", "fecha"],
                    "properties": {
                        "_id": OBJECT_ID, "usuarioId": OBJECT_ID,
                        "nombre": TEXTO, "texto": TEXTO, "fecha": FECHA,
                    },
                },
            },
            "activo": BOOLEANO,
            "createdAt": FECHA,
            "updatedAt": FECHA,
            "doneAt": FECHA_O_NULL,           # primera entrada a done (velocity, C15)
        },
    },
    "eventos": {
        "bsonType": "object",
        "required": ["tarjetaId", "tipo", "de", "a", "usuarioId", "timestamp", "meta"],
        "properties": {
            "tarjetaId": OBJECT_ID,
            # Catálogo congelado (D-13). Añadir un tipo nuevo exige pasar por aquí.
            "tipo": {"enum": [
                "creacion", "movimiento", "reasignacion", "cambio_sprint",
                "bloqueo", "desbloqueo", "edicion", "archivado",
            ]},
            "de": {"bsonType": ["string", "objectId", "null"]},  # semántica según tipo
            "a": {"bsonType": ["string", "objectId", "null"]},
            "usuarioId": OBJECT_ID,
            "timestamp": FECHA,
            "meta": {"bsonType": "object"},   # payload variable por tipo (D-13)
        },
    },
    "dailies": {
        "bsonType": "object",
        "required": ["sprintId", "fecha", "participaciones"],
        "properties": {
            "sprintId": OBJECT_ID,
            "fecha": FECHA,
            "participaciones": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["usuarioId", "nombre", "hice", "hare", "bloqueo"],
                    "properties": {
                        "usuarioId": OBJECT_ID,
                        "nombre": TEXTO,
                        "hice": TEXTO,
                        "hare": TEXTO,
                        "bloqueo": {"bsonType": ["string", "null"]},
                    },
                },
            },
        },
    },
}


def crear_o_actualizar(nombre: str, esquema: dict) -> str:
    """Crea la colección con validador, o actualiza el validador si ya existe."""
    validador = {"$jsonSchema": esquema}
    if nombre in db.list_collection_names():
        # collMod reemplaza el validador sin tocar los datos existentes
        db.command("collMod", nombre, validator=validador, validationLevel="strict")
        return "actualizada"
    db.create_collection(nombre, validator=validador, validationLevel="strict")
    return "creada"


if __name__ == "__main__":
    for nombre, esquema in ESQUEMAS.items():
        resultado = crear_o_actualizar(nombre, esquema)
        print(f"  {nombre:<12} {resultado}")
    print("Listo: 6 colecciones con $jsonSchema en", db.name)
