"""Métricas ágiles: un endpoint GET por pipeline de agregación.

Los pipelines viven en app/queries/ (uno por archivo, comentados etapa por
etapa: son material del informe). Este router solo resuelve parámetros,
ejecuta y serializa.
"""

from fastapi import APIRouter, HTTPException

from app.db import db
from app.queries.arbol import pipeline_arbol
from app.queries.bloqueadas import pipeline_bloqueadas
from app.queries.burndown import pipeline_burndown
from app.queries.carga_wip import pipeline_carga
from app.queries.cycle_time import pipeline_cycle_time
from app.queries.velocity import pipeline_velocity
from app.utiles import a_json, oid

router = APIRouter(prefix="/metricas", tags=["metricas"])


@router.get("/velocity")
def velocity(proyectoId: str):
    """Pipeline 1: puntos completados por sprint cerrado + media móvil de 3."""
    return a_json(list(db.tarjetas.aggregate(pipeline_velocity(oid(proyectoId)))))


@router.get("/burndown")
def burndown(proyectoId: str):
    """Pipeline 2: curva de puntos restantes por día del sprint activo."""
    sprint = db.sprints.find_one({"proyectoId": oid(proyectoId), "estado": "activo"})
    if sprint is None:
        raise HTTPException(status_code=404, detail="El proyecto no tiene sprint activo")

    # Comprometido = suma de puntos de las tarjetas vivas del sprint. Se calcula
    # aparte y entra al pipeline como constante ($sum ignora los null de los nodos).
    total = list(db.tarjetas.aggregate([
        {"$match": {"sprintId": sprint["_id"], "activo": True}},
        {"$group": {"_id": None, "puntos": {"$sum": "$puntos"}}},
    ]))
    comprometido = total[0]["puntos"] if total else 0

    dias = list(db.eventos.aggregate(pipeline_burndown(sprint["_id"], comprometido)))
    return a_json({"sprint": sprint["nombre"], "sprintId": sprint["_id"],
                   "fechaInicio": sprint["fechaInicio"], "fechaFin": sprint["fechaFin"],
                   "comprometido": comprometido, "dias": dias})


@router.get("/cycle-time")
def cycle_time(proyectoId: str):
    """Pipeline 3: horas de Doing a Done, agrupadas por tipo de tarjeta."""
    # Los eventos no llevan proyectoId: el proyecto se traduce a su lista de
    # sprints (consulta barata e indexada) y el pipeline filtra por ella.
    sprint_ids = [s["_id"] for s in
                  db.sprints.find({"proyectoId": oid(proyectoId)}, {"_id": 1})]
    if not sprint_ids:
        raise HTTPException(status_code=404, detail="El proyecto no tiene sprints")
    return a_json(list(db.eventos.aggregate(pipeline_cycle_time(sprint_ids))))


@router.get("/carga")
def carga(proyectoId: str | None = None):
    """Pipeline 4: carga y WIP por integrante. Sin proyectoId cruza TODOS los
    proyectos — la vista real de quién está sobrecargado en la organización."""
    pid = oid(proyectoId) if proyectoId else None
    return a_json(list(db.tarjetas.aggregate(pipeline_carga(pid))))


@router.get("/arbol/{tarjetaId}")
def arbol(tarjetaId: str):
    """Pipeline 5: subárbol completo de un nodo con progreso agregado."""
    resultado = list(db.tarjetas.aggregate(pipeline_arbol(oid(tarjetaId))))
    if not resultado:
        raise HTTPException(status_code=404, detail="No existe la tarjeta")
    return a_json(resultado[0])


@router.get("/bloqueadas")
def bloqueadas(proyectoId: str, umbralDias: int = 2):
    """Pipeline 6: tarjetas bloqueadas o estancadas (radar de la daily)."""
    return a_json(list(db.tarjetas.aggregate(
        pipeline_bloqueadas(oid(proyectoId), umbralDias))))
