/* Tablero 2D: drag & drop + detalle + administración desde la UI.
 *
 * El cliente NO decide nada de negocio: manda la intención a la API y el
 * backend aplica la guarda WIP (D-11), el orden fraccionario (D-05), el cambio
 * de sprint (D-16), los permisos (D-07/D-17) y los eventos (D-04). Si el
 * backend rechaza (409 WIP, 403 permisos), la UI revierte y muestra el motivo.
 * Variables que inyecta la plantilla: PROYECTO_ID, SPRINT_ID, SPRINT_NOMBRE,
 * MIEMBROS. Helpers globales de base.html: abrirModal, cerrarModal, toast,
 * esc, llamarApi, selUsuario.
 */

// --- membresía (D-18): quien no es del equipo solo observa ---------------------

function esMiembro() {
  return MIEMBROS.some(m => m.id === selUsuario.value);
}

const sortables = [];

function aplicarMembresia() {
  const miembro = esMiembro();
  document.body.classList.toggle("observador", !miembro);
  sortables.forEach(s => s.option("disabled", !miembro));  // sin drag para observadores
}
selUsuario.addEventListener("change", aplicarMembresia);

// --- drag & drop -------------------------------------------------------------

document.querySelectorAll(".celda").forEach(celda => {
  sortables.push(new Sortable(celda, {
    group: "tarjetas",
    animation: 150,
    draggable: ".tarjeta",
    ghostClass: "fantasma",
    forceFallback: true,       // sin DnD nativo: mismo aspecto en todo navegador
    filter: ".no-drag",        // el botón ⋯ y el enlace del nodo no inician arrastre
    preventOnFilter: false,
    onEnd: alSoltar,
  }));
});
aplicarMembresia();

async function alSoltar(evt) {
  if (evt.to === evt.from && evt.newIndex === evt.oldIndex) return; // no se movió

  const tarjeta = evt.item;
  // Los vecinos entre los que cayó: el backend calcula el punto medio (D-05)
  const vecinos = [...evt.to.querySelectorAll(".tarjeta")];
  const i = vecinos.indexOf(tarjeta);

  const respuesta = await fetch(`/tarjetas/${tarjeta.dataset.id}/mover`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      columna: evt.to.dataset.columna,
      asignadoA: evt.to.dataset.fila,          // "sin-asignar" quita el responsable
      vecinoAnteriorId: i > 0 ? vecinos[i - 1].dataset.id : null,
      vecinoSiguienteId: i < vecinos.length - 1 ? vecinos[i + 1].dataset.id : null,
      usuarioId: selUsuario.value,
    }),
  });

  if (!respuesta.ok) {
    // Revertir: la tarjeta vuelve exactamente a donde estaba. Se excluye a sí
    // misma de la lista: en un movimiento dentro de la misma celda todavía
    // figura en ella y correría el índice un lugar.
    const hermanos = [...evt.from.querySelectorAll(".tarjeta")].filter(t => t !== tarjeta);
    evt.from.insertBefore(tarjeta, hermanos[evt.oldIndex] || null);
    const error = await respuesta.json().catch(() => ({}));
    toast(error.detail || "No se pudo mover la tarjeta", true);
    return;
  }
  actualizarWip();
}

async function actualizarWip() {
  // El contador vive en el documento del proyecto (D-11): se relee de ahí
  const proyecto = await (await fetch(`/proyectos/${PROYECTO_ID}`)).json();
  for (const col of proyecto.columnas) {
    const pill = document.getElementById(`wip-${col.clave}`);
    if (!pill || !col.limiteWip) continue;
    pill.textContent = `${col.wip}/${col.limiteWip}`;
    pill.classList.toggle("lleno", col.wip >= col.limiteWip);
  }
}

// --- administración del tablero ------------------------------------------------

function opciones(lista, seleccionado) {
  return lista.map(o =>
    `<option value="${esc(o.valor)}" ${o.valor === seleccionado ? "selected" : ""}>${esc(o.texto)}</option>`
  ).join("");
}

const TIPOS_TRABAJO = ["historia", "bug", "tarea", "spike"]
  .map(t => ({ valor: t, texto: t }));
const PUNTOS_FIB = [{ valor: "", texto: "sin estimar" },
  ...[1, 2, 3, 5, 8, 13, 21].map(n => ({ valor: String(n), texto: `${n} pts` }))];
const OPCIONES_MIEMBROS = [{ valor: "", texto: "— sin responsable —" },
  ...MIEMBROS.map(m => ({ valor: m.id, texto: m.nombre }))];

