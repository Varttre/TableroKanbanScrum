"""Pipeline 3 — Cycle time por tipo de tarjeta.

Pregunta de negocio: ¿cuánto tarda el equipo en terminar lo que EMPIEZA, y qué
tipo de trabajo (historia, bug, tarea, spike) fluye peor?

Definición (D-12): desde la PRIMERA entrada a Doing hasta la PRIMERA entrada a
Done — tiempo de trabajo activo, no de espera (eso sería lead time).

Se calcula solo con `eventos`: los timestamps salen de los movimientos y el tipo
de tarjeta viene del evento de creación (meta.tipoTarjeta, catálogo D-13).
Colección: eventos (C16). El filtro por proyecto entra como lista de sprintIds
porque los eventos no llevan proyectoId (se resuelve con una consulta previa
barata a `sprints`).
"""


def pipeline_cycle_time(sprint_ids):
    return [
        # Etapa 1 — $match: movimientos de los sprints del proyecto (traen los
        # timestamps) + TODOS los eventos de creación (traen el tipo de tarjeta,
        # D-13). La creación no se filtra por sprint a propósito: una tarjeta
        # nacida en el backlog tiene creacion.meta.sprintId = null y perdería su
        # tipo al entrar al sprint (flujo D-16). Las tarjetas de otros proyectos
        # que se cuelan aquí se descartan solas en la etapa 3: no tienen
        # entradas a Doing/Done dentro de estos sprints.
        {"$match": {"$or": [
            {"tipo": "movimiento", "meta.sprintId": {"$in": sprint_ids}},
            {"tipo": "creacion"},
        ]}},

        # Etapa 2 — $group por tarjeta: reconstruir su línea de tiempo con
        # acumuladores CONDICIONALES. $min y $max ignoran los null, así que
        # cada acumulador "ve" solo los eventos que le interesan:
        #   - entroDoing: el timestamp más antiguo con destino "doing"
        #   - entroDone:  el timestamp más antiguo con destino "done"
        #   - tipoTarjeta: el valor que trajo el evento de creación
        {"$group": {
            "_id": "$tarjetaId",
            "entroDoing": {"$min": {"$cond": [{"$eq": ["$a", "doing"]},
                                              "$timestamp", None]}},
            "entroDone": {"$min": {"$cond": [{"$eq": ["$a", "done"]},
                                             "$timestamp", None]}},
            "tipoTarjeta": {"$max": {"$cond": [{"$eq": ["$tipo", "creacion"]},
                                               "$meta.tipoTarjeta", None]}},
        }},

        # Etapa 3 — $match: solo tarjetas que COMPLETARON el ciclo. Las que
        # siguen en Doing no tienen cycle time todavía.
        {"$match": {"entroDoing": {"$ne": None}, "entroDone": {"$ne": None}}},

        # Etapa 4 — $dateDiff: horas entre ambas entradas.
        {"$addFields": {
            "horas": {"$dateDiff": {"startDate": "$entroDoing",
                                    "endDate": "$entroDone",
                                    "unit": "hour"}},
        }},

        # Etapa 5 — $group por tipo: promedio, extremos y tamaño de muestra
        # (sin la cantidad, un promedio de 2 tarjetas parecería tan sólido
        # como uno de 20).
        {"$group": {
            "_id": "$tipoTarjeta",
            "promedioHoras": {"$avg": "$horas"},
            "minimoHoras": {"$min": "$horas"},
            "maximoHoras": {"$max": "$horas"},
            "tarjetas": {"$sum": 1},
        }},

        # Etapa 6 — presentación: días además de horas, para leerlo de un vistazo.
        {"$project": {
            "_id": 0,
            "tipo": "$_id",
            "promedioHoras": {"$round": ["$promedioHoras", 1]},
            "promedioDias": {"$round": [{"$divide": ["$promedioHoras", 24]}, 1]},
            "minimoHoras": 1,
            "maximoHoras": 1,
            "tarjetas": 1,
        }},
        {"$sort": {"promedioHoras": -1}},
    ]
