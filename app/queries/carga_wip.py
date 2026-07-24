"""Pipeline 4 — Carga y WIP por integrante.

Pregunta de negocio: ¿quién está sobrecargado AHORA? Es la consulta que cruza
proyectos (C9): una persona puede estar tranquila en un proyecto y ahogada
sumando los dos. Por eso el filtro por proyecto es OPCIONAL: sin él se ve la
carga real de cada persona en toda la organización.

Colecciones: tarjetas + $lookup a usuarios. Índice de soporte: {asignadoA, columna}.
"""


def pipeline_carga(proyecto_id=None):
    # Filtro base: trabajo VIVO y PENDIENTE. Se excluyen done (ya no es carga),
    # backlog (no está comprometido), los nodos padre (no puntúan, D-06) y lo
    # no asignado (no carga a nadie).
    filtro = {
        "activo": True,
        "asignadoA": {"$ne": None},
        "tipo": {"$ne": "nodo"},
        "columna": {"$in": ["todo", "doing"]},
    }
    if proyecto_id is not None:
        filtro["proyectoId"] = proyecto_id

    return [
        # Etapa 1 — $match: el filtro de arriba.
        {"$match": filtro},

        # Etapa 2 — $group por persona, con acumuladores condicionales:
        #   - wip: cuántas tarjetas tiene EN CURSO (Doing) — lo que limita D-11
        #   - bloqueadas: cuántas de sus tarjetas están frenadas
        #   - proyectos: $addToSet junta los nombres SIN repetir — aquí se ve
        #     quién está repartido entre varios proyectos (posible con el
        #     nombre denormalizado, sin join a proyectos)
        {"$group": {
            "_id": "$asignadoA",
            "tarjetasPendientes": {"$sum": 1},
            "puntosPendientes": {"$sum": "$puntos"},
            "wip": {"$sum": {"$cond": [{"$eq": ["$columna", "doing"]}, 1, 0]}},
            "bloqueadas": {"$sum": {"$cond": ["$bloqueado.estado", 1, 0]}},
            "proyectos": {"$addToSet": "$proyectoNombre"},
        }},

        # Etapa 3 — $lookup a usuarios: nombre y rol. Este join sí es necesario
        # (no denormalizamos el rol en las tarjetas) y es barato: ocurre después
        # de agrupar, una vez por persona, no por tarjeta.
        {"$lookup": {
            "from": "usuarios",
            "localField": "_id",
            "foreignField": "_id",
            "as": "usuario",
        }},
        {"$unwind": "$usuario"},

        # Etapa 4 — presentación, ordenada por quién tiene más entre manos.
        {"$project": {
            "_id": 0,
            "usuarioId": "$_id",
            "nombre": "$usuario.nombre",
            "rol": "$usuario.rol",
            "tarjetasPendientes": 1,
            "puntosPendientes": 1,
            "wip": 1,
            "bloqueadas": 1,
            "proyectos": 1,
        }},
        {"$sort": {"wip": -1, "puntosPendientes": -1}},
    ]
