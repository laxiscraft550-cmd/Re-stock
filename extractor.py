"""Obtiene nombre y precio de una página de producto, de cualquier tienda."""
import html, ipaddress, json, re, socket, threading
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "es-PE,es;q=0.9",
           "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"}
MAX_BYTES = 8_000_000


class ErrorTienda(Exception):
    """Mensaje apto para mostrar al usuario."""


class Bloqueado(ErrorTienda):
    pass


class NoExiste(ErrorTienda):
    pass


@dataclass
class Producto:
    nombre: str
    precio: float                   # 0 = agotado y la tienda no muestra precio
    lista: float | None = None      # precio "normal" tachado
    tarjeta: float | None = None    # precio con la tarjeta de la tienda
    moneda: str = "PEN"
    stock: bool | None = None
    metodo: str = ""


def limpiar_url(u):
    p = urlsplit(u.strip())
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if not re.match(r"(utm_|gclid|fbclid|gad_|srsltid|mc_|_ga)", k)]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, urlencode(q), ""))


def validar_url(u):
    """Impide que un link haga al bot consultar tu red local."""
    p = urlsplit(u)
    if p.scheme not in ("http", "https") or not p.hostname or p.username:
        raise ErrorTienda("El link no es válido.")
    try:
        ips = {i[4][0] for i in socket.getaddrinfo(p.hostname, None)}
    except (socket.gaierror, UnicodeError):
        raise ErrorTienda("No encuentro esa página (revisa el link o tu internet).")
    if not all(ipaddress.ip_address(i.split("%")[0]).is_global for i in ips):
        raise ErrorTienda("Ese link apunta a una red privada.")


def descargar(u, saltos=6):
    for _ in range(saltos):
        validar_url(u)
        try:
            with requests.get(u, headers=HEADERS, timeout=25, allow_redirects=False, stream=True) as r:
                if r.is_redirect:
                    u = urljoin(u, r.headers["Location"])
                    continue
                if r.status_code in (404, 410):
                    raise NoExiste("La página del producto ya no existe (404).")
                if r.status_code in (401, 403, 429):
                    raise Bloqueado(f"La tienda rechazó la consulta ({r.status_code}).")
                if r.status_code >= 400:
                    raise ErrorTienda(f"La tienda respondió con error {r.status_code}.")
                data = bytearray()
                for c in r.iter_content(65536):
                    data += c
                    if len(data) > MAX_BYTES:
                        raise ErrorTienda("La página es demasiado grande.")
                m = re.search(rb"charset=[\"']?([\w-]+)", data[:3000], re.I)
                h = re.search(r"charset=([\w-]+)", r.headers.get("Content-Type", ""), re.I)
                enc = h[1] if h else m[1].decode() if m else "utf-8"
        except requests.RequestException as e:
            raise ErrorTienda(f"No pude conectar con la tienda ({type(e).__name__}).")
        try:
            return u, data.decode(enc, "replace")
        except LookupError:
            return u, data.decode("utf-8", "replace")
    raise ErrorTienda("El link redirige demasiadas veces.")


_chrome = threading.Lock()


def descargar_con_chrome(u):
    """Respaldo para páginas que arman el precio con JavaScript. Usa el Chrome instalado."""
    validar_url(u)
    try:
        from playwright.sync_api import sync_playwright, Error
    except ImportError:
        raise ErrorTienda("Falta instalar playwright.")

    def filtro(route):
        try:
            if route.request.resource_type in ("image", "media", "font"):
                return route.abort()
            if urlsplit(route.request.url).scheme in ("http", "https"):
                validar_url(route.request.url)
            route.continue_()
        except ErrorTienda:
            route.abort()

    with _chrome, sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Error:
            raise ErrorTienda("No pude abrir Chrome.")
        try:
            pg = b.new_page(locale="es-PE", service_workers="block")
            pg.route("**/*", filtro)
            r = pg.goto(u, wait_until="domcontentloaded", timeout=40000)
            pg.wait_for_timeout(6000)
            if r and r.status in (404, 410):
                raise NoExiste("La página del producto ya no existe (404).")
            if r and r.status in (401, 403, 429):
                raise Bloqueado(f"La tienda rechazó la consulta ({r.status}).")
            return pg.url, pg.content()
        except Error:
            raise ErrorTienda("La página no cargó en Chrome.")
        finally:
            b.close()


