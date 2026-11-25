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
msg("/historial 1"); msg("/lista"); msg("/intervalo 5"); assert b.intervalo() == 30
msg("/objetivo 1 ²"); msg("/borrar 1"); assert not b.db.producto(1)
print("Todas las pruebas pasaron")
