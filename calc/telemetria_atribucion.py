"""Atribución temporal de energía por intervalos de alimentación y medidor vigente.

Todas las funciones son puras: reciben datos ya fetcheados, sin acceso a Supabase.
La capa de BD se inyecta como argumento (resolver_fuente) para mantener testabilidad
y desacoplar el cálculo del repositorio.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable


# ── Utilidades internas ───────────────────────────────────────────────────────

def _norm(iso: str) -> str:
    """Normaliza cualquier ISO 8601 (sufijo Z o +HH:MM) a UTC con sufijo +00:00.

    Necesario para comparación lexicográfica segura entre strings provenientes
    del endpoint (formato 'Z') y de Supabase (formato '+00:00').
    """
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()


def _ts(iso: str) -> float:
    """Convierte ISO 8601 a POSIX timestamp (float) para aritmética temporal."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


# ── Funciones públicas ────────────────────────────────────────────────────────

def resolver_caminos(
    activo_id: int,
    desde_iso: str,
    hasta_iso: str,
    resolver_fuente: Callable[[int, str, str], list[dict]],
    _visitados: frozenset[int] | None = None,
) -> list[dict]:
    """Resuelve la cadena ascendente de alimentación del activo en [desde_iso, hasta_iso).

    resolver_fuente: función inyectada con firma (activo_id, desde_iso, hasta_iso) → list[dict].
    Cada elemento retornado por resolver_fuente debe contener:
      fuente_activo_id (int | None), intervalo_desde (str ISO), intervalo_hasta (str ISO).

    Algoritmo:
    - Obtiene los intervalos de alimentación del activo vía resolver_fuente.
    - Para cada intervalo con fuente_activo_id no nulo, resuelve recursivamente la
      cadena del padre restringida a ese sub-intervalo e interseca.
    - Un cambio de alimentación en un ancestro subdivide los intervalos del descendiente
      aunque el descendiente no haya cambiado de padre.
    - La recursión termina cuando resolver_fuente devuelve lista vacía (acometida raíz).
    - Detecta ciclos: si activo_id ya está en la cadena en construcción, corta y marca
      el segmento con completo=False.

    Retorna lista de dicts con claves:
      desde (str ISO UTC +00:00)
      hasta (str ISO UTC +00:00)
      camino (list[int]): ids ascendentes desde el padre inmediato hasta la acometida inclusive.
      completo (bool): False si hay hueco de vigencia o ciclo detectado.

    Invariante: los segmentos cubren [desde_iso, hasta_iso) sin solapes ni huecos,
    ordenados por desde.
    """
    if _visitados is None:
        _visitados = frozenset()

    desde_n = _norm(desde_iso)
    hasta_n = _norm(hasta_iso)

    if activo_id in _visitados:
        # Ciclo detectado en la cadena ascendente
        return [{"desde": desde_n, "hasta": hasta_n, "camino": [], "completo": False}]

    _vis = _visitados | {activo_id}
    intervalos = resolver_fuente(activo_id, desde_iso, hasta_iso)

    if not intervalos:
        # Base case: acometida raíz (sin filas de alimentación entrante en la tabla)
        return [{"desde": desde_n, "hasta": hasta_n, "camino": [], "completo": True}]

    resultado: list[dict] = []
    cursor = desde_n

    for iv in intervalos:
        iv_desde = _norm(iv["intervalo_desde"])
        iv_hasta = _norm(iv["intervalo_hasta"])
        fuente_id = iv.get("fuente_activo_id")

        # Hueco antes del inicio de este intervalo
        if cursor < iv_desde:
            resultado.append({"desde": cursor, "hasta": iv_desde, "camino": [], "completo": False})

        if fuente_id is None:
            # Fuente explícitamente nula: sin atribución posible aguas arriba
            resultado.append({"desde": iv_desde, "hasta": iv_hasta, "camino": [], "completo": False})
        else:
            # Recursar en la cadena del padre, restringida a este sub-intervalo
            sub = resolver_caminos(fuente_id, iv_desde, iv_hasta, resolver_fuente, _vis)
            for sc in sub:
                resultado.append({
                    "desde":    sc["desde"],
                    "hasta":    sc["hasta"],
                    "camino":   [fuente_id] + sc["camino"],
                    "completo": sc["completo"],
                })

        cursor = iv_hasta

    # Hueco después del último intervalo
    if cursor < hasta_n:
        resultado.append({"desde": cursor, "hasta": hasta_n, "camino": [], "completo": False})

    return resultado


