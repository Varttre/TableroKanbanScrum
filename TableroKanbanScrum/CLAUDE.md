# CLAUDE.md — Constitución del proyecto

> Este archivo se carga automáticamente en cada sesión. Es **estable**: no escribas
> aquí avances ni bitácora. El estado vivo está en `docs/ESTADO.md`.

---

## 1. Qué es esto

**Tablero híbrido Scrum-Kanban con MongoDB.** Trabajo final del curso Base de Datos II.

Aplicación web que digitaliza un tablero de gestión visual para una startup de
desarrollo de software, permitiendo gestión multi-proyecto, trazabilidad histórica
del flujo de tarjetas y generación automática de métricas ágiles.

**Restricción dominante: esto se evalúa como proyecto de base de datos, no de frontend.**
El modelado NoSQL, las operaciones CRUD y las consultas de agregación valen casi toda
la nota. La UI solo tiene que funcionar y ser demostrable.

## 2. Restricciones duras

- **Presupuesto total: 15 horas de trabajo humano.** No es negociable ni ampliable.
- **Un solo desarrollador.** El resto del equipo redacta el informe.
- El desarrollador **debe poder explicar oralmente** el modelo de datos y los pipelines.
  Código que él no pueda defender es código inútil, por elegante que sea.
- Todo el trabajo se hace por sesiones cortas, discontinuas, posiblemente con días
  de separación.

## 3. Stack

- **Backend:** Python 3.11+ / FastAPI / PyMongo (driver crudo, **sin ODM**)
- **BD:** MongoDB Atlas (tier gratuito M0 — es replica set, soporta transacciones y
  change streams si algún día se necesitan)
- **Frontend:** Jinja2 + SortableJS (drag & drop) + Chart.js. Sin npm, sin build step.
- **Validación:** Pydantic en la API, `$jsonSchema` a nivel de colección en Mongo
- **Deploy:** Render o Railway

**Prohibido sin autorización explícita:** ORM/ODM (Mongoose, Beanie, MongoEngine),
React/Vue/Svelte, cualquier cosa que requiera `npm install` o pipeline de build,
autenticación con JWT, Docker.

**Razón de no usar ODM:** los pipelines de agregación deben quedar visibles como
listas de diccionarios idénticas a lo que se escribiría en mongosh. Son el material
del informe y de la sustentación oral.

## 4. Alcance

### Dentro (obligatorio)

- CRUD completo sobre las 6 colecciones
- Tablero 2D: filas = integrantes, columnas = Backlog / To Do / Doing / Done
- Drag & drop con persistencia de orden
- Jerarquía de tarjetas padre-hijo con drill-down (2 niveles en UI, N en el modelo)
- Límite WIP por columna, validado sin condición de carrera
- Registro automático e inmutable de cada movimiento en `eventos`
- Registro de dailies (qué hice / qué haré / qué me bloquea)
- 6 pipelines de agregación (ver §6)
- Dashboard con 2 gráficos
- Script de datos semilla con 3 sprints de historia realista

### Fuera (va a `docs/MEJORAS.md`, no se implementa)

Autenticación real, notificaciones, adjuntos, app móvil, integraciones externas,
i18n, tests automatizados, permisos granulares, CFD, tiempo real vía change streams,
modo TV.

**Cortar bien suma nota:** la rúbrica premia explícitamente "oportunidades de mejora
identificadas". Todo lo descartado se documenta con su justificación.

## 5. Modelo de datos (6 colecciones)

```
usuarios      _id, nombre, email, rol("moderador"|"desarrollador"), activo

proyectos     _id, nombre, cliente, estado, columnas:[{clave,nombre,orden,limiteWip}],
              miembros:[{usuarioId, nombre}]        # columnas embebidas: acotadas,
                                                    # siempre se leen con el proyecto

sprints       _id, proyectoId, nombre, objetivo, fechaInicio, fechaFin,
              estado("planificacion"|"activo"|"cerrado")

tarjetas      _id, titulo, descripcion, tipo("historia"|"bug"|"tarea"|"spike"|"nodo"),
              proyectoId, proyectoNombre, sprintId(null=backlog),
              asignadoA, asignadoNombre, columna, orden(float), puntos(Fibonacci),
              diaPrevisto, bloqueado:{estado,motivo,desde},
              padreId(null=raiz), ancestros:[ObjectId], profundidad, liderId,
              etiquetas:[], checklist:[], comentarios:[],
              createdAt, updatedAt, doneAt

eventos       _id, tarjetaId, tipo, de, a, usuarioId, timestamp, meta
              # APPEND-ONLY. Nunca se actualiza ni se borra.

dailies       _id, sprintId, fecha,
              participaciones:[{usuarioId, hice, hare, bloqueo}]
```

