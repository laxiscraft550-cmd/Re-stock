"""Bot de Telegram que vigila precios. Ejecutar: python bot.py"""
import html, logging, os, random, re, secrets, socket, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlsplit
import requests
from datos import Datos
from extractor import Bloqueado, ErrorTienda, NoExiste, limpiar_url, obtener
from reglas import VOLVIO, evaluar

AQUI = Path(__file__).parent
log = logging.getLogger("bot")
e = lambda s: html.escape(str(s))
AYUDA = """<b>Cómo usarme</b>
Pégame el link de un producto y lo vigilo.

/lista – lo que vigilo
/revisar – revisar todo ahora
/objetivo 3 199 – avisar cuando el nº 3 llegue a S/ 199
/historial 3 – precios que he visto
/borrar 3 – dejar de vigilar
/intervalo 20 – minutos entre revisiones normales (mínimo 10)
/stock 3 – minutos entre revisiones de lo agotado (mínimo 2)"""


def leer_env():
    f = AQUI / ".env"
    for l in f.read_text("utf-8-sig").splitlines() if f.exists() else []:
        if "=" in l and not l.lstrip().startswith("#"):
            k, v = l.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def dinero(v, moneda="PEN"):
    return f"{'S/' if moneda == 'PEN' else 'US$' if moneda == 'USD' else moneda} {v:,.2f}"