# ---------- utilidades ----------
def numero(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if v > 0 else None
    m = re.search(r"\d[\d.,]*", str(v))
    if not m:
        return None
    s = m[0].rstrip(".,")
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", s) else s.replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        x = float(s)
    except ValueError:
        return None
    return x if 0 < x < 10_000_000 else None


def nodos(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from nodos(v)
    elif isinstance(o, list):
        for v in o:
            yield from nodos(v)


def next_data(s):
    t = s.find("script", id="__NEXT_DATA__")
    try:
        return json.loads(t.string) if t and t.string else None
    except ValueError:
        return None


def meta(s, *nombres):
    for n in nombres:
        for a in ("property", "name", "itemprop"):
            t = s.find("meta", attrs={a: n})
            if t and t.get("content"):
                return html.unescape(t["content"]).strip()


def titulo(s):
    h = s.find("h1")
    return (meta(s, "og:title") or (h.get_text(" ", strip=True) if h else "")
            or (s.title.get_text(strip=True) if s.title else "") or "Producto")


# ---------- extractores por plataforma ----------
def falabella(u, s):
    d = next_data(s)
    try:
        p = d["props"]["pageProps"]["productData"]
        vs = p["variants"]
    except (TypeError, KeyError):
        return None
    ids = [x for x in urlsplit(u).path.split("/") if x.isdigit()]
    pedido = ids[-1] if ids else None
    v = (next((x for x in vs if str(x.get("id")) == pedido), None)
         or next((x for x in vs if x.get("isPurchaseable")), None)   # link sin variante: cualquiera disponible
         or next((x for x in vs if str(x.get("id")) == str(p.get("currentVariant"))), None)
         or (vs[0] if vs else None))
    if not v:
        return None
    normal, publico, tarjeta = [], [], []
    for x in v.get("prices") or []:
        raw = x.get("price")
        n = numero(raw[0] if isinstance(raw, list) and raw else raw)
        t = str(x.get("type", "")).lower()
        if n:
            (normal if "normal" in t else tarjeta if "cmr" in t else publico).append(n)
    # Las variantes agotadas no traen isPurchaseable.
    hay = any("isPurchaseable" in x for x in vs)
    if p.get("isOutOfStock"):
        stock = False
    else:
        stock = bool(v.get("isPurchaseable")) if hay else None
    precio = min(publico or normal or [0])
    return Producto(p.get("name") or titulo(s), precio, max(normal) if normal else None,
                    min(tarjeta) if tarjeta else None, stock=stock,
                    metodo="Falabella/Sodimac/Tottus")


def ripley(u, s):
    d = next_data(s)
    try:
        p = d["props"]["pageProps"]["detailProps"]["data"]["product"]
        pr = p["parentpricestock"]["price"]
    except (TypeError, KeyError):
        return None
    v = lambda k: numero((pr.get(k) or {}).get("valueNumber"))
    st = p["parentpricestock"].get("stock")
    return Producto(p.get("name") or titulo(s), v("sale") or v("master") or 0, v("master"), v("ripley"),
                    stock=st if isinstance(st, bool) else None, metodo="Ripley")


def juntoz(u, s):
    m = re.search(r'\\"price\\":([\d.]+),\\"specialPrice\\":([\d.]+|null),'
                  r'\\"(?:hasSpecialPrice\\":(true|false)|stock)', str(s))
    if not m:
        return None
    lista, esp = numero(m[1]), numero(m[2])
    usa = esp and m[3] != "false"
    st = re.search(r'\\"specialPrice\\":[^,]+,\\"stock\\":(\d+)', str(s))
    return Producto(titulo(s), (esp if usa else lista) or 0, lista,
                    stock=int(st[1]) > 0 if st else None, metodo="Juntoz")


def vtex(u):
    """Plaza Vea, Oechsle, Promart, Coolbox, Wong, Metro y más: API pública del catálogo."""
    p = urlsplit(u)
    m = re.fullmatch(r"/([^/]+)/p/?", p.path)
    if not m:
        return None
    _, t = descargar(f"{p.scheme}://{p.netloc}/api/catalog_system/pub/products/search/{m[1]}/p")
    try:
        prod = json.loads(t)[0]
        items = prod["items"]
    except (ValueError, KeyError, IndexError, TypeError):
        return None
    q = dict(parse_qsl(p.query))
    sku = q.get("skuId") or q.get("idsku")
    if sku:
        items = [i for i in items if i.get("itemId") == sku] or items
    ofertas = [x["commertialOffer"] for i in items for x in i.get("sellers", []) if x.get("commertialOffer")]
    con = [o for o in ofertas if o.get("AvailableQuantity", 0) > 0 and numero(o.get("Price"))]
    val = con or [o for o in ofertas if numero(o.get("Price"))]
    if not val:
        # Agotado: VTEX publica precio 0.
        return Producto(prod.get("productName", "Producto"), 0, stock=False, metodo="VTEX") if ofertas else None
    o = min(val, key=lambda x: x["Price"])
    return Producto(prod.get("productName", "Producto"), float(o["Price"]), numero(o.get("ListPrice")),
                    stock=bool(con), metodo="VTEX")


def precio_tachado(s, precio):
    t = s.select_one('[data-price-type="oldPrice"][data-price-amount]')
    cand = [numero(t["data-price-amount"])] if t else []
    cand += [numero(meta(s, k)) for k in ("product:original_price:amount", "og:price:standard_amount")]
    return next((c for c in cand if c and c > precio), None)


def jsonld(u, s):
    prod = None
    for t in s.find_all("script", type=re.compile("ld\\+json")):
        try:
            d = json.loads(t.string or "", strict=False)
        except ValueError:
            continue
        for n in nodos(d):
            tipo = n.get("@type")
            if "Product" in (tipo if isinstance(tipo, list) else [tipo]) and n.get("offers"):
                prod = n          # solo el primero: los demás suelen ser "relacionados"
                break
        if prod:
            break
    if not prod:
        return None
    precios, lista, mon, stock = [], None, "PEN", None
    for o in nodos(prod["offers"]):
        v = numero(o.get("price") or o.get("lowPrice"))
        if v and any(x in str(o.get("priceType", "")) for x in ("ListPrice", "Strikethrough")):
            lista = v
        elif v:
            precios.append(v)
        mon = o.get("priceCurrency") or mon
        if o.get("availability") and stock is not True:
            stock = not re.search(r"OutOfStock|SoldOut|Discontinued", str(o["availability"]), re.I)
    if precios or stock is False:
        p = min(precios or [0])
        return Producto(str(prod.get("name") or titulo(s)), p, lista or (precio_tachado(s, p) if p else None),
                        moneda=mon, stock=stock, metodo="datos estructurados")


def microdatos(u, s):
    for t in s.select('[itemprop="price"]'):
        v = numero(t.get("content") or t.get_text())
        if v:
            return Producto(titulo(s), v, numero(meta(s, "product:price:amount")),
                            moneda=meta(s, "priceCurrency") or "PEN", metodo="microdatos")


def metas(u, s):
    v = numero(meta(s, "product:sale_price:amount", "product:price:amount", "og:price:amount"))
    return v and Producto(titulo(s), v, precio_tachado(s, v),
                          moneda=meta(s, "product:price:currency", "og:price:currency") or "PEN",
                          metodo="metaetiquetas")


def magento(u, s):
    """Solo el precio principal de la ficha, nunca el de productos relacionados."""
    t = s.select_one('.product-info-main [data-price-type="finalPrice"][data-price-amount]')
    v = t and numero(t["data-price-amount"])
    return v and Producto(titulo(s), v, precio_tachado(s, v), metodo="Magento")


def visual(u, s):
    """Último recurso: primer precio visible después del título."""
    h = s.find("h1")
    if not h:
        return None
    for t in h.find_all_next(string=re.compile(r"S/\.?\s*\d"), limit=8):
        if t.find_parent(["script", "style", "del", "s"]):
            continue
        clases = " ".join(" ".join(a.get("class") or []) for a in list(t.parents)[:4]).lower()
        if re.search(r"old|regular|before|antes|list-price|tachad|relat|carousel", clases):
            continue
        m = re.search(r"S/\.?\s*([\d.,]+)", t)
        v = m and numero(m[1])
        if v:
            return Producto(titulo(s), v, metodo="lectura visual (verifica que sea correcto)")


def stock_visual(s):
    """Solo afirma algo si la página es inequívoca; ante la duda, None."""
    h = s.find("h1")
    if not h:
        return None

    def visibles(pat, desde):
        for t in desde.find_all_next(string=re.compile(pat, re.I)):
            if t.find_parent(["script", "style", "template", "noscript", "option"]):
                continue
            if not any("display:none" in (a.get("style") or "").replace(" ", "") or a.has_attr("hidden")
                       for a in list(t.parents)[:6]):
                yield t

    compra = list(visibles(r"^\s*((agregar|añadir) al carr|agregar a la bolsa|añadir a la cesta|comprar ahora)", h))
    agotado = list(visibles(r"^\s*(producto )?(agotado|sin stock)\b", h))
    # Nunca devuelve False: muchas páginas traen "Agotado" oculto o de otro producto.
    if compra and not agotado and not compra[0].find_parent("button", disabled=True):
        return True
    return None


def normalizar(r):
    r.nombre = re.sub(r"\s+", " ", html.unescape(r.nombre)).strip()[:150]
    if not r.precio:
        if r.stock is not False:
            return None
        r.lista = r.tarjeta = None
    if r.lista and r.lista <= r.precio:
        r.lista = None
    if r.tarjeta and r.tarjeta >= r.precio:
        r.tarjeta = None
    return r


def analizar(u, texto):
    s = BeautifulSoup(texto, "html.parser")
    host, ruta = urlsplit(u).hostname or "", urlsplit(u).path
    t = (s.title.get_text() if s.title else "").lower()
    if "account-verification" in ruta or re.search(
            r"just a moment|access denied|captcha|attention required|verifica que eres", t):
        raise Bloqueado("La tienda pide una verificación anti-bots.")
    prop = {"falabella.com": falabella, "sodimac.com": falabella, "tottus.com": falabella,
            "ripley.com": ripley, "juntoz.com": juntoz}
    for f in [f for k, f in prop.items() if k in host] + [jsonld, magento, microdatos, metas, visual]:
        try:
            r = f(u, s)
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        r = r and normalizar(r)
        if r:
            if r.stock is None:         # primero el dato oficial de la página; lo visual es lo último
                d = f is not jsonld and jsonld(u, s)
                r.stock = d.stock if d and d.stock is not None else stock_visual(s)
            return r
    return None


def obtener(u):
    """Devuelve (url_final, Producto). Si la tienda bloquea, no se insiste."""
    def api(x):
        try:
            r = vtex(x)
        except ErrorTienda:
            r = None
        return r and normalizar(r)

    r = api(u)                      # VTEX: una sola consulta ligera
    if r:
        return u, r
    final, texto = descargar(u)
    r = (api(final) if final != u else None) or analizar(final, texto)
    if r:
        return final, r
    final, texto = descargar_con_chrome(u)
    r = analizar(final, texto)
    if not r:
        raise ErrorTienda("No encontré un precio en esa página. ¿Es el link de un producto?")
    return final, r


if __name__ == "__main__":
    import sys
    for x in sys.argv[1:]:
        try:
            print(obtener(x)[1])
        except ErrorTienda as e:
            print("ERROR", x[:70], "->", e)
