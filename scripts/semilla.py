"""Semilla: 3 sprints cerrados + 1 activo (D-12) con historia coherente de eventos.

Uso:  python -m scripts.semilla        (borra y re-siembra; idempotente)

Diseño de la historia (startup "Rumbo", Lima):
- Proyecto protagonista "Qhatu Delivery": 4 sprints semanales (lun-vie), velocity
  20 / 24 / 23 en los cerrados, sprint 4 activo a mitad de semana.
- Proyecto secundario "Web Andina Travel": 1 sprint activo, poca historia. Existe
  para demostrar multi-proyecto (Diego trabaja en ambos → consulta C9 de carga).
- Árbol (D-06): la historia "Módulo de pagos" nació con 21 puntos (> 13) y se
  partió: se convirtió en nodo y el trabajo real vive en hijos y nietos (3 niveles).
- Una tarjeta bloqueada y una estancada en Doing (alimentan el pipeline 6).

Todo timestamp se guarda en UTC. Lima es UTC-5 fijo (sin horario de verano), así
que las horas laborales 9:00-18:00 Lima son 14:00-23:00 UTC del mismo día.
"""

import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bson import ObjectId

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import db  # noqa: E402

random.seed(42)  # semilla determinista: re-sembrar produce exactamente los mismos datos

UTC = timezone.utc


def lima(anio, mes, dia, hora=9, minuto=0):
    """Momento en hora de Lima expresado en UTC (Lima = UTC-5 todo el año)."""
    return datetime(anio, mes, dia, hora, minuto, tzinfo=UTC) + timedelta(hours=5)


def jitter(ts, max_min=25):
    """Minutos aleatorios para que los eventos no caigan todos en punto."""
    return ts + timedelta(minutes=random.randint(0, max_min))


# ---------------------------------------------------------------------------
# 1. USUARIOS — 8 personas: 2 moderadores + 6 desarrolladores (equipo 7±2)
# ---------------------------------------------------------------------------

def oid():
    # ObjectId desde el random YA SEMBRADO (seed 42): re-sembrar produce los
    # MISMOS ids — las URLs guardadas del tablero sobreviven a la re-siembra.
    return ObjectId(random.randbytes(12))


USUARIOS = {
    "lucia":     {"_id": oid(), "nombre": "Lucía Fernández",   "email": "lfernandez@rumbo.pe", "rol": "moderador",     "activo": True},
    "marco":     {"_id": oid(), "nombre": "Marco Quispe",      "email": "mquispe@rumbo.pe",    "rol": "moderador",     "activo": True},
    "alejandro": {"_id": oid(), "nombre": "Alejandro Torres",  "email": "atorres@rumbo.pe",    "rol": "desarrollador", "activo": True},
    "valeria":   {"_id": oid(), "nombre": "Valeria Huamán",    "email": "vhuaman@rumbo.pe",    "rol": "desarrollador", "activo": True},
    "diego":     {"_id": oid(), "nombre": "Diego Rojas",       "email": "drojas@rumbo.pe",     "rol": "desarrollador", "activo": True},
    "camila":    {"_id": oid(), "nombre": "Camila Paredes",    "email": "cparedes@rumbo.pe",   "rol": "desarrollador", "activo": True},
    "jorge":     {"_id": oid(), "nombre": "Jorge Mamani",      "email": "jmamani@rumbo.pe",    "rol": "desarrollador", "activo": True},
    "fiorella":  {"_id": oid(), "nombre": "Fiorella Castillo", "email": "fcastillo@rumbo.pe",  "rol": "desarrollador", "activo": True},
}


def uid(clave):
    return USUARIOS[clave]["_id"]


def unombre(clave):
    return USUARIOS[clave]["nombre"]


def miembro(clave):
    return {"usuarioId": uid(clave), "nombre": unombre(clave)}


# ---------------------------------------------------------------------------
# 2. PROYECTOS — columnas embebidas con contador wip (D-11); se recuenta al final
# ---------------------------------------------------------------------------

