# tests/test_migrar_facturas_a_contratos.py
"""Tests para scripts/migrar_facturas_a_contratos.py.

Cubre funciones puras (sin DB) y tests de integración con un cliente Supabase
simulado en memoria.
"""
from __future__ import annotations

import pytest

from scripts.migrar_facturas_a_contratos import (
    _letra_para_n,
    _agrupar_por_identificador,
    _inicializar_contadores,
    migrar,
)


# ── Mock de cliente Supabase ──────────────────────────────────────────────────

class _MockQuery:
    """Proxy encadenable que simula la API de supabase-py."""

    def __init__(self, db: dict, table_name: str):
        self._db = db
        self._name = table_name
        self._mode: str | None = None
        self._insert_data: dict | None = None
        self._update_data: dict | None = None
        self._filters: list[tuple] = []
        self._order_by: str | None = None

    # ── Operaciones ───────────────────────────────────────────────────────────

    def select(self, *args, **kwargs):
        self._mode = "select"
        return self

    def insert(self, data: dict):
        self._mode = "insert"
        self._insert_data = data
        return self

    def update(self, data: dict):
        self._mode = "update"
        self._update_data = data
        return self

    # ── Filtros ───────────────────────────────────────────────────────────────

    def eq(self, col: str, val):
        self._filters.append(("eq", col, val))
        return self

    def order(self, col: str):
        self._order_by = col
        return self

    # ── Ejecución ─────────────────────────────────────────────────────────────

    def _matches(self, row: dict) -> bool:
        for kind, col, val in self._filters:
            if kind == "eq" and row.get(col) != val:
                return False
        return True

    def execute(self):
        table: list[dict] = self._db["tables"][self._name]

        if self._mode == "select":
            rows = [r for r in table if self._matches(r)]
            if self._order_by:
                rows = sorted(rows, key=lambda r: r.get(self._order_by, 0))
            return _Result(rows)

        if self._mode == "insert":
            row = dict(self._insert_data)
            if "id" not in row:
                row["id"] = self._db["ids"][self._name]
                self._db["ids"][self._name] += 1
            table.append(row)
            return _Result([row])

        if self._mode == "update":
            updated = []
            for row in table:
                if self._matches(row):
                    row.update(self._update_data)
                    updated.append(row)
            return _Result(updated)

        raise ValueError(f"Modo no reconocido: {self._mode}")


class _Result:
    def __init__(self, data: list[dict]):
        self.data = data


class _MockClient:
    """Cliente Supabase simulado en memoria."""

    def __init__(self):
        self._db: dict = {
            "tables": {
                "clientes": [],
                "contratos": [],
                "cfe_facturas": [],
                "gas_facturas": [],
            },
            "ids": {
                "clientes": 1,
                "contratos": 1,
                "cfe_facturas": 1,
                "gas_facturas": 1,
            },
        }

    def seed(self, table: str, rows: list[dict]) -> None:
        for row in rows:
            r = dict(row)
            if "id" not in r:
                r["id"] = self._db["ids"][table]
                self._db["ids"][table] += 1
            self._db["tables"][table].append(r)

    def rows(self, table: str) -> list[dict]:
        return self._db["tables"][table]

    def table(self, name: str) -> _MockQuery:
        return _MockQuery(self._db, name)


# ── Tests de funciones puras ──────────────────────────────────────────────────

class TestLetraParaN:
    def test_primeras_letras(self):
        assert _letra_para_n(0) == "A"
        assert _letra_para_n(1) == "B"
        assert _letra_para_n(25) == "Z"

    def test_doble_letra(self):
        assert _letra_para_n(26) == "AA"
        assert _letra_para_n(27) == "AB"
        assert _letra_para_n(51) == "AZ"
        assert _letra_para_n(52) == "BA"

    def test_triple_letra(self):
        # 26 + 26*26 = 702 → AAA
        assert _letra_para_n(702) == "AAA"


class TestAgruparPorIdentificador:
    def test_agrupa_por_campo(self):
        facturas = [
            {"id": 1, "numero_servicio": "SVC-1"},
            {"id": 2, "numero_servicio": "SVC-1"},
            {"id": 3, "numero_servicio": "SVC-2"},
        ]
        grupos = _agrupar_por_identificador(facturas, "numero_servicio")
        assert set(grupos.keys()) == {"SVC-1", "SVC-2"}
        assert len(grupos["SVC-1"]) == 2
        assert len(grupos["SVC-2"]) == 1

    def test_none_a_sin_identificador(self):
        facturas = [{"id": 1, "numero_servicio": None}]
        grupos = _agrupar_por_identificador(facturas, "numero_servicio")
        assert "SIN_IDENTIFICADOR" in grupos

    def test_cadena_vacia_a_sin_identificador(self):
        facturas = [{"id": 1, "numero_servicio": ""}]
        grupos = _agrupar_por_identificador(facturas, "numero_servicio")
        assert "SIN_IDENTIFICADOR" in grupos

    def test_campo_ausente_a_sin_identificador(self):
        facturas = [{"id": 1}]
        grupos = _agrupar_por_identificador(facturas, "numero_servicio")
        assert "SIN_IDENTIFICADOR" in grupos

    def test_espacios_a_sin_identificador(self):
        facturas = [{"id": 1, "numero_servicio": "   "}]
        grupos = _agrupar_por_identificador(facturas, "numero_servicio")
        assert "SIN_IDENTIFICADOR" in grupos


