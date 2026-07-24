"""Evidencia de índices: explain("executionStats") de 3 consultas representativas.

Se corre DOS veces: antes de crear los índices (todo COLLSCAN) y después
(IXSCAN). Con una semilla pequeña los milisegundos no cuentan la historia;
lo que importa es `totalDocsExamined` frente a documentos devueltos: el
COLLSCAN examina la colección entera, el IXSCAN solo lo que responde.

Ejecutar desde la raíz:  python scripts/explain_indices.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import db  # noqa: E402


def explicar(nombre, coleccion, filtro):
    plan = db.command("explain", {"find": coleccion, "filter": filtro},
                      verbosity="executionStats")
    stats = plan["executionStats"]
    ganador = plan["queryPlanner"]["winningPlan"]
    # la etapa útil está anidada (FETCH → IXSCAN o directamente COLLSCAN)
    etapa = ganador
    while "inputStage" in etapa:
        etapa = etapa["inputStage"]
    indice = etapa.get("indexName", "—")
    print(f"{nombre}")
    print(f"  etapa: {etapa['stage']:<8} índice: {indice}")
    print(f"  documentos examinados: {stats['totalDocsExamined']:>3}"
          f"  · devueltos: {stats['nReturned']}"
          f"  · claves examinadas: {stats['totalKeysExamined']}\n")


qhatu = db.proyectos.find_one({"nombre": "Qhatu Delivery"})
s4 = db.sprints.find_one({"proyectoId": qhatu["_id"], "estado": "activo"})
epica = db.tarjetas.find_one({"titulo": "Módulo de pagos en línea"})

print(f"--- explain sobre {db.tarjetas.count_documents({})} tarjetas, "
      f"{db.eventos.count_documents({})} eventos ---\n")

# C1 — el render del tablero: la consulta más frecuente del sistema
explicar("C1 · tablero (proyecto + sprint activo, raíces)", "tarjetas",
         {"proyectoId": qhatu["_id"], "sprintId": s4["_id"], "padreId": None})

# C7 — subárbol por materialized path (D-03)
explicar("C7 · subárbol de la épica (ancestros multikey)", "tarjetas",
         {"ancestros": epica["_id"]})

# C13 — los eventos que alimentan el burndown (pipeline 2)
explicar("C13 · eventos de movimiento del sprint activo", "eventos",
         {"meta.sprintId": s4["_id"], "tipo": "movimiento"})
