"""Pipeline 6 — Tarjetas bloqueadas o estancadas: el radar de la daily.

Pregunta de negocio: ¿qué está frenado y desde cuándo? Dos casos distintos:
  - BLOQUEADA: alguien lo declaró (bloqueado.estado = true, con motivo).
  - ESTANCADA: nadie declaró nada, pero lleva en Doing más de N días sin
    actividad — el problema silencioso que la daily debe destapar.

Colección: tarjetas. Índices de soporte: {proyectoId, columna, updatedAt}
y el parcial sobre {bloqueado.estado}.
Esperado con la semilla (Qhatu, umbral 2 días): 1 bloqueada (webhook, sin
credenciales del cliente) y 1 estancada (migrar imágenes, en Doing desde el lunes).
"""


def pipeline_bloqueadas(proyecto_id, umbral_dias=2):
    return [
        # Etapa 1 — $match: tarjetas vivas del proyecto que están EN el flujo.
        # Done ya terminó y el backlog aún no empieza: ninguna puede estar
        # frenada. Los nodos padre se excluyen: son agrupadores — su "actividad"
        # es la de sus hijos, igual que no puntúan ni cuentan WIP.
        {"$match": {
            "proyectoId": proyecto_id,
            "activo": True,
            "columna": {"$in": ["todo", "doing"]},
            "tipo": {"$ne": "nodo"},
        }},

        # Etapa 2 — $dateDiff: días calendario sin actividad. updatedAt se
        # actualiza con CADA evento de la tarjeta, así que es un proxy
        # honesto de "última vez que alguien la tocó". $$NOW es la hora del
        # servidor; el timezone evita que un límite de día en UTC (19:00 en
        # Lima) parta mal el conteo.
        {"$addFields": {
            "diasSinActividad": {"$dateDiff": {
                "startDate": "$updatedAt",
                "endDate": "$$NOW",
                "unit": "day",
                "timezone": "America/Lima",
            }},
        }},

        # Etapa 3 — clasificar. Estancada = en Doing, sin bloqueo declarado y
        # quieta más días que el umbral. Se separa del bloqueo porque piden
        # acciones distintas: el bloqueo se persigue afuera (cliente, proveedor),
        # el estancamiento se pregunta en la daily.
        {"$addFields": {
            "estancada": {"$and": [
                {"$eq": ["$columna", "doing"]},
                {"$eq": ["$bloqueado.estado", False]},
                {"$gt": ["$diasSinActividad", umbral_dias]},
            ]},
        }},

        # Etapa 4 — $match: solo lo que requiere atención.
        {"$match": {"$or": [{"bloqueado.estado": True}, {"estancada": True}]}},

        # Etapa 5 — presentación, lo más quieto primero.
        {"$project": {
            "_id": 0,
            "tarjetaId": "$_id",
            "titulo": 1, "tipo": 1, "puntos": 1, "columna": 1,
            "asignadoNombre": 1,
            "bloqueado": 1,
            "estancada": 1,
            "diasSinActividad": 1,
        }},
        {"$sort": {"diasSinActividad": -1}},
    ]
