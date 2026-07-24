# Tablero Kanban-Scrum con MongoDB

Aplicación web que digitaliza el tablero híbrido Scrum-Kanban de **Rumbo**, una
startup limeña de desarrollo de software (caso de estudio): gestión multi-proyecto,
tablero 2D con drag & drop, jerarquía de tarjetas, límites WIP validados sin
condición de carrera, historial inmutable de eventos y métricas ágiles calculadas
con el framework de agregación de MongoDB.

> Trabajo final del curso **Base de Datos II** (UTP). La nota está en el modelado
> NoSQL, el CRUD y las consultas de agregación — la UI existe para demostrarlos.

**Demo desplegada:** https://tablero-kanban.onrender.com
*(free tier: la primera petición tras dormir tarda ~1 minuto)*

---

## Qué hace

- **Tablero 2D**: filas = integrantes, columnas = Backlog / To Do / Doing / Done.
  Arrastrar una tarjeta persiste su posición (orden fraccionario), valida el límite
  WIP de forma atómica (rechazo 409 visible) y registra el evento. Sacarla del
  Backlog la mete al sprint activo; arrastrarla a otra fila la reasigna.
- **Jerarquía de trabajo**: una historia de más de 13 puntos se parte (regla Scrum);
  el nodo padre muestra el progreso agregado de su subárbol y permite drill-down
  con breadcrumb, a cualquier profundidad.
- **Daily**: cada integrante registra qué hizo / qué hará / qué lo bloquea
  (`/daily/<proyectoId>`); los bloqueos quedan resaltados.
- **Dashboard** (`/dashboard/<proyectoId>`): velocity con media móvil, burndown
  real vs ideal, KPIs del sprint y carga por integrante — todo servido por
  pipelines de agregación (`/metricas/*`).
- **API completa** autodocumentada en `/docs` (Swagger): CRUD de las 6 colecciones
  y los 6 pipelines.

## Stack

| Capa | Tecnología |
|---|---|
| Backend | Python 3.12 · FastAPI · PyMongo (driver crudo, **sin ODM** a propósito) |
| Base de datos | MongoDB Atlas M0 con validadores `$jsonSchema` por colección |
| Frontend | Jinja2 (render en servidor) · SortableJS · Chart.js — sin npm, sin build |
| Deploy | Render (auto-deploy desde `main`) |

Sin ODM porque los pipelines de agregación deben quedar visibles como listas de
diccionarios idénticas a lo que se escribiría en `mongosh`: son el material del
informe y de la sustentación.

## Levantarlo en local

Requisitos: Python 3.12+ y una cadena de conexión de MongoDB Atlas (M0 gratuito).

```bash
git clone https://github.com/Varttre/TableroKanbanScrum.git
cd TableroKanbanScrum
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt

copy .env.example .env            # y pegar tu MONGODB_URI dentro
```

Preparar la base (los tres scripts son idempotentes y re-ejecutables):

```bash
python scripts/crear_colecciones.py   # 6 colecciones con validador $jsonSchema
python scripts/semilla.py             # datos demo: 3 sprints cerrados + 1 activo
python scripts/crear_indices.py       # los 11 índices de la matriz de acceso
```

Arrancar:

```bash
uvicorn app.main:app --reload
# → http://127.0.0.1:8000        (tablero)
# → http://127.0.0.1:8000/docs   (API)
```

Verificación opcional: `python scripts/verificar_pipelines.py` (21 asserts contra
los valores conocidos de la semilla; los del radar de bloqueos dependen de la
fecha fija de la semilla, 2026-07-23, y se omiten con aviso en otra fecha).

## La semilla

`scripts/semilla.py` genera una historia **coherente y determinista** (misma
semilla → mismos datos e ids): 8 usuarios, 2 proyectos, 4+1 sprints, 38 tarjetas
(incluido un árbol de 3 niveles), 96 eventos y 23 dailies. Está diseñada para que
las métricas den valores conocidos: velocity 20/24/23, burndown 26→16, una tarjeta
bloqueada y una estancada. Borra y re-siembra todo en cada ejecución.

## Arquitectura (capas)

```
app/
├── main.py            punto de entrada FastAPI + estáticos
├── db.py              LA conexión a MongoDB (un MongoClient por proceso)
├── modelos.py         contratos Pydantic (validación de entrada)
├── servicios.py       lógica de negocio: guarda WIP atómica, orden fraccionario,
│                      eventos automáticos, jerarquía, permisos de líder
├── routers/           un router HTTP por colección + /metricas + páginas HTML
├── queries/           LOS 6 PIPELINES, un archivo por pipeline, comentados
│                      etapa por etapa (el corazón del proyecto)
├── templates/         Jinja2: tablero, dashboard, daily
└── static/            CSS + JS propios; vendor/ (SortableJS, Chart.js locales)
scripts/               crear_colecciones · semilla · crear_indices · explain · verificar
docs/                  modelo de datos, decisiones de diseño, índices, bitácora
```

Regla de las capas: solo se llama hacia abajo (router → servicio → BD) y la lógica
existe una sola vez — todo movimiento de tarjeta pasa por `servicios.mover_tarjeta`,
venga del tablero o de la API.

## Documentación del proyecto

| Documento | Contenido |
|---|---|
| `docs/MODELO_DATOS.md` | Matriz de 18 patrones de acceso + esquema de las 6 colecciones |
| `docs/DECISIONES.md` | 16 decisiones de diseño con alternativas y motivo |
| `docs/CONSULTAS.md` | Los 6 pipelines: pregunta de negocio, operadores y salida real |
| `docs/CRUD.md` | Mapa colección × operación, con el porqué de cada tipo de delete |
| `docs/INDICES.md` | Los 11 índices y la evidencia `explain()` antes/después |
| `docs/MEJORAS.md` | Todo lo descartado deliberadamente, con su justificación |
