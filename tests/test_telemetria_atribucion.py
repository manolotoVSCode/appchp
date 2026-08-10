"""Tests para calc/telemetria_atribucion.py.

Todas las pruebas usan funciones puras con resolver_fuente simulado (sin BD).
"""
import math
import os
import pytest
from datetime import datetime, timezone, timedelta

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "fake_key")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest

from calc.telemetria_atribucion import (
    agregar_por_camino,
    integrar_por_segmentos,
    resolver_caminos,
)


# ── Utilidades de test ────────────────────────────────────────────────────────

def _n(s: str) -> str:
    """Normaliza ISO 8601 a UTC +00:00 (misma convención que _norm en el módulo)."""
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()


# Instantes del rango de prueba: enero 2024
D  = _n("2024-01-01T00:00:00Z")   # inicio
M  = _n("2024-01-15T12:00:00Z")   # mitad
M2 = _n("2024-01-20T00:00:00Z")   # un punto más adelante
H  = _n("2024-01-31T23:59:59Z")   # fin


def make_resolver(tabla: dict) -> callable:
    """Crea un resolver simulado a partir de un dict {activo_id: [(fuente_id, desde, hasta|None)]}.

    La función recorta cada intervalo al [desde_iso, hasta_iso] solicitado, replicando
    la semántica de resolver_intervalos_fuente. hasta=None significa intervalo abierto.
    """
    def resolver(activo_id: int, desde_iso: str, hasta_iso: str) -> list[dict]:
        result = []
        for fuente_id, f_d, f_h in tabla.get(activo_id, []):
            iv_d = max(f_d, desde_iso)
            iv_h = min(f_h, hasta_iso) if f_h is not None else hasta_iso
            if iv_d < iv_h:
                result.append({
                    "fuente_activo_id": fuente_id,
                    "intervalo_desde":  iv_d,
                    "intervalo_hasta":  iv_h,
                    "motivo":           "test",
                })
        return result
    return resolver


def _meds_lineales(n: int, kw: float, desde: str, hasta: str) -> list[dict]:
    """Genera n mediciones de kW constante igualmente espaciadas en [desde, hasta]."""
    dt0 = datetime.fromisoformat(desde.replace("Z", "+00:00"))
    dt1 = datetime.fromisoformat(hasta.replace("Z", "+00:00"))
    total_s = (dt1 - dt0).total_seconds()
    return [
        {
            "ts": (dt0 + timedelta(seconds=total_s * i / (n - 1))).isoformat(),
            "kw": kw,
        }
        for i in range(n)
    ]


def _integral_trapezoid(meds: list[dict]) -> float:
    """Integral trapezoidal de referencia sobre la serie completa."""
    total = 0.0
    for i in range(1, len(meds)):
        t0 = datetime.fromisoformat(meds[i - 1]["ts"].replace("Z", "+00:00")).timestamp()
        t1 = datetime.fromisoformat(meds[i]["ts"].replace("Z", "+00:00")).timestamp()
        kw0 = meds[i - 1]["kw"]
        kw1 = meds[i]["kw"]
        total += (kw0 + kw1) / 2.0 * (t1 - t0) / 3600.0
    return total


# ── Test a — Carga sin cambios en el rango ────────────────────────────────────

def test_carga_sin_cambios():
    """Un activo con fuente constante durante todo el rango → un segmento completo."""
    resolver = make_resolver({
        10: [(1, D, None)],   # carga 10 → acometida 1, sin cambios
        # acometida 1 no tiene entradas → base case
    })
    caminos = resolver_caminos(10, D, H, resolver)

    assert len(caminos) == 1
    assert caminos[0]["camino"] == [1]
    assert caminos[0]["completo"] is True
    assert caminos[0]["desde"] == D
    assert caminos[0]["hasta"] == H


# ── Test b — Cambio de alimentación a mitad del rango ────────────────────────

def test_cambio_alimentacion():
    """La carga cambia de transformador a mitad del rango → dos segmentos."""
    resolver = make_resolver({
        20: [(2, D, M), (3, M, None)],   # carga 20: fuente 2 → fuente 3
        # transformadores 2 y 3 son raíces (acometidas): sin entradas
    })
    caminos = resolver_caminos(20, D, H, resolver)

    assert len(caminos) == 2
    assert caminos[0]["camino"] == [2]
    assert caminos[0]["completo"] is True
    assert caminos[0]["desde"] == D
    assert caminos[0]["hasta"] == M

    assert caminos[1]["camino"] == [3]
    assert caminos[1]["completo"] is True
    assert caminos[1]["desde"] == M
    assert caminos[1]["hasta"] == H