function abrirNuevaTarjeta() {
  const destinos = [{ valor: "", texto: "Backlog (fuera del sprint)" }];
  if (SPRINT_ID) destinos.unshift({ valor: SPRINT_ID, texto: `${SPRINT_NOMBRE} (sprint activo)` });
  abrirModal(`
    <header class="modal-cabecera"><h2>Nueva tarjeta</h2>
      <button class="btn-mini" onclick="cerrarModal()">✕</button></header>
    <div class="modal-cuerpo">
      <form class="form-daily" onsubmit="return crearTarjeta(event)">
        <label>Título<input name="titulo" required maxlength="120"></label>
        <label>Descripción<textarea name="descripcion" rows="2"></textarea></label>
        <label>Tipo<select name="tipo">${opciones(TIPOS_TRABAJO, "historia")}</select></label>
        <label>Estimación<select name="puntos">${opciones(PUNTOS_FIB, "")}</select></label>
        <label>Responsable<select name="asignadoA">${opciones(OPCIONES_MIEMBROS, "")}</select></label>
        <label>Entra a<select name="sprintId">${opciones(destinos, "")}</select></label>
        <button class="btn">Crear tarjeta</button>
      </form>
    </div>`);
}

async function crearTarjeta(evento) {
  evento.preventDefault();
  const f = evento.target;
  const creada = await llamarApi("/tarjetas", "POST", {
    titulo: f.titulo.value, descripcion: f.descripcion.value,
    tipo: f.tipo.value,
    puntos: f.puntos.value ? Number(f.puntos.value) : null,
    asignadoA: f.asignadoA.value || null,
    sprintId: f.sprintId.value || null,
    proyectoId: PROYECTO_ID,
  });
  if (creada) location.reload();
  return false;
}

function abrirNuevoSprint() {
  abrirModal(`
    <header class="modal-cabecera"><h2>Nuevo sprint</h2>
      <button class="btn-mini" onclick="cerrarModal()">✕</button></header>
    <div class="modal-cuerpo">
      <form class="form-daily" onsubmit="return crearSprint(event)">
        <label>Nombre<input name="nombre" required placeholder="Sprint 5"></label>
        <label>Objetivo<input name="objetivo" placeholder="¿Qué queremos lograr esta semana?"></label>
        <label>Inicio (lunes)<input type="date" name="inicio" required></label>
        <label>Fin (viernes)<input type="date" name="fin" required></label>
        <label class="etiqueta-inline"><input type="checkbox" name="activar" checked>
          Activarlo ya (cierra el sprint activo actual)</label>
        <button class="btn">Crear sprint</button>
      </form>
    </div>`);
}

async function crearSprint(evento) {
  evento.preventDefault();
  const f = evento.target;
  // horario laboral de la organización: 9:00 y 18:00 de Lima (UTC-5)
  const creado = await llamarApi("/sprints", "POST", {
    proyectoId: PROYECTO_ID,
    nombre: f.nombre.value, objetivo: f.objetivo.value,
    fechaInicio: f.inicio.value + "T14:00:00Z",
    fechaFin: f.fin.value + "T23:00:00Z",
    estado: f.activar.checked ? "activo" : "planificacion",
  });
  if (creado) location.reload();
  return false;
}

async function editarLimiteWip(pill) {
  if (!document.body.classList.contains("modo-moderador")) return;
  const actual = pill.dataset.limite;
  const nuevo = prompt(`Límite de tarjetas en curso para esta columna\n` +
                       `(actual: ${actual || "sin límite"}; vacío = sin límite)`, actual);
  if (nuevo === null) return;
  const limite = nuevo.trim() === "" ? null : Number(nuevo);
  if (limite !== null && (!Number.isInteger(limite) || limite < 1))
    return toast("El límite debe ser un entero ≥ 1 (o vacío para quitarlo)", true);
  const r = await llamarApi(`/proyectos/${PROYECTO_ID}`, "PATCH",
                            { limitesWip: { [pill.dataset.clave]: limite } });
  if (r) location.reload();
}

// --- modal de detalle ----------------------------------------------------------

document.addEventListener("click", e => {
  const boton = e.target.closest(".btn-detalle");
  if (boton) abrirDetalle(boton.closest(".tarjeta").dataset.id);
});

function fecha(iso) {
  // La API entrega UTC (ISO 8601); el navegador la muestra en hora local
  if (!iso) return "";
  return new Date(iso.endsWith("Z") ? iso : iso + "Z")
    .toLocaleString("es-PE", { dateStyle: "short", timeStyle: "short" });
}

const ETIQUETA_EVENTO = {
  creacion: "creada", movimiento: "movida", reasignacion: "reasignada",
  cambio_sprint: "cambio de sprint", bloqueo: "bloqueada",
  desbloqueo: "desbloqueada", edicion: "editada", archivado: "archivada",
};