class Bot:
    def __init__(self, token, db=None):
        self.api = f"https://api.telegram.org/bot{token}/"
        self.db = db or Datos()
        self.pct = float(os.environ.get("BAJADA_MINIMA_PORCENTAJE", 3))
        self.pool = ThreadPoolExecutor(2)
        self.ocupado = threading.Lock()
        self.espera_confirmar = 20

    # ---- Telegram ----
    def tg(self, metodo, _t=20, **d):
        # No registrar la excepción original: su texto contiene el token.
        try:
            r = requests.post(self.api + metodo, json=d, timeout=_t).json()
        except (requests.RequestException, ValueError) as ex:
            raise RuntimeError(f"Telegram no disponible ({type(ex).__name__})") from None
        if not r.get("ok"):
            if r.get("error_code") == 429:
                time.sleep(min(r.get("parameters", {}).get("retry_after", 5), 60))
            raise RuntimeError(f"Telegram: {r.get('description')}")
        return r["result"]

    def enviar(self, texto, teclado=None):
        """True si Telegram lo aceptó."""
        d = dict(chat_id=int(self.db.ajuste("dueno")), text=texto, parse_mode="HTML",
                 link_preview_options={"is_disabled": True})
        if teclado:
            d["reply_markup"] = {"inline_keyboard": teclado}
        for i in range(3):
            try:
                self.tg("sendMessage", **d)
                return True
            except RuntimeError as ex:
                log.warning("%s", ex)
                time.sleep(2 * (i + 1))
        return False

    # ---- presentación ----
    def ficha(self, f):
        m = f["moneda"]
        t = f"<b>#{f['id']}</b> <a href=\"{e(f['url'])}\">{e(f['nombre'])}</a>"
        t += f"\n💰 <b>{dinero(f['precio'], m)}</b>" if f["precio"] else "\n💰 Precio aún desconocido"
        if f["lista"]:
            t += f"  <s>{dinero(f['lista'], m)}</s> (-{round((1 - f['precio'] / f['lista']) * 100)}%)"
        if f["tarjeta"]:
            t += f"\n💳 Con tarjeta de la tienda: {dinero(f['tarjeta'], m)}"
        if f["objetivo"]:
            t += f"\n🎯 Objetivo: {dinero(f['objetivo'], m)}"
        t += {1: "\n✅ Con stock", 0: "\n🚫 Agotado (te aviso cuando vuelva)"}.get(
            f["stock"], "\n❔ No pude leer el stock: solo vigilo el precio")
        if f["fallos"]:
            t += f"\n⚠️ {e(f['error'])}"
        return t

    # ---- vigilancia ----
    def agregar(self, url):
        url = limpiar_url(url)
        ya = self.db.q("SELECT * FROM productos WHERE url=?", url)
        if ya:
            return self.enviar("Ya lo vigilo:\n\n" + self.ficha(ya[0]))
        try:
            final, p = obtener(url)
        except ErrorTienda as ex:
            return self.enviar(f"❌ {e(ex)}\nNo lo agregué.")
        final = limpiar_url(final)
        ya = self.db.q("SELECT * FROM productos WHERE url=?", final)
        if ya:
            return self.enviar("Ya lo vigilo:\n\n" + self.ficha(ya[0]))
        i = self.db.x("""INSERT INTO productos(url,nombre,moneda,precio,lista,tarjeta,stock,ref,ref_tarjeta,minimo,revisado)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""", final, p.nombre, p.moneda, p.precio, p.lista, p.tarjeta,
            None if p.stock is None else int(p.stock), p.precio or None, p.tarjeta, p.precio or None, time.time())
        self.programar(i)
        if p.precio:
            self.db.x("INSERT INTO historial VALUES(?,?,?,?)", i, time.time(), p.precio, p.tarjeta)
        ya_oferta = "\n\n🔥 La tienda ya lo muestra en oferta." if p.lista else ""
        self.enviar(f"✅ Vigilando\n\n{self.ficha(self.db.producto(i))}{ya_oferta}\n\n<i>Leído por: {e(p.metodo)}. "
                    "Compara el precio con la tienda; si no coincide, bórralo.</i>",
                    [[{"text": "🗑 Borrar", "callback_data": f"del:{i}"}]])

    def revisar(self, f):
        """True si hubo aviso."""
        i = f["id"]
        try:
            _, p = obtener(f["url"])
            if p.precio and f["precio"] and p.moneda != f["moneda"]:
                raise ErrorTienda("Cambió la moneda del precio.")
            motivos, n = evaluar(f, p, self.pct)
            if motivos:   # segunda lectura para descartar errores momentáneos de la tienda
                time.sleep(min(3, self.espera_confirmar) if VOLVIO in motivos else self.espera_confirmar)
                _, p2 = obtener(f["url"])
                if VOLVIO in motivos and p2.stock:
                    p = p2
                elif abs(p2.precio - p.precio) > 0.01 or p2.tarjeta != p.tarjeta or p2.stock != p.stock:
                    raise ErrorTienda("Precio inestable; lo confirmo en la próxima revisión.")
        except Exception as ex:
            if not isinstance(ex, ErrorTienda):
                log.exception("producto %s", i)
            msg = str(ex) if isinstance(ex, ErrorTienda) else "Error inesperado al leer la tienda."
            self.db.x("UPDATE productos SET fallos=fallos+1,error=?,revisado=? WHERE id=?", msg, time.time(), i)
            if isinstance(ex, NoExiste) and f["fallos"]:   # algunas tiendas retiran la página al agotarse
                self.db.x("UPDATE productos SET stock=0 WHERE id=?", i)
            self.programar(i, bloqueado=isinstance(ex, Bloqueado))
            if f["fallos"] + 1 == 5:
                self.enviar(f"⚠️ Llevo 5 intentos sin poder leer esto:\n\n{self.ficha(self.db.producto(i))}")
            return False
        f = self.db.producto(i)
        if not f:
            return False
        motivos, n = evaluar(f, p, self.pct)   # por si cambió el objetivo mientras tanto
        if not p.precio:                       # agotado sin precio: conservar el último conocido
            p.precio, p.lista, p.tarjeta = f["precio"], f["lista"], f["tarjeta"]
        if f["precio"] != p.precio or f["tarjeta"] != p.tarjeta:
            self.db.x("INSERT INTO historial VALUES(?,?,?,?)", i, time.time(), p.precio, p.tarjeta)
        antes = f["precio"]
        self.db.x("""UPDATE productos SET nombre=?,moneda=?,precio=?,lista=?,tarjeta=?,stock=COALESCE(?,stock),
            fallos=0,error=NULL,revisado=? WHERE id=?""", p.nombre, p.moneda, p.precio, p.lista, p.tarjeta,
            None if p.stock is None else int(p.stock), time.time(), i)
        if motivos:
            cab = "📦 <b>¡HAY STOCK!</b> " if VOLVIO in motivos else "🔥 <b>¡OFERTA!</b> "
            t = cab + e(" · ".join(motivos)) + "\n\n" + self.ficha(self.db.producto(i))
            if antes and antes != p.precio:
                t += f"\nAntes: {dinero(antes, f['moneda'])}"
            if not self.enviar(t, [[{"text": "🛒 Ver en la tienda", "url": f["url"]}]]):
                self.db.x("UPDATE productos SET stock=? WHERE id=?", f["stock"], i)
                self.programar(i)
                return False    # las referencias no cambian: se reintenta en la próxima revisión
        self.db.x("UPDATE productos SET ref=?,ref_tarjeta=?,objetivo_avisado=?,minimo=? WHERE id=?",
                  n["ref"], n["ref_tarjeta"], n["objetivo_avisado"], n["minimo"], i)
        self.programar(i)
        return bool(motivos)

    def intervalo(self):
        return max(10, int(self.db.ajuste("intervalo") or os.environ.get("INTERVALO_MINUTOS", 20)))

    def intervalo_stock(self):
        return max(2, int(self.db.ajuste("intervalo_stock") or os.environ.get("INTERVALO_AGOTADOS", 3)))

    def programar(self, i, bloqueado=False):
        """Lo agotado se revisa más seguido; si la tienda bloquea, se espera cada vez más."""
        f = self.db.producto(i)
        if f:
            m = self.intervalo_stock() if f["stock"] == 0 else self.intervalo()
            if bloqueado:
                m = min(max(m, 15) * 2 ** min(f["fallos"], 4), 240)
            self.db.x("UPDATE productos SET siguiente=? WHERE id=?", time.time() + m * 60 * random.uniform(.9, 1.1), i)

    def ronda(self, todos=False):
        with self.ocupado:
            filas = self.db.q("SELECT id,url FROM productos WHERE siguiente<=? ORDER BY stock IS 0 DESC, siguiente",
                              float("inf") if todos else time.time())
            tiendas = {}
            for f in filas:
                tiendas.setdefault(urlsplit(f["url"]).hostname, []).append(f["id"])

            def tienda(ids):        # tiendas en paralelo; dentro de cada una, de a uno y con pausa
                avisos = 0
                for n, i in enumerate(ids):
                    if n:
                        time.sleep(random.uniform(2, 4))
                    f = self.db.producto(i)
                    if f:
                        try:
                            avisos += self.revisar(f)
                        except Exception:
                            log.exception("revisar %s", i)
                return avisos

            with ThreadPoolExecutor(4) as pool:
                return len(filas), sum(pool.map(tienda, tiendas.values()))

    def vigilar(self):
        while True:
            try:
                if self.db.ajuste("dueno"):
                    self.ronda()
            except Exception:
                log.exception("ronda")
            time.sleep(10)

    # ---- comandos ----
    def revisar_todo(self):
        if self.ocupado.locked():
            return self.enviar("Ya estoy revisando.")
        self.enviar("🔎 Revisando…")
        n, a = self.ronda(True)
        self.enviar(f"Listo: {n} productos, {a} avisos.")

    def mensaje(self, m):
        texto, chat = (m.get("text") or m.get("caption") or "").strip(), m["chat"]
        dueno = self.db.ajuste("dueno")
        if not dueno:
            esperado = f"/start {self.db.ajuste('codigo')}"
            if chat["type"] == "private" and secrets.compare_digest(texto.encode(), esperado.encode()):
                self.db.guardar("dueno", chat["id"])
                self.enviar("👋 Listo, este bot ahora es tuyo.\n\n" + AYUDA)
            return
        if str(chat["id"]) != dueno:
            return
        links = re.findall(r"https?://[^\s<>\"]+", texto)
        for ent in (m.get("entities") or []) + (m.get("caption_entities") or []):
            if ent["type"] == "text_link":
                links.append(ent["url"])
        links = list(dict.fromkeys(links))
        if links:
            self.enviar("⏳ Leyendo…")
            for u in links[:20]:
                self.pool.submit(self.seguro, self.agregar, u)
            return
        cmd, *a = texto.split() or [""]
        cmd = cmd.split("@")[0].lower()
        num = int(a[0].lstrip("#")) if a and re.fullmatch(r"#?\d{1,9}", a[0], re.ASCII) else None
        if cmd == "/lista":
            fs = self.db.q("SELECT * FROM productos ORDER BY id")
            for k in range(0, len(fs), 8):
                self.enviar("\n\n".join(self.ficha(f) for f in fs[k:k + 8]))
            if not fs:
                self.enviar("Aún no vigilo nada. Pégame un link.")
        elif cmd == "/revisar":
            self.pool.submit(self.seguro, self.revisar_todo)
        elif cmd == "/intervalo" and num:
            self.db.guardar("intervalo", min(max(10, num), 1440))
            for f in self.db.q("SELECT id FROM productos"):
                self.programar(f["id"])
            self.enviar(f"Revisaré cada {self.intervalo()} minutos.")
        elif cmd == "/stock" and num:
            self.db.guardar("intervalo_stock", min(max(2, num), 1440))
            for f in self.db.q("SELECT id FROM productos WHERE stock=0"):
                self.programar(f["id"])
            self.enviar(f"Revisaré lo agotado cada {self.intervalo_stock()} minutos.")
        elif cmd in ("/borrar", "/objetivo", "/historial") and num is not None:
            f = self.db.producto(num)
            if not f:
                self.enviar("No existe ese número. Mira /lista")
            elif cmd == "/borrar":
                self.borrar(num)
            elif cmd == "/historial":
                h = self.db.q("SELECT * FROM historial WHERE producto=? ORDER BY fecha DESC LIMIT 15", num)
                self.enviar(self.ficha(f) + "\n\n" + "\n".join(
                    f"{datetime.fromtimestamp(x['fecha']):%d/%m/%y %H:%M}  {dinero(x['precio'], f['moneda'])}" for x in h))
            else:
                try:
                    v = float(a[1].replace(",", ""))
                except (IndexError, ValueError):
                    v = 0
                if not 0 < v < 1e7:
                    return self.enviar("Ejemplo: /objetivo 3 199")
                ya = bool(f["precio"]) and f["precio"] <= v and f["stock"] != 0
                self.db.x("UPDATE productos SET objetivo=?,objetivo_avisado=? WHERE id=?", v, int(ya), num)
                self.enviar(f"🎯 Te aviso cuando llegue a {dinero(v, f['moneda'])}." +
                            (" ¡Ya está en ese precio!" if ya else ""))
        else:
            self.enviar(AYUDA)

    def borrar(self, i):
        self.db.x("DELETE FROM historial WHERE producto=?", i)
        self.db.x("DELETE FROM productos WHERE id=?", i)
        self.enviar(f"🗑 #{i} borrado.")

    def seguro(self, fn, *a):
        try:
            fn(*a)
        except Exception:
            log.exception("tarea")
            self.enviar("❌ Ocurrió un error inesperado.")

    def actualizar(self, u):
        if "message" in u:
            self.mensaje(u["message"])
        elif "callback_query" in u:
            c = u["callback_query"]
            if str(c["from"]["id"]) == self.db.ajuste("dueno"):
                if c.get("data", "").startswith("del:"):
                    self.borrar(int(c["data"][4:]))
                self.tg("answerCallbackQuery", callback_query_id=c["id"])

    def correr(self):
        while True:
            try:
                yo = self.tg("getMe")
                break
            except RuntimeError as ex:
                if "Unauthorized" in str(ex) or "Not Found" in str(ex):
                    sys.exit("El TELEGRAM_TOKEN no es válido.")
                time.sleep(15)          # al encender la PC puede no haber internet aún
        if not self.db.ajuste("dueno"):
            if not self.db.ajuste("codigo"):
                self.db.guardar("codigo", secrets.token_hex(8))
            print(f"Abre este link para hacerte dueño del bot:\nhttps://t.me/{yo['username']}?start={self.db.ajuste('codigo')}")
        print("Bot encendido. Ctrl+C para detener.", flush=True)
        threading.Thread(target=self.vigilar, daemon=True).start()
        off = int(self.db.ajuste("offset", 0))
        while True:
            try:
                us = self.tg("getUpdates", 65, offset=off, timeout=50, allowed_updates=["message", "callback_query"])
            except RuntimeError as ex:
                log.warning("%s", ex)
                if "Conflict" in str(ex):
                    print("OJO: el bot está encendido en otra computadora. Apaga una de las dos.", flush=True)
                time.sleep(5)
                continue
            for u in us:
                off = u["update_id"] + 1
                self.db.guardar("offset", off)
                try:
                    self.actualizar(u)
                except Exception:
                    log.exception("mensaje")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[RotatingFileHandler(AQUI / "bot.log", maxBytes=1_000_000, backupCount=1, encoding="utf-8")])
    leer_env()
    tk = os.environ.get("TELEGRAM_TOKEN")
    if not tk:
        sys.exit("Falta TELEGRAM_TOKEN en el archivo .env")
    candado = socket.socket()
    try:
        candado.bind(("127.0.0.1", 47391))   # evita dos copias a la vez
    except OSError:
        sys.exit("El bot ya está encendido.")
    Bot(tk).correr()
