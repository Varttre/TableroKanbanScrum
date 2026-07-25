"""Índices del proyecto — salen de la matriz de patrones de acceso, no se improvisan.

create_index es idempotente: si el índice ya existe con la misma definición,
no hace nada — el script puede correrse las veces que haga falta.

Ejecutar desde la raíz:  python scripts/crear_indices.py
"""

import sys
from pathlib import Path

from pymongo import ASCENDING as ASC
from pymongo import DESCENDING as DESC

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import db 


def crear():
    # --- tarjetas: la colección más consultada ---------------------------------
    # Render del tablero y backlog: tarjetas raíz por (proyecto, sprint).
    db.tarjetas.create_index(
        [("proyectoId", ASC), ("sprintId", ASC), ("padreId", ASC)],
        name="tablero_c1")
    # Hijos directos de un nodo; además es el campo conector que el
    # $graphLookup recorre en cada salto.
    db.tarjetas.create_index([("padreId", ASC)], name="hijos_c6")
    # Subárbol completo por materialized path y permiso de líder
    # Multikey: Mongo indexa cada elemento del array `ancestros`.
    db.tarjetas.create_index([("ancestros", ASC)], name="subarbol_c7")
    # Carga por integrante entre proyectos.
    db.tarjetas.create_index([("asignadoA", ASC), ("columna", ASC)], name="carga_c9")
    # Radar de la daily: por proyecto y columna, ordenando por quietud. Índice PARCIAL
    # adicional para "las bloqueadas" a secas: solo indexa
    # los documentos con bloqueado.estado = true (baratísimo de mantener).
    db.tarjetas.create_index(
        [("proyectoId", ASC), ("columna", ASC), ("updatedAt", ASC)],
        name="radar_c12")
    db.tarjetas.create_index(
        [("bloqueado.estado", ASC)], name="bloqueadas_c12",
        partialFilterExpression={"bloqueado.estado": True})
    # velocity: tarjetas en done por sprint.
    db.tarjetas.create_index([("sprintId", ASC), ("columna", ASC)], name="velocity_c15")

    # --- eventos: solo lecturas analíticas --------------------------------
    # Burndown . También cubre el cycle time: su $match
    # filtra por meta.sprintId y tipo, los dos primeros campos de este índice —
    # por eso no necesita índice propio.
    db.eventos.create_index(
        [("meta.sprintId", ASC), ("tipo", ASC), ("timestamp", ASC)],
        name="burndown_c13")
    # Historial de una tarjeta (auditoría, modal de la UI).
    db.eventos.create_index([("tarjetaId", ASC), ("timestamp", DESC)], name="historial_c14")

    # --- sprints / dailies --------------------------------------------------------
    # sprint activo del proyecto (se consulta en cada movimiento).
    db.sprints.create_index([("proyectoId", ASC), ("estado", ASC)], name="activo_c10")
    # Una daily por (sprint, día). ÚNICO: la regla de negocio deja de ser
    # una validación de la app y pasa a ser una garantía de la base de datos.
    db.dailies.create_index([("sprintId", ASC), ("fecha", ASC)],
                            name="daily_unica_c11", unique=True)

    # usuarios y proyectos: colecciones diminutas que se leen por _id;
    # un índice secundario costaría mantenimiento sin ahorrar nada.


if __name__ == "__main__":
    crear()
    for c in ("tarjetas", "eventos", "sprints", "dailies"):
        nombres = [i["name"] for i in db[c].list_indexes() if i["name"] != "_id_"]
        print(f"{c:<9} {len(nombres)} índices: {', '.join(nombres)}")