### Decisiones de modelado que hay que respetar

- **Tarjetas en colección propia, NO embebidas en el proyecto.** Razones: límite de
  16 MB por documento, crecimiento no acotado (antipatrón *massive array*), contención
  de escritura si dos personas mueven tarjetas a la vez, y necesidad de consultarlas
  independientemente.
- **`ancestros` es un materialized path.** "Dame todo el subárbol de X" =
  `find({ancestros: X})`, una consulta indexada sin recursión, a cualquier profundidad.
  Trade-off aceptado: mover un nodo de padre obliga a reescribir `ancestros` en todos
  sus descendientes; es una operación rara y las lecturas son constantes.
- **`eventos` es el corazón del proyecto.** Sin ella no existen burndown, cycle time
  ni velocity: solo se tendría el estado actual, no la historia. Toda mutación de
  tarjeta escribe su evento.
- **Denormalización deliberada** de `proyectoNombre` y `asignadoNombre` en las tarjetas
  para renderizar el tablero sin `$lookup`.
- **Borrado lógico** (`activo: false`) por defecto, para preservar el historial.
  Excepción: eliminar comentarios usa `deleteOne` real, porque la rúbrica exige
  demostrar la D del CRUD.
- **Orden de tarjetas: fraccionario.** Al insertar entre dos vecinos,
  `orden = (anterior + siguiente) / 2`. Una sola escritura en vez de reindexar la
  columna entera. Necesita rutina de rebalanceo cuando el hueco se hace muy pequeño.
  El orden es único **por par (asignadoA, columna)**, porque el tablero es 2D.

## 6. Los 6 pipelines de agregación

Cada uno responde una pregunta real del negocio. Van en `app/queries/`, uno por
archivo, **comentados etapa por etapa** (son material del informe y de la defensa oral).

1. **Velocity por sprint** — `$match`, `$group`, `$setWindowFields` (media móvil)
2. **Burndown del sprint activo** — `$group` por día, `$setWindowFields` (suma acumulada)
3. **Cycle time por tipo de tarjeta** — `$group` con `$min`/`$max` condicional, `$dateDiff`
4. **Carga y WIP por integrante** — `$match`, `$group`, `$lookup`
5. **Árbol de un nodo con progreso agregado** — `$graphLookup` ← el diferenciador técnico
6. **Tarjetas bloqueadas o estancadas** — `$dateDiff`, `$match`

Fechas: guardar todo en UTC, agrupar con `timezone: "America/Lima"` en `$dateToString`.
Si no, el burndown se corre un día.

## 7. Protocolo de trabajo — REGLAS OBLIGATORIAS

### Al inicio de cada sesión

1. Lee `docs/ESTADO.md` **antes de hacer cualquier otra cosa**.
2. Resume en 3 líneas dónde quedamos y cuál es el siguiente bloque.
3. **Pregunta si arrancamos ese bloque o hacemos otra cosa. Espera respuesta.**

### Antes de escribir código

4. Presenta un plan corto del bloque: qué archivos tocas, qué decisiones hay abiertas,
   cuánto estimas. **Espera aprobación explícita.**
5. **Pregunta en vez de asumir.** Si hay ambigüedad en el modelo, en una regla de
   negocio o en un nombre, pregunta. Una suposición equivocada cuesta más que una
   pregunta.

### Cuando hace falta acción humana

6. Si algo requiere que el desarrollador haga algo fuera del repo (crear el cluster
   en Atlas, conseguir una cadena de conexión, instalar algo, abrir una URL),
   **detente, da instrucciones numeradas y exactas, y espera confirmación.**
   No sigas adelante suponiendo que ya está hecho.

### Al escribir código

7. **Explica el porqué, en español, brevemente.** El desarrollador entiende mejor con
   contexto de razonamiento que con sintaxis.
8. **No escribas código que él no pueda explicar.** Ante dos soluciones, prefiere la
   simple sobre la elegante-pero-opaca.
