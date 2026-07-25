"""Verificación de los 6 pipelines contra los valores conocidos de la semilla.

Ejecutar desde la raíz del repo:  python scripts/verificar_pipelines.py
Requiere la BD sembrada (scripts/semilla.py). Los asserts del pipeline 6
dependen de la fecha (la semilla fija "hoy" = jueves 2026-07-23): si se corre
otro día, ese bloque solo avisa en vez de fallar.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import db
from app.queries.arbol import pipeline_arbol
from app.queries.bloqueadas import pipeline_bloqueadas
from app.queries.burndown import pipeline_burndown
from app.queries.carga_wip import pipeline_carga
from app.queries.cycle_time import pipeline_cycle_time
from app.queries.velocity import pipeline_velocity

OK = 0


def check(cond, msg):
    global OK
    assert cond, f"FALLO: {msg}"
    OK += 1
    print(f"  ok  {msg}")


qhatu = db.proyectos.find_one({"nombre": "Qhatu Delivery"})
s4 = db.sprints.find_one({"proyectoId": qhatu["_id"], "estado": "activo"})

# --- 1. Velocity ------------------------------------------------------------
print("1. velocity")
v = list(db.tarjetas.aggregate(pipeline_velocity(qhatu["_id"])))
check([r["puntos"] for r in v] == [20, 24, 23], "velocity por sprint = 20, 24, 23")
check([r["mediaMovil"] for r in v] == [20, 22, 22.3], "media móvil = 20, 22, 22.3")
check(all(r["sprint"].startswith("Sprint") for r in v), "cada fila trae el nombre del sprint")

# --- 2. Burndown ------------------------------------------------------------
print("2. burndown")
comprometido = list(db.tarjetas.aggregate([
    {"$match": {"sprintId": s4["_id"], "activo": True}},
    {"$group": {"_id": None, "puntos": {"$sum": "$puntos"}}},
]))[0]["puntos"]
check(comprometido == 26, "comprometido del sprint activo = 26")
b = list(db.eventos.aggregate(pipeline_burndown(s4["_id"], comprometido)))
check([d["quemado"] for d in b] == [4, 6], "quemado por día = 4 (mar), 6 (mié)")
check([d["restante"] for d in b] == [22, 16], "restante = 22, 16 (10 de 26 hechos)")

# --- 3. Cycle time ----------------------------------------------------------
print("3. cycle time")
sprint_ids = [s["_id"] for s in db.sprints.find({"proyectoId": qhatu["_id"]}, {"_id": 1})]
ct = {r["tipo"]: r for r in db.eventos.aggregate(pipeline_cycle_time(sprint_ids))}
check(sum(r["tarjetas"] for r in ct.values()) == 20, "20 tarjetas con ciclo completo")
check({t: ct[t]["tarjetas"] for t in ct} ==
      {"historia": 9, "bug": 4, "tarea": 4, "spike": 3}, "muestra por tipo = 9/4/4/3")
check(all(r["promedioHoras"] > 0 for r in ct.values()), "todos los promedios > 0")
check(ct["spike"]["promedioHoras"] < ct["historia"]["promedioHoras"],
      "los spikes (timebox) fluyen más rápido que las historias")

# --- 4. Carga y WIP ---------------------------------------------------------
print("4. carga y wip")
carga = {r["nombre"]: r for r in db.tarjetas.aggregate(pipeline_carga())}
alejandro = next(v for k, v in carga.items() if "Alejandro" in k)
check(alejandro["bloqueadas"] == 1, "Alejandro tiene 1 tarjeta bloqueada (webhook)")
diego = next(v for k, v in carga.items() if "Diego" in k)
check(diego["wip"] == 1 and diego["puntosPendientes"] == 8,
      "Diego: wip=1 (cobro), 8 pts pendientes (los nodos no cuentan)")
check(not any("Valeria" in k for k in carga), "Valeria sin pendientes (su épica es nodo)")
check(any(len(r["proyectos"]) >= 1 for r in carga.values()), "campo multi-proyecto presente")

# --- 5. Árbol ($graphLookup) ------------------------------------------------
print("5. arbol")
epica = db.tarjetas.find_one({"titulo": "Módulo de pagos en línea"})
a = list(db.tarjetas.aggregate(pipeline_arbol(epica["_id"])))[0]
check(len(a["descendientes"]) == 6, "la épica tiene 6 descendientes (2 niveles)")
check(a["puntosTotales"] == 20 and a["puntosHechos"] == 7, "progreso 7/20 puntos")
check(a["progresoPct"] == 35, "progreso = 35 %")
check(max(d["nivel"] for d in a["descendientes"]) == 1,
      "profundidad máxima relativa = 1 (nietos: depthField arranca en 0)")

# --- 6. Bloqueadas / estancadas ----------------------------------------------
print("6. bloqueadas y estancadas")
bl = list(db.tarjetas.aggregate(pipeline_bloqueadas(qhatu["_id"], 2)))
if date.today() == date(2026, 7, 23):
    check(len(bl) == 2, "2 tarjetas en el radar")
    check(any(r["bloqueado"]["estado"] and "Webhook" in r["titulo"] for r in bl),
          "el webhook figura como bloqueada")
    check(any(r["estancada"] and "CDN" in r["titulo"] for r in bl),
          "migrar imágenes figura como estancada (Doing desde el lunes)")
else:
    print(f"  (hoy no es 2026-07-23: asserts de fecha omitidos; devuelve {len(bl)} filas)")

print(f"\n{OK} verificaciones pasaron. Pipelines consistentes con la semilla.")