def integrar_por_segmentos(
    mediciones: list[dict],
    segmentos: list[dict],
    bucket_min: int,
) -> list[dict]:
    """Integra la energía de las mediciones distribuyéndola en segmentos temporales.

    mediciones: [{"ts": str ISO, "kw": float}], ordenada por ts ascendente.
    segmentos: salida de resolver_caminos, ordenada por "desde".
    bucket_min: separación nominal entre muestras en minutos (5 para 24h/7d, 60 para 30d).

    Corta la serie temporal en las fronteras de cada segmento interpolando linealmente
    el kW en el instante de frontera, de modo que la suma de las energías por segmento
    reproduce exactamente la integral trapezoidal del periodo completo.

    Invariante obligatoria (no aproximada):
      sum(s["energia_kwh"] for s in result) == integral trapezoidal total con tolerancia float.

    Retorna la lista de segmentos enriquecida con:
      energia_kwh (float): integral trapezoidal atribuida al segmento.
      hueco_datos_min (float): minutos dentro del segmento donde la separación entre
        muestras consecutivas supera 2×bucket_min. La energía sobre el hueco se
        sigue integrando (no se descarta), solo se declara su existencia.
    """
    if not segmentos:
        return []

    n_seg = len(segmentos)
    energy_acc = [0.0] * n_seg
    hueco_acc = [0.0] * n_seg

    # Pre-parsear límites de segmentos como POSIX timestamps
    seg_t0 = [_ts(s["desde"]) for s in segmentos]
    seg_t1 = [_ts(s["hasta"]) for s in segmentos]
    umbral_s = 2.0 * bucket_min * 60.0  # segundos

    def _seg_para_tiempo(t: float) -> int:
        """Índice del segmento que contiene el instante t."""
        for i in range(n_seg):
            if seg_t0[i] <= t < seg_t1[i]:
                return i
        # t exactamente al final del último segmento (tolerancia numérica)
        if abs(t - seg_t1[-1]) < 1e-3:
            return n_seg - 1
        return -1

    if len(mediciones) < 2:
        return [{**s, "energia_kwh": 0.0, "hueco_datos_min": 0.0} for s in segmentos]

    med_t = [_ts(m["ts"]) for m in mediciones]
    med_kw = [float(m.get("kw", 0.0)) for m in mediciones]

    for i in range(len(mediciones) - 1):
        t0, t1 = med_t[i], med_t[i + 1]
        kw0, kw1 = med_kw[i], med_kw[i + 1]

        if t1 <= t0:
            continue

        gap_s = t1 - t0
        es_hueco = gap_s > umbral_s

        # Encontrar fronteras de segmentos estrictamente dentro de (t0, t1)
        fronteras = sorted({
            b
            for b in (seg_t0 + seg_t1)
            if t0 < b < t1
        })
        puntos = [t0] + fronteras + [t1]

        for j in range(len(puntos) - 1):
            pa, pb = puntos[j], puntos[j + 1]
            frac_a = (pa - t0) / (t1 - t0)
            frac_b = (pb - t0) / (t1 - t0)
            kwa = kw0 + (kw1 - kw0) * frac_a
            kwb = kw0 + (kw1 - kw0) * frac_b
            dt_h = (pb - pa) / 3600.0
            energy = (kwa + kwb) / 2.0 * dt_h

            t_mid = (pa + pb) / 2.0
            seg_i = _seg_para_tiempo(t_mid)
            if seg_i >= 0:
                energy_acc[seg_i] += energy
                if es_hueco:
                    # Acumula los minutos de hueco proporcionalmente al sub-intervalo
                    hueco_acc[seg_i] += (pb - pa) / 60.0

    return [
        {
            **s,
            "energia_kwh":    round(energy_acc[i], 6),
            "hueco_datos_min": round(hueco_acc[i], 2),
        }
        for i, s in enumerate(segmentos)
    ]