let NOMBRES_USUARIOS = null;  // id → nombre, para atribuir el historial del modal

async function abrirDetalle(id) {
  if (!NOMBRES_USUARIOS) {
    const us = await (await fetch("/usuarios?incluirInactivos=true")).json();
    NOMBRES_USUARIOS = Object.fromEntries(us.map(u => [u._id, u.nombre]));
  }
  const [t, eventos] = await Promise.all([
    (await fetch(`/tarjetas/${id}`)).json(),
    (await fetch(`/eventos/tarjeta/${id}`)).json(),
  ]);
  const miembro = esMiembro();  // los observadores ven el detalle en solo lectura

  const comentarios = (t.comentarios || []).map(c => `
    <li>
      <div><strong>${esc(c.nombre)}</strong> <span class="fecha">${fecha(c.fecha)}</span></div>
      <p>${esc(c.texto)}</p>
      ${miembro ? `<button class="btn-mini" onclick="eliminarComentario('${t._id}', '${c._id}')" title="Eliminar comentario">🗑</button>` : ""}
    </li>`).join("") || "<li class='vacio'>Sin comentarios</li>";

  const checklist = (t.checklist || []).map(c =>
    `<li>${c.hecho ? "☑" : "☐"} ${esc(c.texto)}</li>`).join("");

  // cada acción con su autor: los eventos siempre guardaron quién (D-04)
  const historial = eventos.slice(-8).reverse().map(e => `
    <li><span class="fecha">${fecha(e.timestamp)}</span>
        ${ETIQUETA_EVENTO[e.tipo] || esc(e.tipo)}${e.tipo === "movimiento" ? `: ${esc(e.de)} → ${esc(e.a)}` : ""}
        <span class="actor">· ${esc(NOMBRES_USUARIOS[e.usuarioId] || "—")}</span></li>`).join("");

  const esNodo = t.tipo === "nodo";
  // el tipo se edita aquí: cambiarlo cambia el color de la tarjeta (ver leyenda)
  const selectorTipo = (esNodo || !miembro)
    ? `<span class="tipo">${esc(t.tipo)}</span>`
    : `<select class="sel-tipo" onchange="cambiarTipo('${t._id}', this.value)"
         title="Cambiar el tipo (cambia el color)">${opciones(TIPOS_TRABAJO, t.tipo)}</select>`;

  const bloqueoHtml = t.bloqueado?.estado
    ? `<div class="aviso-bloqueo">⛔ Bloqueada: ${esc(t.bloqueado.motivo)}
        ${miembro ? `<button class="btn" onclick="desbloquear('${t._id}')">Desbloquear</button>` : ""}
      </div>`
    : (miembro ? `<button class="btn btn-suave" onclick="bloquear('${t._id}')">⛔ Bloquear…</button>` : "");

  const acciones = !miembro ? "" : (esNodo
    ? `<button class="btn btn-suave" onclick="abrirSubtarea('${t._id}', '${t.sprintId || ""}')">＋ Añadir subtarea</button>`
    : `<button class="btn btn-suave" onclick="abrirDividir('${t._id}', '${t.asignadoA || ""}')"
         title="La convierte en un nodo que agrupa subtareas">✂ Dividir en subtareas…</button>`);

  abrirModal(`
    <header class="modal-cabecera t-${esc(t.tipo)}">
      <h2>${esc(t.titulo)}</h2>
      <button class="btn-mini" onclick="cerrarModal()">✕</button>
    </header>
    <div class="modal-cuerpo">
      <p class="meta">
        ${selectorTipo}
        ${t.puntos ? `<span class="puntos">${t.puntos} pts</span>` : ""}
        <span>${esc(t.asignadoNombre || "sin asignar")}</span>
      </p>
      ${bloqueoHtml}
      ${acciones}
      ${t.descripcion ? `<p class="descripcion">${esc(t.descripcion)}</p>` : ""}
      ${checklist ? `<h3>Checklist</h3><ul class="checklist">${checklist}</ul>` : ""}
      <h3>Comentarios</h3>
      <ul class="comentarios">${comentarios}</ul>
      ${miembro ? `
      <form class="form-comentario" onsubmit="return comentar(event, '${t._id}')">
        <input name="texto" placeholder="Escribe un comentario…" required>
        <button class="btn">Comentar</button>
      </form>` : ""}
      <h3>Historial</h3>
      <ul class="historial">${historial}</ul>
      ${miembro ? `
      <footer class="modal-pie">
        <button class="btn btn-peligro" onclick="archivar('${t._id}')">Archivar tarjeta</button>
      </footer>` : ""}
    </div>`);
}

async function cambiarTipo(id, tipo) {
  if (await llamarApi(`/tarjetas/${id}`, "PATCH", { tipo })) location.reload();
}

