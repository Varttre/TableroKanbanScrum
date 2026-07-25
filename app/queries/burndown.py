"""Pipeline 2 — Burndown del sprint activo: puntos restantes por día.

Pregunta de negocio: ¿el sprint va camino de cumplirse o nos estamos quedando?

Se calcula SOLO con `eventos` — sin $lookup — porque los eventos de movimiento
denormalizan `puntos` y `sprintId`. Eso además da la semántica correcta:
si una tarjeta se reestima mañana, la curva histórica no se reescribe.

Colección: eventos. Índice de soporte: {meta.sprintId, tipo, timestamp}.
Esperado con la semilla (S4, comprometido=26): lun 0, mar 4, mié 6 quemados
→ acumulado 0/4/10 → restante 26/22/16.
"""


def pipeline_burndown(sprint_id, comprometido):
    return [
        # Etapa 1 — $match: movimientos del sprint que TOCAN la columna Done,
        # en cualquier dirección. Entrar a Done quema puntos; salir de Done
        # (rework: se descubrió que no estaba terminada) los devuelve.
        {"$match": {
            "tipo": "movimiento",
            "meta.sprintId": sprint_id,
            "$or": [{"a": "done"}, {"de": "done"}],
        }},

        # Etapa 2 — $addFields: el signo del movimiento. Los puntos vienen del
        # propio evento (denormalización), capturados en el momento del
        # movimiento — no del estado actual de la tarjeta.
        {"$addFields": {
            "delta": {"$cond": [{"$eq": ["$a", "done"]},
                                "$meta.puntos",
                                {"$multiply": [-1, "$meta.puntos"]}]},
        }},

        # Etapa 3 — $group por día calendario DE LIMA. Los timestamps están en
        # UTC; sin timezone, un cierre del lunes 20:00 Lima (= martes 01:00 UTC)
        # caería en el día equivocado y la curva se correría un día.
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d",
                                      "date": "$timestamp",
                                      "timezone": "America/Lima"}},
            "quemado": {"$sum": "$delta"},
        }},

        # Etapa 4 — $setWindowFields: suma acumulada de lo quemado, ordenando
        # por día. window ["unbounded", "current"] = "desde el inicio hasta hoy".
        {"$setWindowFields": {
            "sortBy": {"_id": 1},
            "output": {
                "acumulado": {
                    "$sum": "$quemado",
                    "window": {"documents": ["unbounded", "current"]},
                },
            },
        }},

        # Etapa 5 — la curva del gráfico: restante = comprometido - acumulado.
        # `comprometido` se calcula aparte (suma de puntos del sprint) y entra
        # al pipeline como constante.
        {"$addFields": {"restante": {"$subtract": [comprometido, "$acumulado"]}}},

        # Etapa 6 — presentación.
        {"$project": {"_id": 0, "dia": "$_id",
                      "quemado": 1, "acumulado": 1, "restante": 1}},
        {"$sort": {"dia": 1}},
    ]