def agregar_por_camino(segmentos_energia: list[dict]) -> dict[int, float]:
    """Acumula energia_kwh de cada segmento en todos los nodos de su camino.

    Los segmentos con camino vacío (huecos de vigencia o acometida raíz)
    no aportan a ningún nodo; su energía queda sin atribuir aguas arriba.

    Retorna dict {nodo_id: kwh_total}.
    """
    acum: dict[int, float] = {}
    for seg in segmentos_energia:
        kwh = seg.get("energia_kwh", 0.0)
        for nodo_id in seg.get("camino", []):
            acum[nodo_id] = acum.get(nodo_id, 0.0) + kwh
    return acum


def subdividir_por_mes(segmentos: list[dict]) -> list[dict]:
    """Parte cada segmento en las fronteras de mes en UTC.

    Mantiene la invariante de conservación de energía: la energía del segmento
    original se redistribuye proporcionalmente al tiempo de cada sub-segmento.
    Los segmentos sin energía (energia_kwh=0 o ausente) se subdividen igualmente.

    Retorna lista ordenada por 'desde'; el orden de segmentos del input se preserva.
    """
    from datetime import datetime, timezone, timedelta

    result = []
    for seg in segmentos:
        desde_n = seg["desde"]
        hasta_n = seg["hasta"]
        energia_kwh = seg.get("energia_kwh", 0.0)

        # Calcular fronteras de mes dentro de (desde_n, hasta_n)
        d0 = datetime.fromisoformat(desde_n.replace("Z", "+00:00"))
        d1 = datetime.fromisoformat(hasta_n.replace("Z", "+00:00"))

        # Construir lista de cortes: inicio del mes siguiente a d0, hasta < d1
        fronteras: list[datetime] = []
        # primer corte: primer día del mes siguiente a d0
        if d0.month == 12:
            prox = d0.replace(year=d0.year + 1, month=1, day=1,
                              hour=0, minute=0, second=0, microsecond=0)
        else:
            prox = d0.replace(month=d0.month + 1, day=1,
                              hour=0, minute=0, second=0, microsecond=0)
        while prox < d1:
            fronteras.append(prox)
            if prox.month == 12:
                prox = prox.replace(year=prox.year + 1, month=1, day=1)
            else:
                prox = prox.replace(month=prox.month + 1, day=1)

        if not fronteras:
            # El segmento cae íntegramente en un solo mes
            result.append(seg)
            continue

        # Dividir en sub-segmentos y distribuir energía proporcional al tiempo
        total_s = (d1 - d0).total_seconds()
        puntos = [d0] + fronteras + [d1]

        for i in range(len(puntos) - 1):
            pa = puntos[i]
            pb = puntos[i + 1]
            frac = (pb - pa).total_seconds() / total_s if total_s > 0 else 0.0
            sub_kwh = round(energia_kwh * frac, 6)
            sub = {**seg,
                   "desde": pa.astimezone(timezone.utc).isoformat(),
                   "hasta": pb.astimezone(timezone.utc).isoformat(),
                   "energia_kwh": sub_kwh}
            result.append(sub)

    return result


