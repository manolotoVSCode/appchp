# tests/test_repository_mediciones.py
"""Tests unitarios para las funciones de telemetría fase 2.

Patrón: mock de storage.repository._supabase siguiendo test_seleccion_mezcla.py
y test_cli.py. Sin acceso real a Supabase.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, call, patch

import pytest

# Garantizar que el módulo pueda importarse sin credenciales reales
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "fake_key")

import storage.repository as repo

# ── Fixtures de datos ─────────────────────────────────────────────────────────

_MEDIDOR = {
    "id": 1,
    "empresa_id": 10,
    "nombre": "Medidor Planta Norte",
    "punto_medicion": "MPN-01",
    "ubicacion": "Cuarto eléctrico N",
    "numero_serie": "ACC2024001",
    "relacion_tc": 200.0,
    "marca": "Accuenergy",
    "modelo": "Acuvim II",
    "activo": True,
    "created_at": "2026-06-01T00:00:00+00:00",
}

_VARS_COMPLETAS = {
    "v_an": 127.1, "v_bn": 126.8, "v_cn": 127.3, "v_avg_ln": 127.07,
    "v_ab": 220.1, "v_bc": 219.8, "v_ca": 220.4, "v_avg_ll": 220.1,
    "i_a": 45.2,   "i_b": 44.8,   "i_c": 45.5,   "i_n": 0.3, "i_avg": 45.17,
    "kw_a": 5.741, "kw_b": 5.690, "kw_c": 5.790, "kw_total": 17.221,
    "kvar_a": 1.2,  "kvar_b": 1.1,  "kvar_c": 1.3,  "kvar_total": 3.6,
    "kva_a": 5.865, "kva_b": 5.796, "kva_c": 5.930, "kva_total": 17.591,
    "pf_a": 0.979,  "pf_b": 0.981,  "pf_c": 0.977,  "pf_total": 0.979,
    "frecuencia_hz": 59.97,
    "kwh_importado": 12345.678, "kwh_exportado": 0.0,
    "kvarh_importado": 456.789, "kvarh_exportado": 0.0,
    "thd_v_a": 2.1, "thd_v_b": 2.0, "thd_v_c": 2.2,
    "thd_i_a": 8.3, "thd_i_b": 8.1, "thd_i_c": 8.5,
    "demanda_kw": 17.221, "demanda_kva": 17.591,
    "demanda_max_kw": 22.5, "demanda_max_kva": 23.0,
}

_MEDICION = {
    "id": 100, "medidor_id": 1,
    "timestamp": "2026-06-01T08:00:00+00:00",
    **_VARS_COMPLETAS,
}

_BUCKET = {
    "medidor_id": 1,
    "bucket_15min": "2026-06-01T08:00:00+00:00",
    "kw_total_avg": 17.1, "kw_total_max": 17.5, "kw_total_min": 16.8,
    "kvar_total_avg": 3.5, "kva_total_avg": 17.4, "pf_total_avg": 0.978,
    "v_avg_ln_avg": 127.0, "i_avg_avg": 45.0, "frecuencia_hz_avg": 59.97,
    "n_lecturas": 3, "kwh_periodo": 4.3, "kvarh_periodo": 0.9,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_table(tabla_data: dict[str, list]) -> MagicMock:
    """Construye un mock de _supabase para varias tablas con datos fijos.

    tabla_data: {nombre_tabla: lista_de_registros_a_devolver}
    Soporta encadenamiento: .table(t).insert/select/...execute() → MagicMock(data=...)
    """
    client = MagicMock()

    def _table(name):
        t = MagicMock()
        data = tabla_data.get(name, [])
        result = MagicMock(data=data)
        # Cadenas de métodos comunes — cada uno retorna un mock que termina en
        # .execute() → result para cualquier combinación de filtros/operaciones.
        for method in ("insert", "select", "update", "delete", "upsert"):
            getattr(t, method).return_value = _chained(result)
        return t

    client.table.side_effect = _table
    return client


def _chained(result: MagicMock) -> MagicMock:
    """Devuelve un MagicMock donde cualquier método encadenado termina en .execute() → result."""
    m = MagicMock()
    m.execute.return_value = result
    for attr in ("eq", "gte", "lte", "order", "limit", "select", "insert",
                 "neq", "in_", "range"):
        child = MagicMock()
        child.execute.return_value = result
        # Recursión un nivel: eq().gte().execute(), etc.
        for attr2 in ("eq", "gte", "lte", "order", "limit", "neq", "in_"):
            grandchild = MagicMock()
            grandchild.execute.return_value = result
            for a3 in ("eq", "gte", "lte", "order", "limit"):
                setattr(grandchild, a3, MagicMock(return_value=MagicMock(execute=MagicMock(return_value=result))))
            setattr(child, attr2, MagicMock(return_value=grandchild))
        setattr(m, attr, MagicMock(return_value=child))
    return m


# ── Tests ─────────────────────────────────────────────────────────────────────

# a) crear_medidor inserta y retorna el medidor con id
def test_crear_medidor_retorna_con_id():
    mock = _mock_table({"medidores": [_MEDIDOR]})
    with patch("storage.repository._supabase", mock):
        resultado = repo.crear_medidor(
            empresa_id=10,
            nombre="Medidor Planta Norte",
            punto_medicion="MPN-01",
            ubicacion="Cuarto eléctrico N",
            numero_serie="ACC2024001",
            relacion_tc=200.0,
        )
    assert resultado["id"] == 1
    assert resultado["empresa_id"] == 10
    assert resultado["marca"] == "Accuenergy"
    # Verificar que se llamó a insert en la tabla correcta
    mock.table.assert_called_with("medidores")


# b) obtener_medidores_por_empresa filtra por empresa_id
def test_obtener_medidores_por_empresa_filtra():
    mock = _mock_table({"medidores": [_MEDIDOR]})
    with patch("storage.repository._supabase", mock):
        resultado = repo.obtener_medidores_por_empresa(empresa_id=10)
    assert len(resultado) == 1
    assert resultado[0]["empresa_id"] == 10


def test_obtener_medidores_por_empresa_lista_vacia():
    mock = _mock_table({"medidores": []})
    with patch("storage.repository._supabase", mock):
        resultado = repo.obtener_medidores_por_empresa(empresa_id=99)
    assert resultado == []


# c) obtener_medidor retorna None cuando no existe
def test_obtener_medidor_no_existe():
    mock = _mock_table({"medidores": []})
    with patch("storage.repository._supabase", mock):
        resultado = repo.obtener_medidor(medidor_id=999)
    assert resultado is None


def test_obtener_medidor_existe():
    mock = _mock_table({"medidores": [_MEDIDOR]})
    with patch("storage.repository._supabase", mock):
        resultado = repo.obtener_medidor(medidor_id=1)
    assert resultado is not None
    assert resultado["id"] == 1


# d) insertar_medicion persiste todas las columnas del set completo
def test_insertar_medicion_persiste_set_completo():
    captured = {}

    client = MagicMock()
    t = MagicMock()
    client.table.return_value = t

    def _insert_spy(payload):
        captured.update(payload)
        return _chained(MagicMock(data=[{**payload, "id": 100}]))

    t.insert.side_effect = _insert_spy

    with patch("storage.repository._supabase", client):
        resultado = repo.insertar_medicion(
            medidor_id=1,
            timestamp="2026-06-01T08:00:00+00:00",
            **_VARS_COMPLETAS,
        )

    # El resultado proviene del mock (data[0])
    assert resultado["medidor_id"] == 1
    assert resultado["timestamp"] == "2026-06-01T08:00:00+00:00"

    # Verificar que todas las variables del set completo fueron enviadas al insert
    for clave in _VARS_COMPLETAS:
        assert clave in captured, f"Falta clave '{clave}' en el payload enviado a Supabase"
    assert captured["kw_total"] == _VARS_COMPLETAS["kw_total"]
    assert captured["frecuencia_hz"] == _VARS_COMPLETAS["frecuencia_hz"]


# e) insertar_mediciones_batch inserta múltiples y retorna el conteo
def test_insertar_mediciones_batch_retorna_conteo():
    filas = [
        {"medidor_id": 1, "timestamp": f"2026-06-01T08:0{i}:00+00:00", "kw_total": 17.0 + i}
        for i in range(5)
    ]
    # El mock devuelve la misma lista para cualquier insert
    mock = _mock_table({"mediciones_tiempo_real": filas})
    with patch("storage.repository._supabase", mock):
        total = repo.insertar_mediciones_batch(filas)
    assert total == 5


def test_insertar_mediciones_batch_lista_vacia():
    mock = _mock_table({"mediciones_tiempo_real": []})
    with patch("storage.repository._supabase", mock):
        total = repo.insertar_mediciones_batch([])
    assert total == 0


def test_insertar_mediciones_batch_divide_en_chunks():
    """Verifica que el batch de 1001 filas genera dos llamadas a insert (chunks de 1000)."""
    filas = [
        {"medidor_id": 1, "timestamp": f"2026-06-01T08:{i:04d}:00+00:00", "kw_total": 1.0}
        for i in range(1001)
    ]
    client = MagicMock()
    t = MagicMock()
    client.table.return_value = t
    t.insert.return_value = _chained(MagicMock(data=filas[:1000]))

    insert_calls = []

    def _insert_spy(chunk):
        insert_calls.append(len(chunk))
        return _chained(MagicMock(data=chunk))

    t.insert.side_effect = _insert_spy

    with patch("storage.repository._supabase", client):
        repo.insertar_mediciones_batch(filas)

    assert len(insert_calls) == 2
    assert insert_calls[0] == 1000
    assert insert_calls[1] == 1


# f) obtener_mediciones_recientes respeta rango de fechas, orden y .limit(20000)
def test_obtener_mediciones_recientes_rango_y_limit():
    desde = "2026-06-01T00:00:00+00:00"
    hasta = "2026-06-01T23:59:59+00:00"
    mock = _mock_table({"mediciones_tiempo_real": [_MEDICION]})

    # Necesitamos un mock más granular para verificar .limit(20000)
    client = MagicMock()
    t = MagicMock()
    client.table.return_value = t

    # Capturar la cadena completa
    limit_mock = MagicMock()
    limit_mock.execute.return_value = MagicMock(data=[_MEDICION])

    order_mock = MagicMock()
    order_mock.limit.return_value = limit_mock

    lte_mock = MagicMock()
    lte_mock.order.return_value = order_mock

    gte_mock = MagicMock()
    gte_mock.lte.return_value = lte_mock

    eq_mock = MagicMock()
    eq_mock.gte.return_value = gte_mock

    select_mock = MagicMock()
    select_mock.eq.return_value = eq_mock

    t.select.return_value = select_mock

    with patch("storage.repository._supabase", client):
        resultado = repo.obtener_mediciones_recientes(
            medidor_id=1, desde=desde, hasta=hasta
        )

    assert resultado == [_MEDICION]
    order_mock.limit.assert_called_once_with(20000)


# g) obtener_agregados_15min retorna buckets en el rango y aplica .limit(20000)
def test_obtener_agregados_15min_rango_y_limit():
    desde = "2026-06-01T00:00:00+00:00"
    hasta = "2026-06-01T23:59:59+00:00"

    client = MagicMock()
    t = MagicMock()
    client.table.return_value = t

    limit_mock = MagicMock()
    limit_mock.execute.return_value = MagicMock(data=[_BUCKET])

    order_mock = MagicMock()
    order_mock.limit.return_value = limit_mock

    lte_mock = MagicMock()
    lte_mock.order.return_value = order_mock

    gte_mock = MagicMock()
    gte_mock.lte.return_value = lte_mock

    eq_mock = MagicMock()
    eq_mock.gte.return_value = gte_mock

    select_mock = MagicMock()
    select_mock.eq.return_value = eq_mock

    t.select.return_value = select_mock

    with patch("storage.repository._supabase", client):
        resultado = repo.obtener_agregados_15min(
            medidor_id=1, desde=desde, hasta=hasta
        )

    assert resultado == [_BUCKET]
    order_mock.limit.assert_called_once_with(20000)


# h) insertar_medicion con medidor_id inexistente propaga el error de FK
def test_insertar_medicion_fk_error_se_propaga():
    """Cuando Supabase rechaza la inserción por FK, la excepción debe propagarse."""
    client = MagicMock()
    t = MagicMock()
    client.table.return_value = t
    t.insert.return_value.execute.side_effect = Exception(
        'insert or update on table "mediciones_tiempo_real" violates foreign key constraint'
    )

    with patch("storage.repository._supabase", client):
        with pytest.raises(Exception, match="foreign key"):
            repo.insertar_medicion(
                medidor_id=99999,
                timestamp="2026-06-01T08:00:00+00:00",
                kw_total=10.0,
            )
