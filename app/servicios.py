"""Lógica de negocio de tarjetas. TODO movimiento pasa por aquí (mitigación D-11).

Reparto de responsabilidades sobre el contador `wip`:
- `mover_tarjeta` usa la **guarda atómica** (D-11): es la operación concurrente real
  (dos personas arrastrando tarjetas a la vez) y la única donde una carrera importa.
- Las mutaciones administrativas raras (crear, archivar, cambiar de sprint) llaman a
  `reconciliar_wip`, que recuenta y corrige. Recontar es barato a esta escala y evita
  duplicar lógica de incrementos en cada esquina.
"""

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException

from app.db import db
from app.utiles import o_404, oid


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def nombre_usuario(usuario_id: ObjectId) -> str:
    u = o_404(db.usuarios.find_one({"_id": usuario_id}), "usuario")
    return u["nombre"]


def registrar_evento(tarjeta_id, tipo, de, a, usuario_id, meta=None):
    """Única puerta de escritura a `eventos` (append-only, D-04)."""
    db.eventos.insert_one({
        "tarjetaId": tarjeta_id, "tipo": tipo, "de": de, "a": a,
        "usuarioId": usuario_id, "timestamp": ahora(), "meta": meta or {},
    })


def sprint_activo_id(proyecto_id):
    s = db.sprints.find_one({"proyectoId": proyecto_id, "estado": "activo"}, {"_id": 1})
    return s["_id"] if s else None


def en_tablero(tarjeta, sprint_activo) -> bool:
    """¿Cuenta esta tarjeta para el WIP? Solo trabajo del sprint activo:
    los nodos son agrupadores, y el backlog no compite por límite."""
    return (tarjeta["tipo"] != "nodo" and sprint_activo is not None
            and tarjeta["sprintId"] == sprint_activo and tarjeta["activo"])


def reconciliar_wip(proyecto_id):
    """Recuenta las tarjetas del sprint activo por columna y corrige el contador."""
    proyecto = db.proyectos.find_one({"_id": proyecto_id})
    if proyecto is None:
        return
    activo = sprint_activo_id(proyecto_id)
    for col in proyecto["columnas"]:
        n = 0
        if activo is not None:
            n = db.tarjetas.count_documents({
                "proyectoId": proyecto_id, "sprintId": activo,
                "columna": col["clave"], "tipo": {"$ne": "nodo"}, "activo": True,
            })
        db.proyectos.update_one(
            {"_id": proyecto_id, "columnas.clave": col["clave"]},
            {"$set": {"columnas.$.wip": n}})


# --- orden fraccionario (D-05) ----------------------------------------------

def _celda(proyecto_id, sprint_id, asignado, columna):
    """La celda REAL del tablero 2D incluye el sprint: sin él, el rebalanceo
    tocaría tarjetas de sprints ya cerrados que comparten (persona, columna)."""
    return {"proyectoId": proyecto_id, "sprintId": sprint_id,
            "asignadoA": asignado, "columna": columna, "activo": True}


def _rebalancear(proyecto_id, sprint_id, asignado, columna):
    """Renumera 1.0, 2.0, … la celda cuando el hueco fraccionario se agotó."""
    tarjetas = list(db.tarjetas.find(
        _celda(proyecto_id, sprint_id, asignado, columna)).sort("orden"))
    for i, t in enumerate(tarjetas):
        db.tarjetas.update_one({"_id": t["_id"]}, {"$set": {"orden": float(i + 1)}})


def calcular_orden(proyecto_id, sprint_id, asignado, columna,
                   vecino_ant_id, vecino_sig_id):
    """Punto medio entre vecinos: una sola escritura en vez de reindexar la columna."""
    def orden_de(vid):
        if vid is None:
            return None
        v = o_404(db.tarjetas.find_one({"_id": oid(vid)}), "vecino")
        return v["orden"]

    ant, sig = orden_de(vecino_ant_id), orden_de(vecino_sig_id)
    if ant is None and sig is None:
        # al final de la celda destino
        ultimo = db.tarjetas.find_one(
            _celda(proyecto_id, sprint_id, asignado, columna), sort=[("orden", -1)])
        return (ultimo["orden"] + 1.0) if ultimo else 1.0
    if ant is None:
        return sig / 2
    if sig is None:
        return ant + 1.0
    medio = (ant + sig) / 2
    if medio in (ant, sig):  # precisión agotada (~50 inserciones en el mismo hueco)
        _rebalancear(proyecto_id, sprint_id, asignado, columna)
        return calcular_orden(proyecto_id, sprint_id, asignado, columna,
                              vecino_ant_id, vecino_sig_id)
    return medio