def columnas_estandar():
    return [
        {"clave": "backlog", "nombre": "Backlog", "orden": 1, "limiteWip": None, "wip": 0},
        {"clave": "todo",    "nombre": "To Do",   "orden": 2, "limiteWip": None, "wip": 0},
        {"clave": "doing",   "nombre": "Doing",   "orden": 3, "limiteWip": 5,    "wip": 0},
        {"clave": "done",    "nombre": "Done",    "orden": 4, "limiteWip": None, "wip": 0},
    ]


PROY_QHATU = {
    "_id": oid(), "nombre": "Qhatu Delivery", "cliente": "Qhatu S.A.C.",
    "estado": "activo", "columnas": columnas_estandar(),
    "miembros": [miembro(k) for k in ("lucia", "alejandro", "valeria", "diego", "camila")],
    "activo": True,
}
PROY_ANDINA = {
    "_id": oid(), "nombre": "Web Andina Travel", "cliente": "Andina Travel E.I.R.L.",
    "estado": "activo", "columnas": columnas_estandar(),
    "miembros": [miembro(k) for k in ("marco", "jorge", "fiorella", "diego")],
    "activo": True,
}

# ---------------------------------------------------------------------------
# 3. SPRINTS — semanales lun-vie. Hoy es jueves 2026-07-23 (sprint 4 a mitad)
# ---------------------------------------------------------------------------

def sprint(proyecto, nombre, objetivo, lunes, estado):
    viernes = lunes + timedelta(days=4)
    return {
        "_id": oid(), "proyectoId": proyecto["_id"], "nombre": nombre,
        "objetivo": objetivo,
        "fechaInicio": lima(lunes.year, lunes.month, lunes.day, 9),
        "fechaFin": lima(viernes.year, viernes.month, viernes.day, 18),
        "estado": estado,
        "activo": True,  # mismo campo de borrado lógico que escribe el router
    }


from datetime import date  # noqa: E402

S1 = sprint(PROY_QHATU, "Sprint 1", "Registro de usuarios y catálogo navegable", date(2026, 6, 29), "cerrado")
S2 = sprint(PROY_QHATU, "Sprint 2", "Carrito y checkout contra entrega",          date(2026, 7, 6),  "cerrado")
S3 = sprint(PROY_QHATU, "Sprint 3", "Seguimiento de pedidos y calificaciones",    date(2026, 7, 13), "cerrado")
S4 = sprint(PROY_QHATU, "Sprint 4", "Módulo de pagos en línea",                   date(2026, 7, 20), "activo")
SA1 = sprint(PROY_ANDINA, "Sprint 1", "Landing pública con cotizador",            date(2026, 7, 20), "activo")

SPRINTS = [S1, S2, S3, S4, SA1]


def dia_sprint(sp, d):
    """El día d (0=lunes … 4=viernes) del sprint, como fecha calendario."""
    inicio = sp["fechaInicio"] - timedelta(hours=5)  # de vuelta a hora Lima
    f = inicio.date() + timedelta(days=d)
    return f


# ---------------------------------------------------------------------------
# 4. TARJETAS + EVENTOS — fábrica y ciclo de vida
# ---------------------------------------------------------------------------

TARJETAS: list = []
EVENTOS: list = []


def fabrica(proyecto, titulo, tipo, puntos, asignado, sprint_doc, columna,
            padre=None, ancestros=None, lider=None, descripcion="",
            etiquetas=None, checklist=None, comentarios=None, dia_previsto=None):
    t = {
        "_id": oid(), "titulo": titulo, "descripcion": descripcion, "tipo": tipo,
        "proyectoId": proyecto["_id"], "proyectoNombre": proyecto["nombre"],
        "sprintId": sprint_doc["_id"] if sprint_doc else None,
        "asignadoA": uid(asignado) if asignado else None,
        "asignadoNombre": unombre(asignado) if asignado else None,
        "columna": columna, "orden": 0.0,  # el orden real se asigna al final
        "puntos": puntos, "diaPrevisto": dia_previsto,
        "bloqueado": {"estado": False, "motivo": None, "desde": None},
        "padreId": padre["_id"] if padre else None,
        "ancestros": list(ancestros) if ancestros else [],
        "profundidad": len(ancestros) if ancestros else 0,
        "liderId": uid(lider) if lider else None,
        "etiquetas": etiquetas or [], "checklist": checklist or [],
        "comentarios": comentarios or [],
        "activo": True, "createdAt": None, "updatedAt": None, "doneAt": None,
    }
    TARJETAS.append(t)
    return t