// --- dividir en subtareas (la regla ">13 pts se parte", D-06, con el mouse) ----

function abrirDividir(id, asignadoA) {
  abrirModal(`
    <header class="modal-cabecera t-nodo"><h2>Dividir en subtareas</h2>
      <button class="btn-mini" onclick="cerrarModal()">✕</button></header>
    <div class="modal-cuerpo">
      <p class="descripcion">La tarjeta se convierte en un <strong>nodo</strong>: deja de
      puntuar ella misma y pasa a agrupar subtareas (su avance será el de ellas).
      Elige quién lidera la rama.</p>
      <form class="form-daily" onsubmit="return dividir(event, '${id}')">
        <label>Líder de la rama
          <select name="liderId" required>${opciones(MIEMBROS.map(m => ({ valor: m.id, texto: m.nombre })), asignadoA)}</select>
        </label>
        <button class="btn">Convertir en nodo</button>
      </form>
    </div>`);
}

async function dividir(evento, id) {
  evento.preventDefault();
  const r = await llamarApi(`/tarjetas/${id}`, "PATCH",
    { tipo: "nodo", liderId: evento.target.liderId.value, puntos: null });
  if (r) abrirSubtarea(id, r.sprintId || "");   // sigue: crear la primera subtarea
  return false;
}

function abrirSubtarea(padreId, sprintId) {
  abrirModal(`
    <header class="modal-cabecera t-nodo"><h2>Nueva subtarea</h2>
      <button class="btn-mini" onclick="cerrarModal()">✕</button></header>
    <div class="modal-cuerpo">
      <form class="form-daily" onsubmit="return crearSubtarea(event, '${padreId}', '${sprintId}')">
        <label>Título<input name="titulo" required maxlength="120"></label>
        <label>Tipo<select name="tipo">${opciones(TIPOS_TRABAJO, "historia")}</select></label>
        <label>Estimación<select name="puntos">${opciones(PUNTOS_FIB, "")}</select></label>
        <label>Responsable<select name="asignadoA">${opciones(OPCIONES_MIEMBROS, "")}</select></label>
        <button class="btn">Crear subtarea</button>
        <button class="btn btn-suave" type="button" onclick="location.reload()">Terminar</button>
      </form>
    </div>`);
}

async function crearSubtarea(evento, padreId, sprintId) {
  evento.preventDefault();
  const f = evento.target;
  const creada = await llamarApi("/tarjetas", "POST", {
    titulo: f.titulo.value, tipo: f.tipo.value,
    puntos: f.puntos.value ? Number(f.puntos.value) : null,
    asignadoA: f.asignadoA.value || null,
    proyectoId: PROYECTO_ID, padreId,
    sprintId: sprintId || null,
  });
  if (creada) {
    toast(`Subtarea «${f.titulo.value}» creada`);
    abrirSubtarea(padreId, sprintId);   // encadenar: se suelen crear varias
  }
  return false;
}

// --- acciones del modal (todas pasan por la API pública) ----------------------

async function accion(url, opciones, recargar = false) {
  const r = await fetch(url, opciones);
  if (!r.ok) {
    const e = await r.json().catch(() => ({}));
    toast(e.detail || "La operación falló", true);
    return false;
  }
  if (recargar) location.reload();
  return true;
}

function cuerpoJson(datos) {
  return { method: "POST", headers: { "Content-Type": "application/json" },
           body: JSON.stringify({ ...datos, usuarioId: selUsuario.value }) };
}

async function bloquear(id) {
  const motivo = prompt("¿Motivo del bloqueo?");
  if (!motivo) return;
  await accion(`/tarjetas/${id}/bloquear`, cuerpoJson({ motivo }), true);
}

async function desbloquear(id) {
  await accion(`/tarjetas/${id}/desbloquear`, cuerpoJson({}), true);
}

async function comentar(evento, id) {
  evento.preventDefault();
  const campo = evento.target.texto;
  if (await accion(`/tarjetas/${id}/comentarios`, cuerpoJson({ texto: campo.value })))
    abrirDetalle(id);   // re-renderiza el modal, sin recargar el tablero
  return false;
}

async function eliminarComentario(id, comentarioId) {
  if (await accion(`/tarjetas/${id}/comentarios/${comentarioId}?usuarioId=${selUsuario.value}`,
                   { method: "DELETE" }))
    abrirDetalle(id);
}

async function archivar(id) {
  if (!confirm("¿Archivar esta tarjeta y todo su subárbol? (se oculta, el historial se conserva)")) return;
  await accion(`/tarjetas/${id}?usuarioId=${selUsuario.value}`, { method: "DELETE" }, true);
}
