"""Pruebas sin red ni Telegram: python pruebas.py"""
import bot as B
from datos import Datos
from extractor import ErrorTienda, Producto, numero
assert [numero(x) for x in ("S/ 1,299.90", "1.299,90", "5,559", "1,99", 89.9, None, "x")] == [1299.9, 1299.9, 5559, 1.99, 89.9, None, None]
out = []
b = B.Bot("x", Datos(":memory:"))
b.espera_confirmar = 0
b.tg = lambda m, _t=0, **d: out.append(d.get("text", m))
b.db.guardar("codigo", "abc")
msg = lambda t, c=1: b.mensaje({"text": t, "chat": {"id": c, "type": "private"}})
msg("/start"); msg("/start malo"); assert not b.db.ajuste("dueno")
msg("/start abc"); assert b.db.ajuste("dueno") == "1"
out.clear(); msg("/lista", 2); msg("/start abc", 2); assert not out
def pon(*a, **k):
    B.obtener = lambda u: ("https://t.pe/a", Producto("Té <x>", *a, **k))
pon(100.0); b.agregar("https://t.pe/a?utm_source=z"); assert "Vigilando" in out[-1] and "&lt;x&gt;" in out[-1]
rev = lambda: b.revisar(b.db.producto(1))
assert not rev()
pon(98.0); assert not rev()            # 2%: no avisa
pon(96.0); assert rev() and "4%" in out[-1]      # acumulado 4%
assert not rev()                       # no repite
pon(100.0); assert not rev()
pon(90.0, stock=False); assert not rev()
pon(90.0, stock=True); assert rev() and "stock" in out[-1]
msg("/objetivo 1 89"); pon(89.0, stock=True); assert rev() and "objetivo" in out[-1]
assert not rev()
pon(89.0, tarjeta=70.0); assert rev() and "tarjeta" in out[-1]
ok = b.enviar; b.enviar = lambda *a: False; pon(50.0, tarjeta=70.0); assert not rev()
b.enviar = ok; assert rev()            # si Telegram falla, reintenta
def falla(u): raise ErrorTienda("caída")
B.obtener = falla; out.clear()
for _ in range(7): rev()
assert len(out) == 1
msg("/historial 1"); msg("/lista"); msg("/intervalo 5"); assert b.intervalo() == 10
msg("/objetivo 1 ²"); msg("/borrar 1"); assert not b.db.producto(1)
# stock
pon(0, stock=False); b.agregar("https://t.pe/b"); assert "Agotado" in out[-1] and "desconocido" in out[-1]
rev2 = lambda: b.revisar(b.db.producto(2))
import time
assert b.db.producto(2)["siguiente"] - time.time() < 200
assert not rev2()
pon(500.0, stock=True); b.enviar = lambda *a: False; assert not rev2(); b.enviar = ok
assert rev2() and "HAY STOCK" in out[-1] and "S/ 500.00" in out[-1]
assert not rev2()
assert b.db.producto(2)["siguiente"] - time.time() > 500
pon(0, stock=False); assert not rev2(); assert b.db.producto(2)["precio"] == 500
pon(520.0, stock=True); assert rev2() and "520.00" in out[-1] and "Antes: S/ 500.00" in out[-1]
assert b.ronda(True) == (1, 0)
# sincronización entre dos computadoras (Telegram simulado)
import json as J
from sync import Sync
nube = {}
class S(Sync):
    def fijado(self):
        if not nube: return None
        import re
        from sync import PAT
        r = PAT.search(nube["cap"]); return {"message_id": 1}, r[1], r[2]
    def archivo(self, metodo, d, campo):
        nube.update(cap=d.get("caption") or J.loads(d["media"])["caption"], db=self.db.exportar()); return {"message_id": 1}
    def bajar(self, m): return nube["db"]
def copia():
    x = B.Bot("x", Datos(":memory:")); x.db.guardar("dueno", 1)
    x.tg = lambda m, _t=0, **d: nube.update(cap=d["caption"]) if m == "editMessageCaption" else {}
    return x, S(x, 9)
pc1, s1 = copia(); pc2, s2 = copia()
s1.tomar(0); pon(10.0, stock=True); pc1.agregar("https://t.pe/z"); assert s1.paso()
s2.tomar(0); assert pc2.db.q("SELECT url FROM productos")[0][0] == "https://t.pe/a"
assert not s1.paso() and s2.paso()
pc2.borrar(1); assert s2.paso()
_, s3 = pc1, S(pc1, 9); s3.tomar(0); assert not pc1.db.q("SELECT * FROM productos") and not s2.paso()
pon(11.0, stock=True); pc1.agregar("https://t.pe/y")      # se cerró antes de publicar
s4 = S(pc1, 9); s4.tomar(0); assert pc1.db.q("SELECT * FROM productos")   # no pierde lo local
try: pc1.db.importar(b"basura"); assert 0
except Exception as ex: assert not isinstance(ex, AssertionError)
assert pc1.db.q("SELECT * FROM productos")
print("Todas las pruebas pasaron")