def valorar_segmentos(
    segmentos_energia: list[dict],
    precios: dict,
    contrato_intervals: dict,
    tipos_por_nodo: "dict | None" = None,
) -> list[dict]:
    """Valora económicamente cada segmento según el contrato de su acometida.

    Si un segmento abarca más de un intervalo de contrato en la acometida, se subdivide
    proporcionalmente al tiempo en cada tramo de contrato; cada sub-segmento recibe su
    propio contrato_id, precio y costo.

    Args:
        segmentos_energia: salida de integrar_por_segmentos (o subdividir_por_mes),
            con claves: desde, hasta, camino (list[int]), energia_kwh, completo.
        precios: dict indexado por (contrato_id, anio, mes) →
            {"precio_mxn_kwh": float|None, "fuente": str, "mes_referencia": str|None}.
            Precalculado por el llamante para evitar N+1.
        contrato_intervals: dict {acometida_id: list[{contrato_id, intervalo_desde, intervalo_hasta}]}.
            Resultado de resolver_intervalos_contrato por acometida, precalculado.
        tipos_por_nodo: dict {nodo_id: tipo_str} para detectar nodos de tipo 'generacion'.
            Si un nodo en el camino es 'generacion', el costo es None.

    Retorna lista de segmentos con campos añadidos:
        contrato_id (int|None), precio_mxn_kwh (float|None),
        costo_mxn (float|None), fuente_precio (str|None).
    Casos con costo_mxn=None (no se usa 0):
        - camino vacío (sin acometida conocida)
        - acometida sin contrato vigente en el intervalo
        - contrato sin factura resoluble
        - camino contiene nodo de tipo 'generacion'
    """
    from datetime import datetime, timezone

    tipos_por_nodo = tipos_por_nodo or {}

    result = []
    for seg in segmentos_energia:
        camino = seg.get("camino", [])
        desde_n = seg["desde"]
        hasta_n = seg["hasta"]

        # Caso: camino vacío → sin atribución → sin costo
        if not camino:
            result.append({**seg, "contrato_id": None, "precio_mxn_kwh": None,
                           "costo_mxn": None, "fuente_precio": "sin_vigencia"})
            continue

        # Caso: camino contiene nodo de tipo 'generacion' → costo por gas (futuro)
        if tipos_por_nodo and any(tipos_por_nodo.get(n) == "generacion" for n in camino):
            result.append({**seg, "contrato_id": None, "precio_mxn_kwh": None,
                           "costo_mxn": None, "fuente_precio": "generacion"})
            continue

        # La acometida es el último elemento del camino
        acometida_id = camino[-1]

        # Todos los intervalos de contrato de la acometida que solapan con [desde_n, hasta_n)
        intervals = contrato_intervals.get(acometida_id, [])
        seg_desde_n = _norm(desde_n)
        seg_hasta_n = _norm(hasta_n)
        energia_kwh = seg.get("energia_kwh", 0.0)
        total_s = _ts(hasta_n) - _ts(desde_n)

        # Recopilar tramos solapantes: (iv_desde_norm, iv_hasta_norm, contrato_id)
        tramos: list[tuple[str, str, int]] = []
        for iv in intervals:
            iv_desde_n = _norm(iv["intervalo_desde"])
            iv_hasta_n = _norm(iv["intervalo_hasta"])
            # Solapa si iv_desde < seg_hasta y iv_hasta > seg_desde
            if iv_desde_n < seg_hasta_n and iv_hasta_n > seg_desde_n:
                tramo_desde = max(iv_desde_n, seg_desde_n)
                tramo_hasta = min(iv_hasta_n, seg_hasta_n)
                tramos.append((tramo_desde, tramo_hasta, iv["contrato_id"]))

        # Sin ningún intervalo de contrato solapante
        if not tramos:
            result.append({**seg, "contrato_id": None, "precio_mxn_kwh": None,
                           "costo_mxn": None, "fuente_precio": "sin_contrato"})
            continue

        # Ordenar tramos por inicio (por si intervals no vienen ordenados)
        tramos.sort(key=lambda t: t[0])

        for tramo_desde, tramo_hasta, contrato_id in tramos:
            # Fracción de energía proporcional al tiempo
            if total_s > 0:
                tramo_s = _ts(tramo_hasta) - _ts(tramo_desde)
                frac = tramo_s / total_s
            else:
                frac = 1.0 / len(tramos)
            sub_kwh = round(energia_kwh * frac, 6)

            # Resolver mes del sub-tramo
            dt0 = datetime.fromtimestamp(_ts(tramo_desde), tz=timezone.utc)
            anio, mes = dt0.year, dt0.month

            info = precios.get((contrato_id, anio, mes),
                               {"precio_mxn_kwh": None, "fuente": "sin_datos", "mes_referencia": None})
            precio = info["precio_mxn_kwh"]
            costo = round(sub_kwh * precio, 2) if precio is not None else None

            result.append({**seg,
                           "desde":          tramo_desde,
                           "hasta":          tramo_hasta,
                           "energia_kwh":    sub_kwh,
                           "contrato_id":    contrato_id,
                           "precio_mxn_kwh": precio,
                           "costo_mxn":      costo,
                           "fuente_precio":  info["fuente"]})

    return result