# --- ciclo de vida de la tarjeta --------------------------------------------

def crear_tarjeta(d) -> dict:
    """Crea la tarjeta resolviendo denormalizaciones y jerarquía; evento `creacion`."""
    proyecto = o_404(db.proyectos.find_one({"_id": oid(d.proyectoId), "activo": True}), "proyecto")
    actor = exigir_miembro(d.usuarioId, proyecto["_id"])

    sprint_id = None
    if d.sprintId is not None:
        sprint = o_404(db.sprints.find_one({"_id": oid(d.sprintId)}), "sprint")
        sprint_id = sprint["_id"]
    columna = "todo" if sprint_id else "backlog"  # nace en To Do si entra a un sprint

    asignado, asignado_nombre = None, None
    if d.asignadoA is not None:
        asignado = oid(d.asignadoA)
        asignado_nombre = nombre_usuario(asignado)

    # jerarquía (D-03): ancestros = camino materializado del padre + el padre
    padre_id, ancestros = None, []
    if d.padreId is not None:
        padre = o_404(db.tarjetas.find_one({"_id": oid(d.padreId), "activo": True}), "padre")
        padre_id = padre["_id"]
        ancestros = padre["ancestros"] + [padre_id]

    ts = ahora()
    tarjeta = {
        "titulo": d.titulo, "descripcion": d.descripcion, "tipo": d.tipo,
        "proyectoId": proyecto["_id"], "proyectoNombre": proyecto["nombre"],
        "sprintId": sprint_id, "asignadoA": asignado, "asignadoNombre": asignado_nombre,
        "columna": columna,
        "orden": calcular_orden(proyecto["_id"], sprint_id, asignado, columna, None, None),
        "puntos": d.puntos, "diaPrevisto": None,
        "bloqueado": {"estado": False, "motivo": None, "desde": None},
        "padreId": padre_id, "ancestros": ancestros, "profundidad": len(ancestros),
        "liderId": oid(d.liderId) if d.liderId else None,
        "etiquetas": d.etiquetas, "checklist": [c.model_dump() for c in d.checklist],
        "comentarios": [], "activo": True,
        "createdAt": ts, "updatedAt": ts, "doneAt": None,
    }
    db.tarjetas.insert_one(tarjeta)
    registrar_evento(tarjeta["_id"], "creacion", None, columna, actor,
                     {"tipoTarjeta": d.tipo, "sprintId": sprint_id, "padreId": padre_id})
    reconciliar_wip(proyecto["_id"])
    return tarjeta