9. Los pipelines se construyen y explican **etapa por etapa**, no de un solo golpe.
10. Nada fuera del alcance de §4. Si se te ocurre algo bueno, anótalo en
    `docs/MEJORAS.md` y sigue.
11. Avisa si un bloque se está pasando de su presupuesto de horas.

### Actualización de documentación — AUTÓNOMA

El humano NO lleva el control del estado del proyecto. Lo llevas tú. Actualiza los
documentos por iniciativa propia cuando ocurra cualquiera de estos disparadores, sin
pedir permiso y sin esperar al final de la sesión:

| Disparador | Qué actualizas |
|---|---|
| Se completa un bloque | ESTADO.md + BITACORA.md + ENTREGA.md |
| Se toma una decisión de diseño | DECISIONES.md (número correlativo, alternativas, motivo) |
| Surge una idea fuera de alcance | MEJORAS.md |
| Aparece un bloqueo o algo pendiente del humano | ESTADO.md |
| ~30 min de trabajo real acumulado | ESTADO.md (avance parcial y horas) |
| El humano anuncia que va a parar | Todo lo anterior |

Menciona en una línea qué actualizaste. Nunca pidas permiso para hacerlo.

Al cerrar cada bloque, haz commit con mensaje descriptivo. Los timestamps de git son
la única fuente real de horas transcurridas: úsalos para corregir tu estimación.

### Pie de estado — OBLIGATORIO en todas tus respuestas

Termina SIEMPRE cada respuesta con esta línea, sin excepción:

📍 Bloque [N] · [avance dentro del bloque] · [horas]h/15h · Siguiente: [acción concreta]

Ejemplo: 📍 Bloque 3 · pipeline 2 de 6 · 6.5h/15h · Siguiente: cycle time por tipo

Es texto, no una escritura a archivo. Si el pie deja de cuadrar con ESTADO.md,
reescribe ESTADO.md.

### Regla de corte

Avisa proactivamente cuando detectes un punto natural de corte (bloque terminado,
contexto cargado): recuérdame ejecutar /cerrar. No lo ejecutes tú por tu cuenta.

## 8. Presupuesto por bloque

| # | Bloque | h |
|---|--------|---|
| 0 | Setup: Atlas, repo, esqueleto FastAPI | 0.75 |
| 1 | Matriz de patrones de acceso → esquema → validaciones $jsonSchema → semilla con árbol | 3.0 |
| 2 | CRUD (routers + Pydantic), demo vía `/docs` | 2.0 |
| 3 | Los 6 pipelines de agregación | 3.0 |
| 4 | Tablero: drag & drop, drill-down, breadcrumb | 3.5 |
| 5 | Dashboard, 2 gráficos | 0.5 |
| 6 | Índices, `explain()`, despliegue | 1.0 |
| 7 | Material para informe y compañeros | 1.25 |

---

**El bloque 1 empieza por la matriz de patrones de acceso, no por el esquema.**
En modelado documental se enumeran primero las consultas y luego se diseñan los
documentos para servirlas con el mínimo de round trips — al revés que en relacional,
donde se normaliza primero. La matriz va en docs/MODELO_DATOS.md con columnas:
consulta | frecuencia | colecciones que toca | índice que la soporta.
Los índices del bloque 6 salen de esta matriz, no se improvisan.

---

**El bloque 7 genera un `README.md` para lectores humanos (no para ti):** qué es el
proyecto, cómo levantarlo en local, arquitectura, estructura de carpetas, cómo correr
la semilla, y la URL desplegada. Es material del criterio 3 de la rúbrica.

---

**Orden crítico: la semilla va ANTES del CRUD.** Con datos poblados desde la hora 3.75
se pueden construir los pipelines en MongoDB Compass, que tiene constructor visual con
vista previa por etapa y exporta a Python. Sin datos, Compass no sirve.

**Regla de rescate:** hora 9 sin drag & drop funcionando → se congela la UI como esté
y se pasa al bloque 5.

## 9. Convenciones

- Nombres de campos y colecciones en **español**, código y comentarios en español.
- Un archivo por pipeline en `app/queries/`.
- Un router por colección en `app/routers/`.
- Ninguna credencial en el repo: `MONGODB_URI` va en `.env`, con `.env.example` versionado.
