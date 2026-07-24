"""Pipeline 1 — Velocity por sprint, con media móvil de 3 sprints.

Pregunta de negocio: ¿cuántos puntos completa el equipo por sprint y cuál es su
tendencia? Es LA herramienta de capacidad del moderador (D-06): la conversión
puntos→tiempo no se fija a priori, se mide empíricamente aquí.

Colecciones: tarjetas + $lookup a sprints (C15). Índice de soporte: {sprintId, columna}.
Valores esperados con la semilla (Qhatu): S1=20, S2=24, S3=23 → medias 20, 22, 22.3.
"""


def pipeline_velocity(proyecto_id):
    return [
        # Etapa 1 — $match: solo tarjetas TERMINADAS del proyecto, vivas y con
        # sprint. La velocity se calcula sobre el estado actual de las tarjetas
        # (no sobre eventos) porque una tarjeta arrastrada de sprint cuenta en
        # el sprint donde SE TERMINÓ: su sprintId ya fue actualizado al moverla.
        {"$match": {
            "proyectoId": proyecto_id,
            "columna": "done",
            "activo": True,
            "sprintId": {"$ne": None},
        }},

        # Etapa 2 — $group: un documento por sprint con la suma de puntos.
        # Los nodos padre tienen puntos: null y $sum los ignora — no puntúan
        # dos veces (sus hijos ya suman).
        {"$group": {
            "_id": "$sprintId",
            "puntos": {"$sum": "$puntos"},
            "tarjetasTerminadas": {"$sum": 1},
        }},

        # Etapa 3 — $lookup: traer el documento del sprint (nombre, fechas,
        # estado). Es el único join del pipeline y ocurre DESPUÉS de agrupar:
        # se hace una vez por sprint (4 docs), no una vez por tarjeta.
        {"$lookup": {
            "from": "sprints",
            "localField": "_id",
            "foreignField": "_id",
            "as": "sprint",
        }},
        {"$unwind": "$sprint"},

        # Etapa 4 — $match: la velocity solo tiene sentido sobre sprints
        # CERRADOS. El sprint activo se excluye: sus puntos parciales
        # arrastrarían la media hacia abajo sin significar nada.
        {"$match": {"sprint.estado": "cerrado"}},

        # Etapa 5 — $setWindowFields: media móvil de los últimos 3 sprints
        # (el actual y los 2 anteriores: window [-2, 0]). Es el promedio que
        # el moderador usa para comprometer capacidad del siguiente sprint.
        {"$setWindowFields": {
            "sortBy": {"sprint.fechaInicio": 1},
            "output": {
                "mediaMovil": {
                    "$avg": "$puntos",
                    "window": {"documents": [-2, 0]},
                },
            },
        }},

        # Etapa 6 — presentación: aplanar y redondear.
        {"$project": {
            "_id": 0,
            "sprintId": "$_id",
            "sprint": "$sprint.nombre",
            "fechaInicio": "$sprint.fechaInicio",
            "puntos": 1,
            "tarjetasTerminadas": 1,
            "mediaMovil": {"$round": ["$mediaMovil", 1]},
        }},
        {"$sort": {"fechaInicio": 1}},
    ]