def evento(tarjeta, tipo, de, a, usuario, ts, meta=None):
    e = {
        "_id": oid(), "tarjetaId": tarjeta["_id"], "tipo": tipo, "de": de, "a": a,
        "usuarioId": uid(usuario), "timestamp": ts, "meta": meta or {},
    }
    EVENTOS.append(e)
    # updatedAt = el evento más reciente, aunque los eventos se generen fuera de orden
    if tarjeta["updatedAt"] is None or ts > tarjeta["updatedAt"]:
        tarjeta["updatedAt"] = ts
    return e


def crear(tarjeta, usuario, ts, columna_inicial):
    """Evento de creación; fija createdAt."""
    tarjeta["createdAt"] = ts
    evento(tarjeta, "creacion", None, columna_inicial, usuario, ts, {
        "tipoTarjeta": tarjeta["tipo"], "sprintId": tarjeta["sprintId"],
        "padreId": tarjeta["padreId"],
    })


def meta_mov(tarjeta):
    """Denormalización D-13: el movimiento captura puntos y sprint del momento."""
    return {"puntos": tarjeta["puntos"], "sprintId": tarjeta["sprintId"],
            "asignadoA": tarjeta["asignadoA"]}


def mover(tarjeta, de, a, usuario, ts):
    evento(tarjeta, "movimiento", de, a, usuario, ts, meta_mov(tarjeta))
    tarjeta["columna"] = a
    if a == "done" and tarjeta["doneAt"] is None:
        tarjeta["doneAt"] = ts


def ciclo(tarjeta, sp, dev, d_doing, d_done):
    """Ciclo típico dentro de un sprint: To Do → Doing (día X) → Done (día Y).

    La entrada a Doing ocurre en la mañana y la a Done en la tarde: así el
    cycle time (Doing→Done, D-12) da valores realistas de horas laborales.
    """
    fd = dia_sprint(sp, d_doing)
    mover(tarjeta, "todo", "doing", dev, jitter(lima(fd.year, fd.month, fd.day, 9, 30)))
    if d_done is not None:
        fh = dia_sprint(sp, d_done)
        mover(tarjeta, "doing", "done", dev, jitter(lima(fh.year, fh.month, fh.day, 16, 0), 90))


def planificar(sp, tarjetas_specs):
    """Crea las tarjetas de un sprint en la planificación del lunes (To Do)."""
    creadas = []
    for i, (titulo, tipo, puntos, dev, extra) in enumerate(tarjetas_specs):
        fl = dia_sprint(sp, 0)
        ts = lima(fl.year, fl.month, fl.day, 9, 5) + timedelta(minutes=3 * i)
        t = fabrica(PROY_QHATU, titulo, tipo, puntos, dev, sp, "todo", **(extra or {}))
        crear(t, "lucia", ts, "todo")
        creadas.append(t)
    return creadas


# --- Sprints cerrados de Qhatu: (titulo, tipo, puntos, dev, extra) ----------

s1_cards = planificar(S1, [
    ("Registro de usuarios con teléfono",      "historia", 8, "alejandro", {"etiquetas": ["mvp"]}),
    ("Listado de bodegas cercanas",            "historia", 5, "diego",     {"etiquetas": ["mvp", "geo"]}),
    ("Diseñar esquema del catálogo",           "tarea",    3, "valeria",   None),
    ("Investigar API de mapas",                "spike",    2, "diego",     {"etiquetas": ["geo"]}),
    ("Carrito de compras básico",              "historia", 8, "camila",    {"etiquetas": ["mvp"]}),
    ("Bug: validación de teléfono acepta letras", "bug",   2, "alejandro", None),
])
# ciclos: velocity S1 = 8+5+3+2+2 = 20 (el carrito no se terminó → arrastre)
ciclo(s1_cards[0], S1, "alejandro", 0, 2)
ciclo(s1_cards[1], S1, "diego", 1, 3)
ciclo(s1_cards[2], S1, "valeria", 0, 1)
ciclo(s1_cards[3], S1, "diego", 0, 1)
ciclo(s1_cards[4], S1, "camila", 1, None)      # queda en doing al cerrar el sprint
ciclo(s1_cards[5], S1, "alejandro", 3, 4)

