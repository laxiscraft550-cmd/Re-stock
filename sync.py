"""Comparte los datos entre computadoras mediante un archivo fijado en el chat del bot.

El texto del mensaje fijado dice qué copia tiene el control. Al abrir el bot en otra
computadora, esa toma el control y la anterior se apaga sola.
"""
import hashlib, json, logging, os, re, secrets, socket, time
import requests

log = logging.getLogger("sync")
PAT = re.compile(r"id:([0-9a-f]{12}) ver:([0-9a-f]{12})")
LOCALES = ("offset", "sync_ver")


class Sync:
    def __init__(self, bot, bot_id):
        self.b, self.db, self.bot_id = bot, bot.db, bot_id
        self.id = secrets.token_hex(6)
        self.msg = None
        self.huella_publicada = None
        self.activo = False

    # ---- Telegram ----
    def fijado(self):
        """(mensaje, id con control, versión) del archivo fijado, o None."""
        m = self.b.tg("getChat", chat_id=int(self.db.ajuste("dueno"))).get("pinned_message")
        if not m or m.get("from", {}).get("id") != self.bot_id or "document" not in m:
            return None
        r = PAT.search(m.get("caption") or "")
        return (m, r[1], r[2]) if r else None

    def texto(self, ver):
        return (f"💾 Datos del bot: no borrar ni desfijar.\nEncendido en: {socket.gethostname()}\n"
                f"id:{self.id} ver:{ver}")

    def archivo(self, metodo, datos, campo):
        try:
            r = requests.post(self.b.api + metodo, data=datos, timeout=60,
                              files={campo: ("ofertas-respaldo.db", self.db.exportar())}).json()
        except (requests.RequestException, ValueError) as ex:
            raise RuntimeError(f"Telegram no disponible ({type(ex).__name__})") from None
        if not r.get("ok"):
            raise RuntimeError(f"Telegram: {r.get('description')}")
        return r["result"]

    def bajar(self, m):
        ruta = self.b.tg("getFile", file_id=m["document"]["file_id"])["file_path"]
        try:
            r = requests.get(self.b.api.replace("/bot", "/file/bot", 1) + ruta, timeout=60)
        except requests.RequestException as ex:
            raise RuntimeError(f"No pude bajar los datos ({type(ex).__name__})") from None
        if r.status_code != 200:
            raise RuntimeError(f"No pude bajar los datos ({r.status_code})")
        return r.content

    # ---- datos ----
    def huella(self):
        p = [tuple(f) for f in self.db.q("""SELECT id,url,nombre,moneda,precio,lista,tarjeta,stock,ref,ref_tarjeta,
             objetivo,objetivo_avisado,minimo FROM productos ORDER BY id""")]
        a = [tuple(f) for f in self.db.q("SELECT k,v FROM ajustes ORDER BY k") if f["k"] not in LOCALES]
        return hashlib.sha256(json.dumps([p, a]).encode()).hexdigest()

    def publicar(self):
        ver, chat, h = secrets.token_hex(6), self.db.ajuste("dueno"), self.huella()
        if self.msg:
            media = {"type": "document", "media": "attach://db", "caption": self.texto(ver)}
            self.archivo("editMessageMedia", {"chat_id": chat, "message_id": self.msg, "media": json.dumps(media)}, "db")
        else:
            m = self.archivo("sendDocument", {"chat_id": chat, "caption": self.texto(ver),
                                              "disable_notification": "true"}, "document")
            self.b.tg("pinChatMessage", chat_id=int(chat), message_id=m["message_id"], disable_notification=True)
            self.msg = m["message_id"]
        self.db.guardar("sync_ver", ver)
        self.huella_publicada = h

    # ---- control ----
    def tomar(self, espera=25):
        """Baja lo último, toma el control y espera a que la otra copia se apague."""
        f = self.fijado()
        if not f:
            self.publicar()
        else:
            m, _, ver = f
            self.msg = m["message_id"]
            # 1) reclamar, sin tocar los datos todavía
            m = self.b.tg("editMessageCaption", chat_id=int(self.db.ajuste("dueno")),
                          message_id=self.msg, caption=self.texto(ver))
            time.sleep(espera)
            # 2) si otra computadora publicó desde mi última vez, sus datos mandan
            f = self.fijado() or f
            if f[2] != self.db.ajuste("sync_ver"):
                self.db.importar(self.bajar(f[0]))
            self.db.guardar("sync_ver", f[2])
            self.publicar()
        self.activo = True
        self.b.enviar(f"🟢 Ahora estoy encendido en <b>{socket.gethostname()}</b>.")

    def paso(self):
        """Una comprobación. False si otra computadora tomó el control."""
        f = self.fijado()
        if f and f[1] != self.id:
            return False
        if not f:
            self.msg = None         # lo borraron o fijaron otra cosa: se vuelve a crear
            self.publicar()
        elif self.huella() != self.huella_publicada:
            self.publicar()
        return True

    def vigilar(self):
        while True:
            time.sleep(10)
            try:
                if not self.db.ajuste("dueno"):
                    continue
                if not self.activo:
                    self.tomar(0)
                elif not self.paso():
                    print("\nEl bot se encendió en otra computadora. Este se apagó solo.", flush=True)
                    os._exit(0)
            except RuntimeError as ex:
                log.warning("%s", ex)
            except Exception:
                log.exception("sync")
