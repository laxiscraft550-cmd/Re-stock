"""Decide cuándo un cambio de precio merece un aviso. Sin red ni base de datos."""

VOLVIO = "Volvió el stock"


def evaluar(f, p, pct):
    """f: fila guardada; p: Producto nuevo. Devuelve (motivos, campos a guardar)."""
    if p.stock is False:                      # agotado no es oferta: se conservan las referencias
        return [], {c: f[c] for c in ("ref", "ref_tarjeta", "objetivo_avisado", "minimo")}
    motivos, n = [], {}
    if f["stock"] == 0 and p.stock:
        motivos.append(VOLVIO)
    k = 1 - pct / 100

    def ref(vieja, nuevo, texto):
        if nuevo is None:
            return vieja
        if vieja is None or nuevo > vieja:
            return nuevo                      # subió: nueva referencia
        if nuevo <= vieja * k:
            motivos.append(f"{texto} {round((1 - nuevo / vieja) * 100)}%")
            return nuevo                      # bajó: avisa una sola vez
        return vieja                          # bajadas pequeñas se acumulan

    n["ref"] = ref(f["ref"], p.precio, "Bajó")
    n["ref_tarjeta"] = ref(f["ref_tarjeta"], p.tarjeta, "Con tarjeta de la tienda bajó")
    if f["ref_tarjeta"] is None and p.tarjeta and p.tarjeta <= min(p.precio, f["ref"] or p.precio) * k:
        motivos.append("Nuevo precio con tarjeta de la tienda")
    if p.tarjeta is None:
        n["ref_tarjeta"] = None               # terminó la promo de tarjeta: la próxima vuelve a avisar
    ok = f["objetivo"] is not None and p.precio <= f["objetivo"]
    if ok and not f["objetivo_avisado"]:
        motivos.append("Llegó a tu precio objetivo")
    n["objetivo_avisado"] = int(ok)
    n["minimo"] = min(f["minimo"] or p.precio, p.precio)
    if motivos and f["minimo"] and p.precio < f["minimo"]:
        motivos.append("Es el precio más bajo que he visto")
    return motivos, n