s2_cards = planificar(S2, [
    ("Checkout contra entrega",                "historia", 5, "alejandro", {"etiquetas": ["mvp"]}),
    ("Historial de pedidos",                   "historia", 5, "valeria",   None),
    ("Notificación al bodeguero por pedido",   "historia", 3, "diego",     None),
    ("Bug: ítems duplicados en el carrito",    "bug",      3, "camila",    None),
    ("Optimizar consulta de bodegas cercanas", "tarea",    2, "diego",     {"etiquetas": ["geo"]}),
])

# el carrito arrastrado entra al sprint 2 y ahí sí se termina
carrito = s1_cards[4]
f = dia_sprint(S2, 0)
evento(carrito, "cambio_sprint", carrito["sprintId"], S2["_id"], "lucia",
       lima(f.year, f.month, f.day, 9, 40))
carrito["sprintId"] = S2["_id"]
mover(carrito, "doing", "done", "camila",
      jitter(lima(*(lambda d: (d.year, d.month, d.day))(dia_sprint(S2, 2)), 15, 30)))

# velocity S2 = 8 (carrito) + 5+5+3+3 = 24 (optimizar queda a medias → arrastre)
ciclo(s2_cards[0], S2, "alejandro", 1, 4)
ciclo(s2_cards[1], S2, "valeria", 0, 3)
ciclo(s2_cards[2], S2, "diego", 2, 4)
ciclo(s2_cards[3], S2, "camila", 3, 4)
ciclo(s2_cards[4], S2, "diego", 3, None)       # arrastre a S3

s3_cards = planificar(S3, [
    ("Seguimiento del pedido en mapa",         "historia", 8, "diego",     {"etiquetas": ["geo"]}),
    ("Calificación de pedidos con estrellas",  "historia", 5, "valeria",   None),
    ("Bug: la sesión expira durante el checkout", "bug",   3, "alejandro", None),
    ("Refactor del módulo de notificaciones",  "tarea",    3, "camila",    None),
    ("Spike: comparar pasarelas de pago",      "spike",    2, "valeria",   {"etiquetas": ["pago"]}),
])

optimizar = s2_cards[4]
f = dia_sprint(S3, 0)
evento(optimizar, "cambio_sprint", optimizar["sprintId"], S3["_id"], "lucia",
       lima(f.year, f.month, f.day, 9, 40))
optimizar["sprintId"] = S3["_id"]
fh = dia_sprint(S3, 1)
mover(optimizar, "doing", "done", "diego", jitter(lima(fh.year, fh.month, fh.day, 11, 0)))

# velocity S3 = 2 (optimizar) + 8+5+3+3+2 = 23
ciclo(s3_cards[0], S3, "diego", 0, 4)
# el seguimiento estuvo bloqueado un día (caída de la API de mapas) y se desbloqueó:
# así la semilla demuestra el ciclo completo bloqueo→desbloqueo del catálogo (D-13)
mar3 = dia_sprint(S3, 1)
mie3 = dia_sprint(S3, 2)
evento(s3_cards[0], "bloqueo", None, None, "diego",
       lima(mar3.year, mar3.month, mar3.day, 11, 0),
       {"motivo": "API de mapas del proveedor caída"})
evento(s3_cards[0], "desbloqueo", None, None, "diego",
       lima(mie3.year, mie3.month, mie3.day, 9, 30), {})
ciclo(s3_cards[1], S3, "valeria", 1, 3)
ciclo(s3_cards[2], S3, "alejandro", 2, 3)
ciclo(s3_cards[3], S3, "camila", 0, 2)
ciclo(s3_cards[4], S3, "valeria", 3, 4)

# ---------------------------------------------------------------------------
# Sprint 4 (ACTIVO) — el árbol de pagos: nodo → nodo → hojas (3 niveles, D-06)
# ---------------------------------------------------------------------------

lun4 = dia_sprint(S4, 0)

