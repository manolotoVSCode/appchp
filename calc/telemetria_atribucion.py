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
