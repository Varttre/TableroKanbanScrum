"""Pipeline 5 — Subárbol de un nodo con progreso agregado ($graphLookup).

Pregunta de negocio: ¿cómo va la épica? Un nodo padre no puntúa (D-06): su
avance ES el avance agregado de sus descendientes, a cualquier profundidad.

Es el complemento del materialized path (D-03): `ancestros` responde "dame el
subárbol" plano con un find indexado; $graphLookup RECORRE el grafo desde la
raíz y anota a qué nivel está cada descendiente (depthField), que es lo que la
UI necesita para dibujar el árbol.

Colección: tarjetas (C17). Índice de soporte: {padreId} — el campo conector.
Esperado con la semilla (épica "Módulo de pagos"): 6 descendientes, 20 puntos
totales, 7 hechos → 35 %.
"""


def pipeline_arbol(tarjeta_id):
    return [
        # Etapa 1 — $match: la raíz del subárbol (la épica que se consulta).
        {"$match": {"_id": tarjeta_id}},

        # Etapa 2 — $graphLookup: búsqueda RECURSIVA dentro de la misma
        # colección. Arranca con el _id de la raíz y sigue el borde
        # _id → padreId tantas veces como haga falta:
        #   "busca tarjetas cuyo padreId sea alguno de los _id ya encontrados,
        #    y repite con lo que encuentres"
        # depthField anota la profundidad relativa (0 = hijo directo).
        # Las archivadas no cuentan para el progreso (restrictSearchWithMatch).
        {"$graphLookup": {
            "from": "tarjetas",
            "startWith": "$_id",
            "connectFromField": "_id",
            "connectToField": "padreId",
            "as": "descendientes",
            "depthField": "nivel",
            "restrictSearchWithMatch": {"activo": True},
        }},

        # Etapa 3 — progreso agregado sobre el array de descendientes:
        #   - puntosTotales: $sum sobre los puntos de TODOS los descendientes
        #     ($sum ignora los null de los nodos intermedios: no puntúan)
        #   - puntosHechos: lo mismo pero filtrando columna = done
        {"$addFields": {
            "puntosTotales": {"$sum": "$descendientes.puntos"},
            "puntosHechos": {"$sum": {
                "$map": {
                    "input": {"$filter": {
                        "input": "$descendientes",
                        "as": "d",
                        "cond": {"$eq": ["$$d.columna", "done"]},
                    }},
                    "as": "d",
                    "in": "$$d.puntos",
                },
            }},
        }},

        # Etapa 4 — porcentaje, protegido contra división por cero (un nodo
        # recién partido aún sin hijos puntuados).
        {"$addFields": {
            "progresoPct": {"$cond": [
                {"$gt": ["$puntosTotales", 0]},
                {"$round": [{"$multiply": [
                    {"$divide": ["$puntosHechos", "$puntosTotales"]}, 100]}, 0]},
                0,
            ]},
        }},

        # Etapa 5 — presentación: del subárbol solo lo que la UI dibuja,
        # ordenado por nivel para que el árbol salga de arriba hacia abajo.
        {"$project": {
            "_id": 0,
            "tarjetaId": "$_id",
            "titulo": 1, "tipo": 1, "liderId": 1,
            "puntosTotales": 1, "puntosHechos": 1, "progresoPct": 1,
            "descendientes": {
                "$map": {
                    "input": {"$sortArray": {"input": "$descendientes",
                                             "sortBy": {"nivel": 1, "orden": 1}}},
                    "as": "d",
                    "in": {
                        "tarjetaId": "$$d._id",
                        "titulo": "$$d.titulo",
                        "tipo": "$$d.tipo",
                        "puntos": "$$d.puntos",
                        "columna": "$$d.columna",
                        "padreId": "$$d.padreId",
                        "nivel": "$$d.nivel",
                        "asignadoNombre": "$$d.asignadoNombre",
                        "bloqueado": "$$d.bloqueado.estado",
                    },
                },
            },
        }},
    ]
