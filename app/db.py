"""Conexión única a MongoDB Atlas.

Un solo MongoClient por proceso: PyMongo mantiene internamente un pool de
conexiones, así que crear un cliente por petición sería un error de rendimiento.
Todos los módulos importan `db` desde aquí.
"""

import os

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

cliente = MongoClient(os.environ["MONGODB_URI"])
db = cliente[os.environ.get("DB_NAME", "tablero_kanban")]