class TestInicializarContadores:
    def test_cuenta_por_tipo(self):
        contratos = [
            {"tipo": "electrico", "identificador_real": "SVC-1"},
            {"tipo": "electrico", "identificador_real": "SVC-2"},
            {"tipo": "gas", "identificador_real": "GAS-1"},
        ]
        c = _inicializar_contadores(contratos)
        assert c["electrico"] == 2
        assert c["gas"] == 1

    def test_excluye_sin_identificador_explicitamente(self):
        contratos = [
            {"tipo": "electrico", "identificador_real": "SVC-1"},
            {"tipo": "electrico", "identificador_real": "SIN_IDENTIFICADOR"},
            {"tipo": "gas", "identificador_real": "SIN_IDENTIFICADOR"},
        ]
        c = _inicializar_contadores(contratos)
        # Solo SVC-1 cuenta para electrico; SIN_IDENTIFICADOR no suma
        assert c["electrico"] == 1
        assert c["gas"] == 0

    def test_sin_contratos(self):
        c = _inicializar_contadores([])
        assert c == {"electrico": 0, "gas": 0}


# ── Tests de integración con mock ─────────────────────────────────────────────

class TestMigracion:
    def test_migracion_basica_cfe(self):
        """Un cliente con 3 facturas CFE de un mismo servicio → 1 contrato, 3 asociadas."""
        db = _MockClient()
        db.seed("clientes", [{"id": 1, "nombre": "IBERICA"}])
        db.seed("cfe_facturas", [
            {"id": 1, "cliente_id": 1, "numero_servicio": "812990300016", "contrato_id": None},
            {"id": 2, "cliente_id": 1, "numero_servicio": "812990300016", "contrato_id": None},
            {"id": 3, "cliente_id": 1, "numero_servicio": "812990300016", "contrato_id": None},
        ])

        stats = migrar(db)

        assert stats["clientes_procesados"] == 1
        assert stats["contratos_creados"]["electrico"] == 1
        assert stats["facturas_asociadas"]["electrico"] == 3
        assert stats["facturas_saltadas"] == 0
        assert stats["errores"] == []

        contrato = db.rows("contratos")[0]
        assert contrato["nombre"] == "Contrato A"
        assert contrato["tipo"] == "electrico"
        assert contrato["identificador_real"] == "812990300016"

        for f in db.rows("cfe_facturas"):
            assert f["contrato_id"] == contrato["id"]

    def test_dos_servicios_cfe_crean_dos_contratos(self):
        """Dos numero_servicio distintos → Contrato A y Contrato B."""
        db = _MockClient()
        db.seed("clientes", [{"id": 1, "nombre": "IBERICA"}])
        db.seed("cfe_facturas", [
            {"id": 1, "cliente_id": 1, "numero_servicio": "SVC-1", "contrato_id": None},
            {"id": 2, "cliente_id": 1, "numero_servicio": "SVC-2", "contrato_id": None},
        ])

        stats = migrar(db)

        assert stats["contratos_creados"]["electrico"] == 2
        assert stats["facturas_asociadas"]["electrico"] == 2

        nombres = {c["nombre"] for c in db.rows("contratos")}
        assert nombres == {"Contrato A", "Contrato B"}

    def test_migracion_gas(self):
        """Facturas gas agrupadas por cuenta_contrato → contrato gas creado."""
        db = _MockClient()
        db.seed("clientes", [{"id": 1, "nombre": "IBERICA"}])
        db.seed("gas_facturas", [
            {"id": 1, "cliente_id": 1, "cuenta_contrato": "GAS-001", "contrato_id": None},
            {"id": 2, "cliente_id": 1, "cuenta_contrato": "GAS-001", "contrato_id": None},
        ])

        stats = migrar(db)

        assert stats["contratos_creados"]["gas"] == 1
        assert stats["facturas_asociadas"]["gas"] == 2

        contrato = db.rows("contratos")[0]
        assert contrato["nombre"] == "Contrato A"
        assert contrato["tipo"] == "gas"

    def test_idempotencia(self):
        """Ejecutar la migración dos veces no crea contratos duplicados."""
        db = _MockClient()
        db.seed("clientes", [{"id": 1, "nombre": "IBERICA"}])
        db.seed("cfe_facturas", [
            {"id": 1, "cliente_id": 1, "numero_servicio": "SVC-1", "contrato_id": None},
            {"id": 2, "cliente_id": 1, "numero_servicio": "SVC-1", "contrato_id": None},
        ])

        stats1 = migrar(db)
        stats2 = migrar(db)

        # Segunda corrida no crea contratos ni asocia facturas nuevas
        assert stats2["contratos_creados"]["electrico"] == 0
        assert stats2["facturas_asociadas"]["electrico"] == 0
        assert stats2["facturas_saltadas"] == 2

        # Solo existe 1 contrato
        assert len(db.rows("contratos")) == 1

    def test_contrato_preexistente_reutilizado(self):
        """Si el contrato ya existe antes de la migración, se reutiliza."""
        db = _MockClient()
        db.seed("clientes", [{"id": 1, "nombre": "IBERICA"}])
        db.seed("contratos", [
            {"id": 99, "cliente_id": 1, "nombre": "Contrato A",
             "tipo": "electrico", "identificador_real": "SVC-1"},
        ])
        db.seed("cfe_facturas", [
            {"id": 1, "cliente_id": 1, "numero_servicio": "SVC-1", "contrato_id": None},
        ])

        stats = migrar(db)

        assert stats["contratos_creados"]["electrico"] == 0  # no creó uno nuevo
        assert stats["facturas_asociadas"]["electrico"] == 1
        assert len(db.rows("contratos")) == 1

        assert db.rows("cfe_facturas")[0]["contrato_id"] == 99

    def test_sin_identificador_no_consume_letra(self):
        """El contrato 'Sin identificador' no afecta la secuencia de letras."""
        db = _MockClient()
        db.seed("clientes", [{"id": 1, "nombre": "IBERICA"}])
        db.seed("cfe_facturas", [
            {"id": 1, "cliente_id": 1, "numero_servicio": None, "contrato_id": None},
            {"id": 2, "cliente_id": 1, "numero_servicio": "SVC-1", "contrato_id": None},
        ])

        migrar(db)

        contratos = {c["identificador_real"]: c for c in db.rows("contratos")}
        assert contratos["SIN_IDENTIFICADOR"]["nombre"] == "Sin identificador"
        assert contratos["SVC-1"]["nombre"] == "Contrato A"  # no "Contrato B"

    def test_contrato_manual_afecta_letra(self):
        """Si el cliente ya tiene 'Contrato A' creado manualmente, el siguiente es 'Contrato B'."""
        db = _MockClient()
        db.seed("clientes", [{"id": 1, "nombre": "IBERICA"}])
        db.seed("contratos", [
            {"id": 10, "cliente_id": 1, "nombre": "Contrato A",
             "tipo": "electrico", "identificador_real": "SVC-EXISTENTE"},
        ])
        db.seed("cfe_facturas", [
            {"id": 1, "cliente_id": 1, "numero_servicio": "SVC-NUEVO", "contrato_id": None},
        ])

        migrar(db)

        nuevo = next(
            c for c in db.rows("contratos") if c["identificador_real"] == "SVC-NUEVO"
        )
        assert nuevo["nombre"] == "Contrato B"

    def test_facturas_ya_asociadas_saltadas(self):
        """Facturas con contrato_id ya asignado se cuentan como saltadas, no se tocan."""
        db = _MockClient()
        db.seed("clientes", [{"id": 1, "nombre": "IBERICA"}])
        db.seed("contratos", [
            {"id": 5, "cliente_id": 1, "nombre": "Contrato A",
             "tipo": "electrico", "identificador_real": "SVC-1"},
        ])
        db.seed("cfe_facturas", [
            {"id": 1, "cliente_id": 1, "numero_servicio": "SVC-1", "contrato_id": 5},
            {"id": 2, "cliente_id": 1, "numero_servicio": "SVC-1", "contrato_id": 5},
        ])

        stats = migrar(db)

        assert stats["facturas_saltadas"] == 2
        assert stats["facturas_asociadas"]["electrico"] == 0
        assert stats["contratos_creados"]["electrico"] == 0

    def test_multiples_clientes(self):
        """Dos clientes se procesan de forma independiente con sus propias letras."""
        db = _MockClient()
        db.seed("clientes", [
            {"id": 1, "nombre": "IBERICA"},
            {"id": 2, "nombre": "OTRO"},
        ])
        db.seed("cfe_facturas", [
            {"id": 1, "cliente_id": 1, "numero_servicio": "SVC-1", "contrato_id": None},
            {"id": 2, "cliente_id": 2, "numero_servicio": "SVC-2", "contrato_id": None},
        ])

        stats = migrar(db)

        assert stats["clientes_procesados"] == 2
        assert stats["contratos_creados"]["electrico"] == 2

        # Cada cliente tiene su propio "Contrato A"
        nombres = [c["nombre"] for c in db.rows("contratos")]
        assert nombres.count("Contrato A") == 2

    def test_resumen_sin_identificador_reportado(self):
        """Las facturas enviadas a 'Sin identificador' se contabilizan por separado."""
        db = _MockClient()
        db.seed("clientes", [{"id": 1, "nombre": "IBERICA"}])
        db.seed("cfe_facturas", [
            {"id": 1, "cliente_id": 1, "numero_servicio": "", "contrato_id": None},
            {"id": 2, "cliente_id": 1, "numero_servicio": "", "contrato_id": None},
        ])
        db.seed("gas_facturas", [
            {"id": 1, "cliente_id": 1, "cuenta_contrato": None, "contrato_id": None},
        ])

        stats = migrar(db)

        assert stats["facturas_sin_identificador"]["electrico"] == 2
        assert stats["facturas_sin_identificador"]["gas"] == 1