# La épica nace como historia de 21 puntos en la planificación...
epica = fabrica(PROY_QHATU, "Módulo de pagos en línea", "historia", 21, "valeria",
                S4, "todo", lider=None, etiquetas=["pago", "mvp"],
                descripcion="Cobro con tarjeta vía pasarela, confirmación y manejo de errores.")
crear(epica, "lucia", lima(lun4.year, lun4.month, lun4.day, 9, 5), "todo")

# ...supera el límite de 13 puntos (D-06) → se parte: se convierte en nodo con líder
evento(epica, "edicion", None, None, "lucia",
       lima(lun4.year, lun4.month, lun4.day, 9, 35), {"campos": ["tipo", "puntos", "liderId"]})
epica.update({"tipo": "nodo", "puntos": None, "liderId": uid("valeria")})

def hijo(padre, titulo, tipo, puntos, dev, lider=None, **kw):
    t = fabrica(PROY_QHATU, titulo, tipo, puntos, dev, S4, "todo",
                padre=padre, ancestros=padre["ancestros"] + [padre["_id"]],
                lider=lider, **kw)
    crear(t, "lucia", jitter(lima(lun4.year, lun4.month, lun4.day, 9, 40)), "todo")
    return t

# nivel 1: hijos de la épica
integracion = hijo(epica, "Integración con la pasarela", "nodo", None, "diego", lider="diego")
formulario  = hijo(epica, "Formulario de tarjeta con validación", "historia", 5, "camila")
webhook     = hijo(epica, "Webhook de confirmación de pago", "historia", 5, "alejandro",
                   etiquetas=["pago"], dia_previsto=lima(2026, 7, 24, 18))
# nivel 2: nietos (bajo el nodo de integración)
spike_nz  = hijo(integracion, "Spike: sandbox de Niubiz", "spike", 2, "diego")
cobro     = hijo(integracion, "Cobro con tarjeta (flujo feliz)", "historia", 5, "diego",
                 dia_previsto=lima(2026, 7, 23, 18),
                 checklist=[{"texto": "Probar tarjeta rechazada", "hecho": False},
                            {"texto": "Probar monto con decimales", "hecho": True}])
reintento = hijo(integracion, "Reintento ante fallo de cobro", "historia", 3, "camila")

# los nodos entran a doing cuando arranca su primer hijo
mover(epica, "todo", "doing", "valeria", lima(lun4.year, lun4.month, lun4.day, 10, 0))
mover(integracion, "todo", "doing", "diego", lima(lun4.year, lun4.month, lun4.day, 10, 5))

# ciclos de las hojas hasta hoy (jueves, día 3 del sprint)
ciclo(spike_nz, S4, "diego", 0, 1)             # hecho
ciclo(formulario, S4, "camila", 0, 2)          # hecho
ciclo(cobro, S4, "diego", 1, None)             # en doing
ciclo(webhook, S4, "alejandro", 1, None)       # en doing... y se bloquea (martes)

# el reintento estaba asignado a Camila; en la daily del martes pasa a Diego
mar4 = dia_sprint(S4, 1)
evento(reintento, "reasignacion", uid("camila"), uid("diego"), "lucia",
       lima(mar4.year, mar4.month, mar4.day, 9, 20))
reintento.update({"asignadoA": uid("diego"), "asignadoNombre": unombre("diego")})

# bloqueo real: sin credenciales del cliente (alimenta el pipeline 6)
ts_bloqueo = lima(mar4.year, mar4.month, mar4.day, 15, 10)
evento(webhook, "bloqueo", None, None, "alejandro", ts_bloqueo,
       {"motivo": "Esperando credenciales de producción de la pasarela (cliente)"})
webhook["bloqueado"] = {"estado": True,
                        "motivo": "Esperando credenciales de producción de la pasarela (cliente)",
                        "desde": ts_bloqueo}
