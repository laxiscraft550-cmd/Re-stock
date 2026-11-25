import sqlite3, threading
from pathlib import Path

RUTA = Path(__file__).with_name("ofertas.db")


class Datos:
    def __init__(self, ruta=RUTA):
        self.l = threading.RLock()
        self.c = sqlite3.connect(ruta, check_same_thread=False)
        self.c.row_factory = sqlite3.Row
        with self.l, self.c:
            self.c.executescript("""
            CREATE TABLE IF NOT EXISTS ajustes(k TEXT PRIMARY KEY, v TEXT);
            CREATE TABLE IF NOT EXISTS productos(
              id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE, nombre TEXT, moneda TEXT,
              precio REAL, lista REAL, tarjeta REAL, stock INTEGER, ref REAL, ref_tarjeta REAL,
              objetivo REAL, objetivo_avisado INTEGER DEFAULT 0, minimo REAL,
              fallos INTEGER DEFAULT 0, error TEXT, revisado REAL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS historial(
              producto INTEGER REFERENCES productos(id), fecha REAL, precio REAL, tarjeta REAL);
            """)

    def q(self, sql, *a):
        with self.l:
            return self.c.execute(sql, a).fetchall()

    def x(self, sql, *a):
        with self.l, self.c:
            return self.c.execute(sql, a).lastrowid

    def ajuste(self, k, defecto=None):
        r = self.q("SELECT v FROM ajustes WHERE k=?", k)
        return r[0][0] if r else defecto

    def guardar(self, k, v):
        self.x("INSERT INTO ajustes VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", k, str(v))

    def producto(self, i):
        r = self.q("SELECT * FROM productos WHERE id=?", i)
        return r[0] if r else None