# ── Test c — Cambio en el nodo padre, sin cambio en la carga ─────────────────

def test_cambio_en_nodo_padre_subdivide():
    """El transformador (padre de la carga) cambia de subestación.
    La carga no cambia de padre, pero la intersección subdivide sus intervalos.
    """
    # Topología: carga 30 → transformador 5 (todo el rango)
    # Transformador 5: fuente 6 hasta M, luego fuente 7 desde M
    resolver = make_resolver({
        30: [(5, D, None)],         # carga → transformador (todo el rango)
        5:  [(6, D, M), (7, M, None)],  # transformador cambia de subestación
        # 6 y 7 son acometidas: sin entradas
    })
    caminos = resolver_caminos(30, D, H, resolver)

    assert len(caminos) == 2, f"esperados 2 segmentos, obtenidos {len(caminos)}"

    assert caminos[0]["camino"] == [5, 6]
    assert caminos[0]["completo"] is True
    assert caminos[0]["desde"] == D
    assert caminos[0]["hasta"] == M

    assert caminos[1]["camino"] == [5, 7]
    assert caminos[1]["completo"] is True
    assert caminos[1]["desde"] == M
    assert caminos[1]["hasta"] == H


# ── Test d — Cambio de medidor a mitad del rango ─────────────────────────────

def test_cambio_de_medidor_conserva_energia():
    """Con dos medidores distintos en dos mitades, la energía total se conserva.

    Simula el caso de dos medidores: M1 mide la primera mitad, M2 la segunda.
    Las mediciones se mezclan y la energía integrada debe ser la suma de ambas.
    """
    # Mediciones de M1: [D, M], kw=100
    # Mediciones de M2: [M, H], kw=200
    meds_m1 = _meds_lineales(5, 100.0, D, M)
    meds_m2 = _meds_lineales(5, 200.0, M, H)
    meds_merged = sorted(meds_m1 + meds_m2, key=lambda r: r["ts"])

    # Un único segmento que cubre todo el rango (sin cambio de alimentación)
    segmentos = [{"desde": D, "hasta": H, "camino": [1], "completo": True}]
    resultado = integrar_por_segmentos(meds_merged, segmentos, bucket_min=5)

    energia_esperada = _integral_trapezoid(meds_merged)
    # La energía integrada sobre las mediciones mezcladas de ambos medidores
    # debe coincidir con la integral trapezoidal directa.
    assert abs(resultado[0]["energia_kwh"] - energia_esperada) < 1e-4
    # hueco_datos_min puede ser > 0 dado que las mediciones sintéticas están
    # espaciadas varios días, excediendo el umbral 2×bucket_min. Lo que se
    # verifica aquí es la conservación de energía, no la densidad de datos.


# ── Test e — Hueco de vigencia ────────────────────────────────────────────────

def test_hueco_de_vigencia():
    """Activo sin vigencia entre M y M2 → segmento incompleto en ese intervalo."""
    resolver = make_resolver({
        40: [
            (1, D, M),    # vigencia hasta M
            (1, M2, None),  # vigencia desde M2 (hueco entre M y M2)
        ],
    })
    caminos = resolver_caminos(40, D, H, resolver)

    # Tres segmentos: [D,M] completo, [M,M2] incompleto, [M2,H] completo
    assert len(caminos) == 3

    assert caminos[0]["completo"] is True
    assert caminos[0]["camino"] == [1]
    assert caminos[0]["desde"] == D
    assert caminos[0]["hasta"] == M

    assert caminos[1]["completo"] is False
    assert caminos[1]["camino"] == []
    assert caminos[1]["desde"] == M
    assert caminos[1]["hasta"] == M2

    assert caminos[2]["completo"] is True
    assert caminos[2]["camino"] == [1]
    assert caminos[2]["desde"] == M2
    assert caminos[2]["hasta"] == H


# ── Test f — Acometida como activo consultado ─────────────────────────────────

def test_acometida_caso_base():
    """El activo consultado no tiene entradas en la tabla → segmento completo, camino vacío."""
    resolver = make_resolver({})   # acometida: sin ninguna entrada
    caminos = resolver_caminos(1, D, H, resolver)

    assert len(caminos) == 1
    assert caminos[0]["camino"] == []
    assert caminos[0]["completo"] is True
    assert caminos[0]["desde"] == D
    assert caminos[0]["hasta"] == H