webhook["comentarios"] = [
    {"_id": oid(), "usuarioId": uid("alejandro"), "nombre": unombre("alejandro"),
     "texto": "Pedí las credenciales al contacto de Qhatu, sin respuesta aún.",
     "fecha": lima(mar4.year, mar4.month, mar4.day, 15, 12)},
    {"_id": oid(), "usuarioId": uid("lucia"), "nombre": unombre("lucia"),
     "texto": "Escalado con el gerente del cliente. Mientras tanto usar el sandbox.",
     "fecha": lima(2026, 7, 22, 10, 4)},
]

# tarjetas sueltas del sprint 4 (fuera del árbol)
resto_s4 = planificar(S4, [
    ("Bug: el total del carrito redondea mal",  "bug",   2, "valeria", None),
    ("Actualizar términos y condiciones",       "tarea", 1, "alejandro", None),
    ("Migrar imágenes de productos a un CDN",   "tarea", 3, "camila", None),
])
ciclo(resto_s4[0], S4, "valeria", 0, 1)
ciclo(resto_s4[1], S4, "alejandro", 2, 2)
ciclo(resto_s4[2], S4, "camila", 0, None)      # en doing desde el lunes → ESTANCADA
# puntos hechos hasta el jueves: 2+5+2+1 = 10 de 26 comprometidos

# backlog de Qhatu (sin sprint, sin asignar)
BACKLOG_QHATU = [
    ("Cupones de descuento", "historia", 8),
    ("Push de estado del pedido", "historia", 5),
    ("Reporte semanal para bodegueros", "historia", 5),
    ("Modo oscuro de la app", "tarea", 2),
]
for i, (titulo, tipo, pts) in enumerate(BACKLOG_QHATU):
    t = fabrica(PROY_QHATU, titulo, tipo, pts, None, None, "backlog")
    crear(t, "lucia", lima(2026, 7, 7, 11, 0) + timedelta(minutes=10 * i), "backlog")

# una tarjeta archivada (borrado lógico D-09, evento "archivado")
descartada = fabrica(PROY_QHATU, "Encuesta de satisfacción en la app", "historia", 3,
                     None, None, "backlog")
crear(descartada, "lucia", lima(2026, 7, 7, 11, 50), "backlog")
evento(descartada, "archivado", None, None, "lucia", lima(2026, 7, 14, 12, 0), {})
descartada["activo"] = False

# ---------------------------------------------------------------------------
# Proyecto Andina Travel — liviano: demuestra multi-proyecto, no historia densa
# ---------------------------------------------------------------------------

luna = dia_sprint(SA1, 0)
andina_specs = [
    ("Maquetar la landing principal",   "historia", 5, "jorge",    0, None),   # doing
    ("Galería de destinos",             "historia", 3, "jorge",    0, 2),      # done
    ("Formulario de cotización",        "historia", 5, "fiorella", None, None),  # todo
    ("Configurar dominio y hosting",    "tarea",    2, "diego",    1, 1),      # done
    ("Cargar textos y fotos del cliente", "tarea",  2, "fiorella", None, None),  # todo
]
for i, (titulo, tipo, pts, dev, d_doing, d_done) in enumerate(andina_specs):
    t = fabrica(PROY_ANDINA, titulo, tipo, pts, dev, SA1, "todo")
    crear(t, "marco", lima(luna.year, luna.month, luna.day, 9, 10) + timedelta(minutes=3 * i), "todo")
    if d_doing is not None:
        ciclo(t, SA1, dev, d_doing, d_done)

for i, (titulo, tipo, pts) in enumerate([("SEO básico", "tarea", 3), ("Blog de destinos", "historia", 5)]):
    t = fabrica(PROY_ANDINA, titulo, tipo, pts, None, None, "backlog")
    crear(t, "marco", lima(2026, 7, 15, 16, 0) + timedelta(minutes=5 * i), "backlog")

# ---------------------------------------------------------------------------
# 5. DAILIES — un documento por (sprint, día); participan los devs del proyecto
# ---------------------------------------------------------------------------

DAILIES = []

FRASES_HICE = ["Avancé en «{t}»", "Terminé lo pendiente de «{t}»", "Revisión de código y avance en «{t}»"]
FRASES_HARE = ["Sigo con «{t}»", "Empiezo «{t}»", "Cierro «{t}» y tomo la siguiente"]


