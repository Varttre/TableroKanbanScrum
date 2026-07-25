"""Páginas HTML (Jinja2, render en el servidor).

El tablero se arma con las 2 consultas — proyecto + tarjetas — sin ningún
$lookup: por eso existen las denormalizaciones (proyectoNombre, asignadoNombre)
y las columnas embebidas. El JavaScript del cliente solo maneja el drag & drop;
toda la lógica de negocio vive en servicios.mover_tarjeta.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app import servicios
from app.db import db
from app.utiles import a_json, o_404, oid

router = APIRouter(tags=["paginas"], include_in_schema=False)
templates = Jinja2Templates(directory="app/templates")


def _usuarios_activos():
    return a_json(list(db.usuarios.find({"activo": True}).sort("nombre")))


@router.get("/")
def inicio(request: Request):
    """Portada: los proyectos activos con su sprint en curso."""
    proyectos = list(db.proyectos.find({"activo": True}))
    for p in proyectos:
        s = db.sprints.find_one({"proyectoId": p["_id"], "estado": "activo"})
        p["sprintActivo"] = s["nombre"] if s else None
        p["sprintObjetivo"] = s["objetivo"] if s else None
    usuarios = _usuarios_activos()
    return templates.TemplateResponse(request, "inicio.html", {
        "proyectos": a_json(proyectos),
        "usuarios": usuarios,
        # para el formulario de nuevo proyecto (checkboxes de equipo)
        "usuarios_js": [{"id": u["_id"], "nombre": u["nombre"], "rol": u["rol"]}
                        for u in usuarios],
    })


@router.get("/dashboard/{proyectoId}")
def dashboard(request: Request, proyectoId: str):
    """Dashboard de métricas: la página consume los endpoints /metricas/* por
    fetch — los mismos pipelines que se demuestran en /docs, sin duplicar lógica."""
    pid = oid(proyectoId)
    proyecto = o_404(db.proyectos.find_one({"_id": pid, "activo": True}), "proyecto")
    sprint = db.sprints.find_one({"proyectoId": pid, "estado": "activo"})
    return templates.TemplateResponse(request, "dashboard.html", {
        "proyecto": a_json(proyecto),
        "sprint": a_json(sprint) if sprint else None,
        "usuarios": _usuarios_activos(),
    })


COLUMNA_NOMBRE = {"backlog": "Backlog", "todo": "To Do", "doing": "Doing", "done": "Done"}
DIA_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _describir_evento(e, usuarios, sprints):
    """Convierte un evento del catálogo en una frase humana. Aquí es
    donde el motivo del bloqueo, el origen→destino y compañía se hacen visibles."""
    col = lambda c: COLUMNA_NOMBRE.get(c, c or "—")
    quien = lambda uid: usuarios.get(uid, "—") if uid else "sin responsable"
    sp = lambda sid: sprints.get(sid, "Backlog") if sid else "Backlog"
    meta = e.get("meta", {})
    if e["tipo"] == "creacion":
        extra = " (subtarea)" if meta.get("padreId") else ""
        return f"creada en {col(e['a'])}{extra}"
    if e["tipo"] == "movimiento":
        pts = f" · {meta['puntos']} pts" if meta.get("puntos") else ""
        return f"movida de {col(e['de'])} a {col(e['a'])}{pts}"
    if e["tipo"] == "reasignacion":
        return f"reasignada: {quien(e['de'])} → {quien(e['a'])}"
    if e["tipo"] == "cambio_sprint":
        return f"cambio de sprint: {sp(e['de'])} → {sp(e['a'])}"
    if e["tipo"] == "bloqueo":
        return f"bloqueada — motivo: «{meta.get('motivo', 'sin motivo')}»"
    if e["tipo"] == "desbloqueo":
        return "desbloqueada"
    if e["tipo"] == "edicion":
        return "editada (" + ", ".join(meta.get("campos", [])) + ")"
    if e["tipo"] == "archivado":
        n = meta.get("descendientesArchivados", 0)
        return "archivada" + (f" junto a {n} subtareas" if n else "")
    return e["tipo"]


@router.get("/historial/{proyectoId}")
def historial(request: Request, proyectoId: str, usuarioId: str,
              sprintId: str | None = None, actorId: str | None = None,
              tarjetaId: str | None = None):
    """Auditoría del tablero, SOLO LECTURA y solo moderadores.

    Es la colección `eventos` (append-only) proyectada para humanos:
    agrupada por sprint (rango de fechas) y día de Lima, con filtros
    combinables por sprint, persona (quién hizo la acción) y tarjeta.
    """
    servicios.exigir_moderador(usuarioId)
    pid = oid(proyectoId)
    servicios.exigir_miembro(usuarioId, pid)  # auditoría solo del propio equipo
    proyecto = o_404(db.proyectos.find_one({"_id": pid, "activo": True}), "proyecto")

    sprints = list(db.sprints.find({"proyectoId": pid}).sort("fechaInicio", -1))
    nombres_sprint = {s["_id"]: s["nombre"] for s in sprints}
    titulos = {t["_id"]: t["titulo"]
               for t in db.tarjetas.find({"proyectoId": pid}, {"titulo": 1})}
    nombres_usuario = {u["_id"]: u["nombre"] for u in db.usuarios.find({}, {"nombre": 1})}

    # --- filtros combinables --------------------------------------------------
    filtro: dict = {"tarjetaId": {"$in": list(titulos)}}
    if tarjetaId and oid(tarjetaId) in titulos:   # nunca salirse del proyecto
        filtro["tarjetaId"] = oid(tarjetaId)
    if actorId:
        filtro["usuarioId"] = oid(actorId)
    if sprintId:
        s = o_404(db.sprints.find_one({"_id": oid(sprintId)}), "sprint")
        # "lo que pasó DURANTE el sprint": por rango de fechas, así también se
        # ve el trabajo de backlog hecho esa semana
        filtro["timestamp"] = {"$gte": s["fechaInicio"], "$lte": s["fechaFin"]}
    eventos = list(db.eventos.find(filtro).sort("timestamp", -1).limit(500))

    # --- agrupar: sprint (por rango) → día de Lima → entradas -------------------
    def sprint_de(ts):
        for s in sprints:
            if s["fechaInicio"] <= ts <= s["fechaFin"]:
                return s["nombre"]
        return "Fuera de sprint"

    secciones: list = []          # [{sprint, dias: [{fecha, entradas: [...]}]}]
    for e in eventos:
        ts_lima = e["timestamp"] - timedelta(hours=5)
        nombre_sprint = sprint_de(e["timestamp"])
        dia = f"{DIA_SEMANA[ts_lima.weekday()]} {ts_lima.strftime('%d/%m/%Y')}"
        if not secciones or secciones[-1]["sprint"] != nombre_sprint:
            secciones.append({"sprint": nombre_sprint, "dias": []})
        dias = secciones[-1]["dias"]
        if not dias or dias[-1]["fecha"] != dia:
            dias.append({"fecha": dia, "entradas": []})
        dias[-1]["entradas"].append({
            "hora": ts_lima.strftime("%H:%M"),
            "tipo": e["tipo"],
            "tarjeta": titulos.get(e["tarjetaId"], "(tarjeta eliminada)"),
            "tarjetaId": str(e["tarjetaId"]),
            "actor": nombres_usuario.get(e["usuarioId"], "—"),
            "detalle": _describir_evento(e, nombres_usuario, nombres_sprint),
        })

    return templates.TemplateResponse(request, "historial.html", {
        "proyecto": a_json(proyecto),
        "usuarios": _usuarios_activos(),
        "secciones": secciones,
        "total": len(eventos),
        "sprints_filtro": a_json(sprints),
        "tarjetas_filtro": sorted(
            ({"id": str(k), "titulo": v} for k, v in titulos.items()),
            key=lambda t: t["titulo"]),
        "sel": {"usuarioId": usuarioId, "sprintId": sprintId or "",
                "actorId": actorId or "", "tarjetaId": tarjetaId or ""},
    })


@router.get("/daily/{proyectoId}")
def daily(request: Request, proyectoId: str):
    """La ceremonia diaria: registrar qué hice / qué haré / qué me bloquea.

    Un documento por (sprint, día), índice único. La página muestra la
    daily de HOY (si existe) y el historial reciente del sprint activo.
    """
    pid = oid(proyectoId)
    proyecto = o_404(db.proyectos.find_one({"_id": pid, "activo": True}), "proyecto")
    sprint = db.sprints.find_one({"proyectoId": pid, "estado": "activo"})

    hoy_doc, historial = None, []
    if sprint:
        # "hoy" en fecha de Lima (UTC-5): el mismo criterio de agrupación que
        # usan los pipelines de métricas y el historial de auditoría
        hoy_lima = (datetime.now(timezone.utc) - timedelta(hours=5)).date()
        dailies = list(db.dailies.find({"sprintId": sprint["_id"]}).sort("fecha", -1))
        for d in dailies:
            if (d["fecha"] - timedelta(hours=5)).date() == hoy_lima:
                hoy_doc = d
        historial = [d for d in dailies if d is not hoy_doc][:5]

    return templates.TemplateResponse(request, "daily.html", {
        "proyecto": a_json(proyecto),
        "sprint": a_json(sprint) if sprint else None,
        "usuarios": _usuarios_activos(),
        "hoy": a_json(hoy_doc) if hoy_doc else None,
        "historial": a_json(historial),
        "miembros_ids": [str(m["usuarioId"]) for m in proyecto["miembros"]],
    })


@router.get("/tablero/{proyectoId}")
def tablero(request: Request, proyectoId: str, nodo: str | None = None):
    """El tablero 2D. Con ?nodo=<id> muestra los hijos de ese nodo (drill-down)."""
    pid = oid(proyectoId)
    proyecto = o_404(db.proyectos.find_one({"_id": pid, "activo": True}), "proyecto")
    sprint = db.sprints.find_one({"proyectoId": pid, "estado": "activo"})

    # --- consulta de tarjetas -------------------------------------------------
    breadcrumb, nodo_doc = [], None
    if nodo:
        # Drill-down: los hijos directos del nodo. El breadcrumb sale del
        # materialized path: `ancestros` YA ES la ruta raíz→padre.
        nodo_doc = o_404(db.tarjetas.find_one({"_id": oid(nodo), "activo": True}), "nodo")
        cadena = nodo_doc["ancestros"] + [nodo_doc["_id"]]
        titulos = {t["_id"]: t["titulo"]
                   for t in db.tarjetas.find({"_id": {"$in": cadena}}, {"titulo": 1})}
        breadcrumb = [{"id": str(i), "titulo": titulos.get(i, "?")} for i in cadena]
        filtro = {"padreId": nodo_doc["_id"], "activo": True}
    else:
        # Vista raíz: tarjetas del sprint activo + backlog del proyecto:
        # la columna Backlog muestra lo que aún no entra al sprint).
        pertenece = [{"sprintId": None}]
        if sprint:
            pertenece.append({"sprintId": sprint["_id"]})
        filtro = {"proyectoId": pid, "activo": True, "padreId": None, "$or": pertenece}
    tarjetas = list(db.tarjetas.find(filtro).sort("orden"))

    # --- progreso de los nodos visibles (badge y drill-down) -----------------
    # Un find por `ancestros` (multikey) trae TODOS los descendientes de
    # todos los nodos visibles de una sola vez; el reparto se hace en memoria.
    ids_nodos = {t["_id"] for t in tarjetas if t["tipo"] == "nodo"}
    if nodo_doc is not None:
        ids_nodos.add(nodo_doc["_id"])  # el badge del breadcrumb muestra SU progreso
    progreso: dict = {}
    if ids_nodos:
        for d in db.tarjetas.find({"ancestros": {"$in": list(ids_nodos)}, "activo": True},
                                  {"ancestros": 1, "puntos": 1, "columna": 1}):
            for anc in d["ancestros"]:
                if anc in ids_nodos:
                    p = progreso.setdefault(str(anc), {"total": 0, "hechos": 0, "n": 0})
                    p["n"] += 1
                    if d.get("puntos"):
                        p["total"] += d["puntos"]
                        if d["columna"] == "done":
                            p["hechos"] += d["puntos"]
        for p in progreso.values():
            p["pct"] = round(100 * p["hechos"] / p["total"]) if p["total"] else 0

    # --- grid: una fila por miembro + «Sin asignar» ---------------------------
    tarjetas = a_json(tarjetas)
    filas = [{"id": m["usuarioId"], "nombre": m["nombre"]}
             for m in a_json(proyecto["miembros"])]
    conocidos = {f["id"] for f in filas}
    for t in tarjetas:  # responsable que ya no es miembro: fila extra, no se pierde
        if t["asignadoA"] and t["asignadoA"] not in conocidos:
            filas.append({"id": t["asignadoA"], "nombre": t["asignadoNombre"]})
            conocidos.add(t["asignadoA"])
    filas.append({"id": "sin-asignar", "nombre": "Sin asignar"})

    for f in filas:
        f["celdas"] = {c["clave"]: [] for c in proyecto["columnas"]}
    por_fila = {f["id"]: f for f in filas}
    for t in tarjetas:
        fila = t["asignadoA"] or "sin-asignar"
        por_fila[fila]["celdas"].setdefault(t["columna"], []).append(t)

    return templates.TemplateResponse(request, "tablero.html", {
        "proyecto": a_json(proyecto),
        "sprint": a_json(sprint) if sprint else None,
        "usuarios": _usuarios_activos(),
        "filas": filas,
        "breadcrumb": breadcrumb,
        "nodo": a_json(nodo_doc) if nodo_doc else None,
        "progreso": progreso,
        # para los formularios del tablero (crear tarjeta, dividir, subtareas)
        "miembros": [{"id": m["usuarioId"], "nombre": m["nombre"]}
                     for m in a_json(proyecto["miembros"])],
    })