def mover_tarjeta(tarjeta_id, d) -> dict:
    """El endpoint delicado: guarda WIP atómica + orden fraccionario + evento."""
    t = o_404(db.tarjetas.find_one({"_id": tarjeta_id, "activo": True}), "tarjeta")
    proyecto = o_404(db.proyectos.find_one({"_id": t["proyectoId"]}), "proyecto")
    actor = exigir_miembro(d.usuarioId, proyecto["_id"])

    claves = {c["clave"]: c for c in proyecto["columnas"]}
    if d.columna not in claves:
        raise HTTPException(400, f"Columna inexistente: {d.columna}")
    origen, destino = t["columna"], d.columna

    # "sin-asignar" = soltar en la fila «Sin asignar» del tablero: quita el
    # responsable. Mismo convenio que sprintId="backlog" en actualizar_tarjeta
    # (None a secas significa "no cambiar de fila").
    if d.asignadoA == "sin-asignar":
        nuevo_asignado = None
    elif d.asignadoA:
        nuevo_asignado = oid(d.asignadoA)
    else:
        nuevo_asignado = t["asignadoA"]
    cambia_fila = nuevo_asignado != t["asignadoA"]

    activo = sprint_activo_id(proyecto["_id"])

    # D-16: en el tablero, la columna Backlog significa "fuera del sprint".
    # Sacar una tarjeta del backlog la mete al sprint activo; devolverla al
    # backlog la saca del sprint. Así el arrastre mantiene coherentes columna,
    # sprint, WIP y métricas (burndown/velocity) sin pasos manuales.
    sprint_nuevo = t["sprintId"]
    if origen == "backlog" and destino != "backlog":
        if activo is None:
            raise HTTPException(409, "No hay sprint activo: activa un sprint "
                                     "antes de sacar tarjetas del backlog.")
        sprint_nuevo = activo
    elif destino == "backlog" and origen != "backlog":
        sprint_nuevo = None

    # Guarda WIP (D-11): un findOneAndUpdate sobre EL DOCUMENTO DEL PROYECTO.
    # El filtro exige wip < limiteWip en la columna destino; si no encaja, la
    # operación no modifica nada y el movimiento se rechaza. Contador y límite
    # viven en el mismo documento → atómico sin transacción.
    # `contaba`/`contara`: si la tarjeta entra o sale del tablero (D-16), solo
    # se toca el contador del lado que corresponde.
    contaba = en_tablero(t, activo)
    contara = en_tablero({**t, "columna": destino, "sprintId": sprint_nuevo}, activo)
    if destino != origen and (contaba or contara):
        filtro = {"_id": proyecto["_id"]}
        limite = claves[destino]["limiteWip"]
        if contara and limite is not None:
            filtro["columnas"] = {"$elemMatch": {"clave": destino, "wip": {"$lt": limite}}}
        incrementos, array_filters = {}, []
        if contara:
            incrementos["columnas.$[dest].wip"] = 1
            array_filters.append({"dest.clave": destino})
        if contaba:
            incrementos["columnas.$[orig].wip"] = -1
            array_filters.append({"orig.clave": origen})
        r = db.proyectos.find_one_and_update(
            filtro, {"$inc": incrementos}, array_filters=array_filters,
        )
        if r is None:
            raise HTTPException(
                409, f"Límite WIP alcanzado en «{claves[destino]['nombre']}» "
                     f"({limite}). Termina algo antes de empezar otra cosa.")

    ts = ahora()
    cambios = {
        "columna": destino, "updatedAt": ts,
        "orden": calcular_orden(proyecto["_id"], sprint_nuevo, nuevo_asignado,
                                destino, d.vecinoAnteriorId, d.vecinoSiguienteId),
    }
    if sprint_nuevo != t["sprintId"]:
        cambios["sprintId"] = sprint_nuevo
    if cambia_fila:
        cambios["asignadoA"] = nuevo_asignado
        cambios["asignadoNombre"] = nombre_usuario(nuevo_asignado) if nuevo_asignado else None
    if destino == "done" and t["doneAt"] is None:
        cambios["doneAt"] = ts  # primera entrada a Done: alimenta la velocity

    db.tarjetas.update_one({"_id": tarjeta_id}, {"$set": cambios})

    if sprint_nuevo != t["sprintId"]:
        registrar_evento(tarjeta_id, "cambio_sprint", t["sprintId"], sprint_nuevo, actor)
    if destino != origen:
        # D-13: el evento captura puntos y sprint DEL MOMENTO del movimiento
        registrar_evento(tarjeta_id, "movimiento", origen, destino, actor,
                         {"puntos": t["puntos"], "sprintId": sprint_nuevo,
                          "asignadoA": nuevo_asignado})
    if cambia_fila:
        registrar_evento(tarjeta_id, "reasignacion", t["asignadoA"], nuevo_asignado, actor)
    return db.tarjetas.find_one({"_id": tarjeta_id})


CAMPOS_EDITABLES = ["titulo", "descripcion", "tipo", "puntos", "etiquetas",
                    "diaPrevisto", "checklist", "liderId"]


def actualizar_tarjeta(tarjeta_id, d) -> dict:
    """PATCH parcial. Cada tipo de cambio escribe su evento correspondiente."""
    t = o_404(db.tarjetas.find_one({"_id": tarjeta_id, "activo": True}), "tarjeta")
    actor = exigir_miembro(d.usuarioId, t["proyectoId"])
    enviados = d.model_dump(exclude_unset=True)  # solo lo que el cliente mandó
    cambios, editados = {}, []

    for campo in CAMPOS_EDITABLES:
        if campo in enviados:
            valor = enviados[campo]
            if campo == "liderId":
                valor = oid(valor) if valor else None
            if campo == "checklist":
                valor = [c if isinstance(c, dict) else c.model_dump() for c in valor]
            cambios[campo] = valor
            editados.append(campo)

    if "sprintId" in enviados:  # "backlog" = volver al backlog
        nuevo = None if enviados["sprintId"] in (None, "backlog") else oid(enviados["sprintId"])
        if nuevo != t["sprintId"]:
            cambios["sprintId"] = nuevo
            cambios["columna"] = "todo" if nuevo else "backlog"
            registrar_evento(tarjeta_id, "cambio_sprint", t["sprintId"], nuevo, actor)

    if "asignadoA" in enviados:
        nuevo = oid(enviados["asignadoA"]) if enviados["asignadoA"] else None
        if nuevo != t["asignadoA"]:
            cambios["asignadoA"] = nuevo
            cambios["asignadoNombre"] = nombre_usuario(nuevo) if nuevo else None
            registrar_evento(tarjeta_id, "reasignacion", t["asignadoA"], nuevo, actor)

    if editados:
        registrar_evento(tarjeta_id, "edicion", None, None, actor, {"campos": editados})
    if cambios:
        cambios["updatedAt"] = ahora()
        db.tarjetas.update_one({"_id": tarjeta_id}, {"$set": cambios})
        if "sprintId" in cambios:
            reconciliar_wip(t["proyectoId"])
    return db.tarjetas.find_one({"_id": tarjeta_id})