def agregar_costo_por_camino(segmentos_valorados: list[dict]) -> "dict[int, dict]":
    """Acumula costo_mxn y energía sin costo de cada segmento en todos los nodos del camino.

    Retorna dict {nodo_id: {"costo_mxn": float|None, "energia_sin_costo_kwh": float}}.
    - costo_mxn: None si TODOS los segmentos atribuidos al nodo tienen costo_mxn=None;
      suma de costes parciales en otro caso.
    - energia_sin_costo_kwh: suma de energia_kwh de segmentos con costo_mxn=None.

    Los segmentos con camino vacío no aportan a ningún nodo.
    """
    acum_costo: "dict[int, float | None]" = {}
    acum_sin_costo: dict[int, float] = {}
    tiene_costo: dict[int, bool] = {}

    for seg in segmentos_valorados:
        camino = seg.get("camino", [])
        kwh = seg.get("energia_kwh", 0.0)
        costo = seg.get("costo_mxn")

        for nodo_id in camino:
            if costo is not None:
                tiene_costo[nodo_id] = True
                acum_costo[nodo_id] = round((acum_costo.get(nodo_id) or 0.0) + costo, 2)
            else:
                acum_sin_costo[nodo_id] = round(acum_sin_costo.get(nodo_id, 0.0) + kwh, 3)

    # Unir nodos que aparecen en cualquier acumulador
    todos_nodos = set(acum_costo) | set(acum_sin_costo) | set(tiene_costo)
    return {
        nid: {
            "costo_mxn":           acum_costo.get(nid) if tiene_costo.get(nid) else None,
            "energia_sin_costo_kwh": acum_sin_costo.get(nid, 0.0),
        }
        for nid in todos_nodos
    }


def filtrar_segmentos_por_rol(
    segmentos_medidor: list[dict],
    intervalos_rol: list[dict],
) -> "tuple[list[dict], list[dict]]":
    """Separa segmentos de energía entre carga y cabecera según los intervalos de rol.

    Función pura. Cada segmento se interseca con los intervalos de rol; la energía
    se distribuye proporcionalmente al tiempo en cada sub-tramo resultante.

    Args:
        segmentos_medidor: lista de dicts con al menos `desde` (str ISO),
            `hasta` (str ISO), `energia_kwh` (float/Decimal), y campos arbitrarios.
        intervalos_rol: salida de resolver_intervalos_rol. Cada dict contiene
            `rol`, `intervalo_desde`, `intervalo_hasta`.

    Returns:
        Tupla (segmentos_carga, segmentos_cabecera). Invariante energética:
        sum(carga.energia_kwh) + sum(cabecera.energia_kwh) == sum(input.energia_kwh).
    """
    if not segmentos_medidor:
        return [], []

    # Si no hay intervalos de rol, todo es carga (default)
    if not intervalos_rol:
        return list(segmentos_medidor), []

    carga: list[dict] = []
    cabecera: list[dict] = []

    for seg in segmentos_medidor:
        seg_desde = _norm(seg.get("desde", ""))
        seg_hasta = _norm(seg.get("hasta", ""))
        energia = float(seg.get("energia_kwh", 0.0))

        seg_t0 = _ts(seg_desde)
        seg_t1 = _ts(seg_hasta)
        seg_total_s = seg_t1 - seg_t0

        if seg_total_s <= 0:
            carga.append(seg)
            continue

        # Encontrar intervalos de rol que solapan con este segmento
        for iv in intervalos_rol:
            iv_desde = _norm(iv["intervalo_desde"])
            iv_hasta = _norm(iv["intervalo_hasta"])

            # Intersección (usar timestamps para comparar, no strings)
            inter_t0 = max(seg_t0, _ts(iv_desde))
            inter_t1 = min(seg_t1, _ts(iv_hasta))

            if inter_t0 >= inter_t1:
                continue

            inter_desde = datetime.fromtimestamp(inter_t0, tz=timezone.utc).isoformat()
            inter_hasta = datetime.fromtimestamp(inter_t1, tz=timezone.utc).isoformat()
            frac = (inter_t1 - inter_t0) / seg_total_s
            sub_kwh = round(energia * frac, 6)

            sub_seg = {
                **seg,
                "desde":       inter_desde,
                "hasta":       inter_hasta,
                "energia_kwh": sub_kwh,
                "rol":         iv["rol"],
            }

            if iv["rol"] == "carga":
                carga.append(sub_seg)
            else:
                cabecera.append(sub_seg)

    return carga, cabecera