def tarjetas_de(dev, sp):
    return [t["titulo"] for t in TARJETAS
            if t["asignadoA"] == uid(dev) and t["sprintId"] == sp["_id"] and t["tipo"] != "nodo"]


def generar_dailies(sp, devs, dias, bloqueos=None):
    """bloqueos: {(dev, dia): "texto"} para las excepciones con bloqueo real."""
    bloqueos = bloqueos or {}
    for d in dias:
        f = dia_sprint(sp, d)
        participaciones = []
        for dev in devs:
            titulos = tarjetas_de(dev, sp) or ["tareas del sprint"]
            participaciones.append({
                "usuarioId": uid(dev), "nombre": unombre(dev),
                "hice": random.choice(FRASES_HICE).format(t=random.choice(titulos)),
                "hare": random.choice(FRASES_HARE).format(t=random.choice(titulos)),
                "bloqueo": bloqueos.get((dev, d)),
            })
        DAILIES.append({"_id": oid(), "sprintId": sp["_id"],
                        "fecha": lima(f.year, f.month, f.day, 9, 15),
                        "participaciones": participaciones})


DEVS_QHATU = ["alejandro", "valeria", "diego", "camila"]
for sp_cerrado in (S1, S2, S3):
    generar_dailies(sp_cerrado, DEVS_QHATU, range(5))
# sprint activo: dailies de lunes a jueves (hoy); el bloqueo del webhook se declara
generar_dailies(S4, DEVS_QHATU, range(4), bloqueos={
    ("alejandro", 2): "Sin credenciales de producción de la pasarela",
    ("alejandro", 3): "Sigo bloqueado: credenciales de la pasarela",
})
generar_dailies(SA1, ["jorge", "fiorella", "diego"], range(4))

# ---------------------------------------------------------------------------
# 6. ORDEN FRACCIONARIO (D-05) — único por (proyecto, asignado, columna)
# ---------------------------------------------------------------------------

grupos: dict = {}
for t in TARJETAS:
    grupos.setdefault((t["proyectoId"], t["asignadoA"], t["columna"]), []).append(t)
for grupo in grupos.values():
    grupo.sort(key=lambda t: t["createdAt"])
    for i, t in enumerate(grupo):
        t["orden"] = float(i + 1)  # 1.0, 2.0, 3.0… deja huecos para insertar entre medio

# ---------------------------------------------------------------------------
# 7. INSERTAR Y RECONTAR WIP
# ---------------------------------------------------------------------------

def main():
    colecciones = ["usuarios", "proyectos", "sprints", "tarjetas", "eventos", "dailies"]
    for c in colecciones:
        db[c].delete_many({})

    db.usuarios.insert_many(list(USUARIOS.values()))
    db.proyectos.insert_many([PROY_QHATU, PROY_ANDINA])
    db.sprints.insert_many(SPRINTS)
    db.tarjetas.insert_many(TARJETAS)
    db.eventos.insert_many(EVENTOS)
    db.dailies.insert_many(DAILIES)

    # Recuento del contador wip (D-11): tarjetas de TRABAJO (los nodos no cuentan,
    # son agrupadores) del sprint activo, por columna. Es la única escritura del
    # contador fuera del flujo de movimiento; deja el derivado consistente.
    for proyecto, sp_activo in ((PROY_QHATU, S4), (PROY_ANDINA, SA1)):
        for col in proyecto["columnas"]:
            n = db.tarjetas.count_documents({
                "proyectoId": proyecto["_id"], "sprintId": sp_activo["_id"],
                "columna": col["clave"], "tipo": {"$ne": "nodo"}, "activo": True,
            })
            db.proyectos.update_one(
                {"_id": proyecto["_id"], "columnas.clave": col["clave"]},
                {"$set": {"columnas.$.wip": n}})

    print("Semilla insertada en", db.name)
    for c in colecciones:
        print(f"  {c:<10} {db[c].count_documents({}):>4} documentos")
    for p in db.proyectos.find({}, {"nombre": 1, "columnas.clave": 1, "columnas.wip": 1}):
        wip = ", ".join(f"{c['clave']}={c['wip']}" for c in p["columnas"])
        print(f"  wip {p['nombre']}: {wip}")


if __name__ == "__main__":
    main()