def exigir_miembro(usuario_id, proyecto_id):
    """Guarda de membresía (D-18): con un proyecto solo interactúan sus
    miembros — también los moderadores deben serlo. Quien no lo es puede MIRAR
    el tablero (transparencia entre equipos), pero no tocarlo."""
    uid_ = oid(usuario_id) if isinstance(usuario_id, str) else usuario_id
    p = o_404(db.proyectos.find_one({"_id": proyecto_id},
                                    {"miembros": 1, "nombre": 1}), "proyecto")
    if not any(m["usuarioId"] == uid_ for m in p["miembros"]):
        raise HTTPException(
            403, f"No eres miembro de «{p['nombre']}»: puedes observarlo, no modificarlo")
    return uid_


def exigir_moderador(usuario_id):
    """Guarda declarativa de administración (D-17): crear/editar proyectos,
    usuarios y sprints es trabajo del moderador. Sin autenticación real (D-08),
    el actor viene del selector de cabecera — la regla vive igual en el
    servidor para que la API tampoco lo permita."""
    u = o_404(db.usuarios.find_one({"_id": oid(usuario_id), "activo": True}), "usuario")
    if u["rol"] != "moderador":
        raise HTTPException(403, "Solo un moderador puede administrar "
                                 "proyectos, usuarios y sprints")
    return u


def es_lider(usuario_id, tarjeta) -> bool:
    """El permiso de D-07: ¿este usuario lidera la tarjeta o alguno de sus
    ancestros? UNA consulta indexada resuelve la pregunta a cualquier
    profundidad, reutilizando el materialized path (D-03): el liderazgo de un
    nodo alcanza a todo su subárbol sin recorrerlo.
    """
    if tarjeta.get("liderId") == usuario_id:
        return True
    if not tarjeta["ancestros"]:
        return False
    return db.tarjetas.find_one(
        {"_id": {"$in": tarjeta["ancestros"]}, "liderId": usuario_id},
        {"_id": 1}) is not None


def puede_archivar(usuario_id, tarjeta) -> bool:
    """Regla declarativa (sin autenticación, D-08): archivar destruye visibilidad
    de trabajo ajeno, así que exige rol de moderador o liderazgo sobre la rama."""
    u = o_404(db.usuarios.find_one({"_id": usuario_id, "activo": True}), "usuario")
    return u["rol"] == "moderador" or es_lider(usuario_id, tarjeta)


def archivar_tarjeta(tarjeta_id, usuario_id) -> dict:
    """Borrado lógico (D-09) del subárbol completo: archivar un padre sin sus
    descendientes dejaría huérfanos invisibles que seguirían contando métricas."""
    t = o_404(db.tarjetas.find_one({"_id": tarjeta_id, "activo": True}), "tarjeta")
    actor = exigir_miembro(usuario_id, t["proyectoId"])
    if not puede_archivar(actor, t):
        raise HTTPException(
            403, "Solo un moderador o el líder de esta rama puede archivarla (D-07)")
    ts = ahora()
    descendientes = [x["_id"] for x in db.tarjetas.find(
        {"ancestros": tarjeta_id, "activo": True}, {"_id": 1})]
    db.tarjetas.update_many({"_id": {"$in": [tarjeta_id] + descendientes}},
                            {"$set": {"activo": False, "updatedAt": ts}})
    registrar_evento(tarjeta_id, "archivado", None, None, actor,
                     {"descendientesArchivados": len(descendientes)})
    reconciliar_wip(t["proyectoId"])
    return {"archivadas": 1 + len(descendientes)}
