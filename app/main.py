"""Punto de entrada de la aplicación FastAPI."""

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from app.db import db
from app.routers import (dailies, eventos, metricas, paginas, proyectos,
                         sprints, tarjetas, usuarios)

app = FastAPI(
    title="Tablero Kanban-Scrum",
    description="Tablero híbrido Scrum-Kanban con MongoDB — Base de Datos II, UTP",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

for router in (usuarios.router, proyectos.router, sprints.router,
               tarjetas.router, eventos.router, dailies.router, metricas.router,
               paginas.router):
    app.include_router(router)


@app.get("/salud")
def salud():
    """Verifica que la app corre y que la base de datos responde al ping."""
    try:
        db.command("ping")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"BD no disponible: {exc}")
    return {"estado": "ok", "bd": "conectada"}