# ── Test g — Invariante: suma de energías == integral trapezoidal completa ────

def test_invariante_suma_energia():
    """La suma de energia_kwh de todos los segmentos iguala la integral trapezoidal total."""
    # Mediciones con kW variable sobre el rango completo
    dt0 = datetime.fromisoformat(D.replace("Z", "+00:00"))
    dt1 = datetime.fromisoformat(H.replace("Z", "+00:00"))
    total_s = (dt1 - dt0).total_seconds()
    n = 10
    meds = [
        {
            "ts": (dt0 + timedelta(seconds=total_s * i / (n - 1))).isoformat(),
            "kw": 50.0 + 30.0 * math.sin(2 * math.pi * i / n),
        }
        for i in range(n)
    ]

    # Dos segmentos que dividen el rango exactamente por la mitad
    segmentos = [
        {"desde": D, "hasta": M, "camino": [1], "completo": True},
        {"desde": M, "hasta": H, "camino": [2], "completo": True},
    ]
    resultado = integrar_por_segmentos(meds, segmentos, bucket_min=5)

    energia_total_segs = sum(s["energia_kwh"] for s in resultado)
    energia_trapezoid = _integral_trapezoid(meds)

    # Tolerancia 1e-6: el round(..., 6) intermedio en integrar_por_segmentos
    # introduce hasta ~5e-7 por segmento. Con dos segmentos la cota es ~1e-6.
    # La invariante es exacta en matemática exacta; la tolerancia es float.
    assert abs(energia_total_segs - energia_trapezoid) < 1e-6, (
        f"Invariante violada: suma segmentos={energia_total_segs:.9f}, "
        f"trapezoid={energia_trapezoid:.9f}"
    )


# ── Test h — subdividir_por_mes ───────────────────────────────────────────────

def test_subdividir_por_mes_segmento_unico_mes():
    """Segmento dentro de un solo mes → sin subdivisión."""
    from calc.telemetria_atribucion import subdividir_por_mes
    seg = {"desde": D, "hasta": M, "camino": [1], "completo": True, "energia_kwh": 500.0}
    result = subdividir_por_mes([seg])
    assert len(result) == 1
    assert result[0]["energia_kwh"] == pytest.approx(500.0)


def test_subdividir_por_mes_cruza_frontera():
    """Segmento que cruza frontera de mes → dos sub-segmentos con energía conservada."""
    from calc.telemetria_atribucion import subdividir_por_mes
    seg = {
        "desde": _n("2024-01-15T00:00:00Z"),
        "hasta": _n("2024-02-15T00:00:00Z"),
        "camino": [1], "completo": True, "energia_kwh": 1000.0,
    }
    result = subdividir_por_mes([seg])
    assert len(result) == 2
    suma = sum(s["energia_kwh"] for s in result)
    assert abs(suma - 1000.0) < 1e-4
    # La frontera de mes es 2024-02-01T00:00:00+00:00
    assert result[0]["hasta"].startswith("2024-02-01")
    assert result[1]["desde"].startswith("2024-02-01")


# ── Test i — valorar_segmentos ────────────────────────────────────────────────

def _make_precio(precio_mxn_kwh, fuente="factura_mes_exacto"):
    return {"precio_mxn_kwh": precio_mxn_kwh, "fuente": fuente, "mes_referencia": "2024-01"}


def test_valorar_segmentos_precio_aplicado():
    """Segmento con camino [ac1] y precio 2.0 MXN/kWh → costo = energia × precio."""
    from calc.telemetria_atribucion import valorar_segmentos
    seg = {"desde": D, "hasta": M, "camino": [1], "completo": True, "energia_kwh": 100.0}
    precios = {(5, 2024, 1): _make_precio(2.0)}
    contrato_intervals = {1: [{"contrato_id": 5, "intervalo_desde": D, "intervalo_hasta": H}]}
    result = valorar_segmentos([seg], precios, contrato_intervals)
    assert result[0]["costo_mxn"] == pytest.approx(200.0)
    assert result[0]["contrato_id"] == 5
    assert result[0]["fuente_precio"] == "factura_mes_exacto"


def test_valorar_segmentos_camino_vacio_sin_costo():
    """Segmento con camino vacío → costo_mxn=None, fuente='sin_vigencia'."""
    from calc.telemetria_atribucion import valorar_segmentos
    seg = {"desde": D, "hasta": M, "camino": [], "completo": False, "energia_kwh": 100.0}
    result = valorar_segmentos([seg], {}, {})
    assert result[0]["costo_mxn"] is None
    assert result[0]["fuente_precio"] == "sin_vigencia"


