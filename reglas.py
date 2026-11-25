"""Decide cuándo un cambio de precio merece un aviso. Sin red ni base de datos."""


def evaluar(f, p, pct):
    """f: fila guardada; p: Producto nuevo. Devuelve (motivos, campos a guardar)."""
    motivos, n = [], {}
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
    if p.stock is False:                      # sin stock no hay oferta: no gastar referencias
        return [], {k2: f[k2] for k2 in ("ref", "ref_tarjeta", "objetivo_avisado", "minimo")}
    n["minimo"] = min(f["minimo"] or p.precio, p.precio)
    if motivos and f["minimo"] and p.precio < f["minimo"]:
        motivos.append("Es el precio más bajo que he visto")
    if f["stock"] == 0 and p.stock:
        motivos.append("Volvió a haber stock")
    return motivos, n