def test_valorar_segmentos_sin_contrato_vigente():
    """Acometida sin contrato en acometida_contrato_vigencia → costo_mxn=None."""
    from calc.telemetria_atribucion import valorar_segmentos
    seg = {"desde": D, "hasta": M, "camino": [1], "completo": True, "energia_kwh": 100.0}
    # contrato_intervals vacío para la acometida 1
    result = valorar_segmentos([seg], {}, {1: []})
    assert result[0]["costo_mxn"] is None
    assert result[0]["fuente_precio"] == "sin_contrato"


def test_valorar_segmentos_generacion_sin_costo():
    """Camino que pasa por un nodo de tipo 'generacion' → costo=None."""
    from calc.telemetria_atribucion import valorar_segmentos
    seg = {"desde": D, "hasta": M, "camino": [10, 1], "completo": True, "energia_kwh": 100.0}
    tipos = {10: "generacion", 1: "acometida"}
    result = valorar_segmentos([seg], {}, {}, tipos_por_nodo=tipos)
    assert result[0]["costo_mxn"] is None
    assert result[0]["fuente_precio"] == "generacion"


def test_valorar_segmentos_dos_meses_distintos_precios():
    """Segmento ya dividido por mes: precios distintos por mes → costos distintos."""
    from calc.telemetria_atribucion import valorar_segmentos
    seg_ene = {
        "desde": _n("2024-01-01T00:00:00Z"),
        "hasta": _n("2024-02-01T00:00:00Z"),
        "camino": [1], "completo": True, "energia_kwh": 300.0,
    }
    seg_feb = {
        "desde": _n("2024-02-01T00:00:00Z"),
        "hasta": _n("2024-03-01T00:00:00Z"),
        "camino": [1], "completo": True, "energia_kwh": 200.0,
    }
    precios = {
        (5, 2024, 1): _make_precio(2.0),
        (5, 2024, 2): _make_precio(3.0),
    }
    contrato_intervals = {1: [{"contrato_id": 5,
                                "intervalo_desde": _n("2024-01-01T00:00:00Z"),
                                "intervalo_hasta": _n("2024-03-01T00:00:00Z")}]}
    result = valorar_segmentos([seg_ene, seg_feb], precios, contrato_intervals)
    assert result[0]["costo_mxn"] == pytest.approx(600.0)  # 300 × 2.0
    assert result[1]["costo_mxn"] == pytest.approx(600.0)  # 200 × 3.0


# ── Test j — agregar_costo_por_camino ─────────────────────────────────────────

def test_agregar_costo_por_camino_acumula():
    """Dos segmentos con camino [2, 1]: costos se suman en ambos nodos."""
    from calc.telemetria_atribucion import agregar_costo_por_camino
    segs = [
        {"camino": [2, 1], "energia_kwh": 100.0, "costo_mxn": 200.0},
        {"camino": [2, 1], "energia_kwh": 100.0, "costo_mxn": 300.0},
    ]
    result = agregar_costo_por_camino(segs)
    assert result[1]["costo_mxn"] == pytest.approx(500.0)
    assert result[2]["costo_mxn"] == pytest.approx(500.0)
    assert result[1]["energia_sin_costo_kwh"] == 0.0


def test_agregar_costo_por_camino_mix_sin_costo():
    """Un segmento con costo y otro sin costo: energia_sin_costo_kwh en los nodos compartidos."""
    from calc.telemetria_atribucion import agregar_costo_por_camino
    segs = [
        {"camino": [2, 1], "energia_kwh": 100.0, "costo_mxn": 200.0},
        {"camino": [2, 1], "energia_kwh": 50.0, "costo_mxn": None},
    ]
    result = agregar_costo_por_camino(segs)
    assert result[1]["costo_mxn"] == pytest.approx(200.0)
    assert result[1]["energia_sin_costo_kwh"] == pytest.approx(50.0)


def test_agregar_costo_por_camino_todos_sin_costo():
    """Todos los segmentos sin costo: costo_mxn=None en los nodos."""
    from calc.telemetria_atribucion import agregar_costo_por_camino
    segs = [
        {"camino": [1], "energia_kwh": 100.0, "costo_mxn": None},
    ]
    result = agregar_costo_por_camino(segs)
    assert result[1]["costo_mxn"] is None
    assert result[1]["energia_sin_costo_kwh"] == pytest.approx(100.0)
