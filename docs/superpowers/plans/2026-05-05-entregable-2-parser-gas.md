# Entregable 2 — Parser de Factura de Gas (ENGIE) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parsear las 12 facturas mensuales de gas natural (ENGIE/GDF Suez, RFC TRA0002119W1) en objetos `GasInvoice` tipados, persistirlos en SQLite y exponerlos via CLI.

**Architecture:** Un único parser concreto `ENGIEParser` (no hay otras tarifas de gas) que implementa `InvoiceParser.parse()` usando regex sobre el texto extraído por pdfplumber. El almacenamiento replica el patrón de CFE: `gas_facturas` + `gas_conceptos` en SQLite con valores Decimal guardados como TEXT. El CLI agrega `procesar_factura_gas()` paralelo a `procesar_factura_cfe()`.

**Tech Stack:** Python 3.9+, pdfplumber, sqlite3, dataclasses, Decimal, pytest

---

## Contexto del dominio

**Proveedor:** GDF SUEZ MEXICO COMERCIALIZADORA (marca ENGIE), RFC `TRA0002119W1`
**Cliente:** IBERICA TILES SAPI DE CV, RFC `ITI170630377`, número cliente `610002800`

**Estructura de la factura PDF (una sola página):**

```
FACTURA
www.engiemexico.com
FOLIO
GDF SUEZ MEXICO COMERCIALIZADORA
Blvd. Manuel Ávila Camacho No. 36, Piso 16, I00000547      ← folio al final
Col. Lomas de Chapultepec I Sección, Miguel Hidalgo
Ciudad de México, C.P. 11000 SAP 1004994897
...
11000, 2023-12-14T15:52:02                                  ← fecha emisión ISO
RFC TRA0002119W1                                            ← RFC proveedor (solo en su línea)
PERIODO DE CONSUMO
FACTURA 59030c00-01f5-4dc9-bda1-25d579b23095 De 01.11.2023 a 30.11.2023
NÚMERO DE CLIENTE CUENTA CONTRATO FECHA LÍMITE DE PAGO
610002800 5100096634 25.12.2023
...
RFC MÉTODO DE PAGO FORMA DE PAGO USO DE CFDI
ITI170630377 PPD ...                                        ← RFC cliente + PPD
PUNTO DE SUMINISTRO TIPO DE SERVICIO ...
IBERICA TILES SAPI DE CV COMERCIALIZACION DE GAS - ...
TIPO DE MEDIDOR NÚMERO DE CASETA TIPO DE LECTURA
11067 11067-01 REAL
CONSUMO M3 CORREGIDOS CONSUMO M3 SIN CORREGIR PODER CALORÍFICO
2,960,411.81 0.00 0.035958531,Gj/m3
...
83101601 Compraventa de Gas Natural  01.11.2023 30.11.2023 106,445.1830 GJ $54.8500 $5,838,518.28
78102101 Transporte por Ducto Gas Natural 01.11.2023 30.11.2023 106,445.1830 GJ $24.6300 $2,621,744.85
SUB-TOTAL: 8,460,263.13
TASA IVA 16 % 1,353,642.10
TOTAL :$ 9,813,905.23
```

**Valores esperados fixture (Nov 2023):**
- uuid_cfdi: `59030c00-01f5-4dc9-bda1-25d579b23095`
- folio: `I00000547`
- fecha_emision: `date(2023, 12, 14)`
- periodo_inicio: `date(2023, 11, 1)`, periodo_fin: `date(2023, 11, 30)`
- fecha_limite_pago: `date(2023, 12, 25)`
- nombre_proveedor: `GDF SUEZ MEXICO COMERCIALIZADORA`
- rfc_proveedor: `TRA0002119W1`
- nombre_cliente: `IBERICA TILES`
- rfc_cliente: `ITI170630377`
- numero_cliente: `610002800`, cuenta_contrato: `5100096634`
- punto_suministro: `IBERICA TILES SAPI DE CV`
- numero_caseta: `11067-01`, tipo_lectura: `REAL`
- consumo_m3_corregidos: `Decimal("2960411.81")`
- consumo_sin_corregir_m3: `Decimal("0")`
- poder_calorifico_gj_m3: `Decimal("0.035958531")`
- consumo_total_gj: `Decimal("106445.1830")`
- costo_unitario_total_gj: `Decimal("79.4800")` (54.85 + 24.63)
- subtotal_mxn: `Decimal("8460263.13")`
- iva_mxn: `Decimal("1353642.10")`
- total_mxn: `Decimal("9813905.23")`

---

## Estructura de archivos

| Archivo | Acción | Responsabilidad |
|---------|--------|----------------|
| `parsers/gas/__init__.py` | Crear | Factory `get_gas_parser()` |
| `parsers/gas/engie.py` | Crear | `ENGIEParser` — regex + parse + validate |
| `storage/schema.py` | Modificar | Agregar tablas `gas_facturas` y `gas_conceptos` |
| `storage/repository.py` | Modificar | `save_gas_invoice`, `load_gas_invoice`, `list_gas_invoices` |
| `cli/main.py` | Modificar | Agregar `procesar_factura_gas()` |
| `tests/parsers/test_engie.py` | Crear | 20 tests contra fixture Nov 2023 |
| `tests/storage/test_repository_gas.py` | Crear | 6 tests de persistencia gas |
| `tests/test_cli_gas.py` | Crear | 3 tests CLI gas |

---

## Task 1: Parser ENGIE — parsers/gas/

**Files:**
- Create: `parsers/gas/__init__.py`
- Create: `parsers/gas/engie.py`
- Create: `tests/parsers/test_engie.py`

- [ ] **Step 1: Escribir los tests fallidos**

```python
# tests/parsers/test_engie.py
from __future__ import annotations
import pytest
from datetime import date
from decimal import Decimal
from pathlib import Path

from parsers.gas import get_gas_parser
from parsers.gas.engie import ENGIEParser
from models.gas_invoice import GasInvoice, GasConcepto

FIXTURE = Path("invoices/Gas/TRA0002119W1_I_I0000054727751484 Nov 23.pdf")


@pytest.fixture(scope="module")
def inv():
    return get_gas_parser().parse(FIXTURE)


def test_parse_devuelve_gas_invoice(inv):
    assert isinstance(inv, GasInvoice)


def test_uuid_cfdi(inv):
    assert inv.uuid_cfdi.lower() == "59030c00-01f5-4dc9-bda1-25d579b23095"


def test_folio(inv):
    assert inv.folio == "I00000547"


def test_fecha_emision(inv):
    assert inv.fecha_emision == date(2023, 12, 14)


def test_periodo_inicio(inv):
    assert inv.periodo_inicio == date(2023, 11, 1)


def test_periodo_fin(inv):
    assert inv.periodo_fin == date(2023, 11, 30)


def test_fecha_limite_pago(inv):
    assert inv.fecha_limite_pago == date(2023, 12, 25)


def test_rfc_proveedor(inv):
    assert inv.rfc_proveedor == "TRA0002119W1"


def test_rfc_cliente(inv):
    assert inv.rfc_cliente == "ITI170630377"


def test_numero_cliente(inv):
    assert inv.numero_cliente == "610002800"


def test_cuenta_contrato(inv):
    assert inv.cuenta_contrato == "5100096634"


def test_consumo_m3(inv):
    assert inv.consumo_m3_corregidos == Decimal("2960411.81")


def test_poder_calorifico(inv):
    assert inv.poder_calorifico_gj_m3 == Decimal("0.035958531")


def test_consumo_total_gj(inv):
    assert inv.consumo_total_gj == Decimal("106445.1830")


def test_dos_conceptos(inv):
    assert len(inv.conceptos) == 2


def test_concepto_compraventa(inv):
    c = next(x for x in inv.conceptos if x.clave_producto == "83101601")
    assert c.descripcion == "Compraventa de Gas Natural"
    assert c.cantidad_gj == Decimal("106445.1830")
    assert c.precio_unitario_gj == Decimal("54.8500")
    assert c.importe_mxn == Decimal("5838518.28")


def test_concepto_transporte(inv):
    c = next(x for x in inv.conceptos if x.clave_producto == "78102101")
    assert c.descripcion == "Transporte por Ducto Gas Natural"
    assert c.precio_unitario_gj == Decimal("24.6300")
    assert c.importe_mxn == Decimal("2621744.85")


def test_costo_unitario_total(inv):
    assert inv.costo_unitario_total_gj == Decimal("79.4800")


def test_subtotal(inv):
    assert inv.subtotal_mxn == Decimal("8460263.13")


def test_iva(inv):
    assert inv.iva_mxn == Decimal("1353642.10")


def test_total(inv):
    assert inv.total_mxn == Decimal("9813905.23")


def test_validacion_sin_errores(inv):
    parser = get_gas_parser()
    assert parser.validate(inv) == []


def test_factory_devuelve_engie_parser():
    assert isinstance(get_gas_parser(), ENGIEParser)
```

- [ ] **Step 2: Verificar que los tests fallan**

```bash
python3 -m pytest tests/parsers/test_engie.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'parsers.gas'`

- [ ] **Step 3: Crear `parsers/gas/__init__.py`**

```python
# parsers/gas/__init__.py
from __future__ import annotations

from parsers.gas.engie import ENGIEParser


def get_gas_parser() -> ENGIEParser:
    """Devuelve el parser para facturas de gas ENGIE/GDF Suez."""
    return ENGIEParser()
```

- [ ] **Step 4: Crear `parsers/gas/engie.py`**

```python
# parsers/gas/engie.py
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

import pdfplumber

from models.gas_invoice import GasConcepto, GasInvoice
from parsers.base import InvoiceParser

# ── Regex ────────────────────────────────────────────────────────────────────
RE_UUID = re.compile(
    r'FACTURA\s+([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}'
    r'-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})'
)
# Folio aparece al final de la línea de dirección: "...Piso 16, I00000547"
RE_FOLIO = re.compile(r',\s*(I\d+)\s*$', re.MULTILINE)
# Fecha emisión en ISO: "11000, 2023-12-14T15:52:02"
RE_FECHA_EMISION = re.compile(r'(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}')
# Periodo: "De 01.11.2023 a 30.11.2023"
RE_PERIODO = re.compile(r'De\s+(\d{2}\.\d{2}\.\d{4})\s+a\s+(\d{2}\.\d{2}\.\d{4})')
# Bloque: "NÚMERO DE CLIENTE CUENTA CONTRATO FECHA LÍMITE DE PAGO\n610002800 5100096634 25.12.2023"
RE_CLIENTE_BLOQUE = re.compile(
    r'N[ÚU]MERO\s+DE\s+CLIENTE\s+CUENTA\s+CONTRATO\s+FECHA\s+L[IÍ]MITE\s+DE\s+PAGO'
    r'\s*\n(\d+)\s+(\d+)\s+(\d{2}\.\d{2}\.\d{4})',
    re.IGNORECASE,
)
# RFC proveedor: línea propia "RFC TRA0002119W1"
RE_RFC_PROVEEDOR = re.compile(r'^RFC\s+([A-Z&]{3,4}\d{6}[A-Z0-9]{3})\s*$', re.MULTILINE)
# RFC cliente: siguiente línea después de "RFC MÉTODO DE PAGO ..." comienza con el RFC + PPD
RE_RFC_CLIENTE = re.compile(r'^([A-Z&]{3,4}\d{6}[A-Z0-9]{3})\s+PPD\b', re.MULTILINE)
# Nombre proveedor: primera línea después de "FOLIO"
RE_NOMBRE_PROVEEDOR = re.compile(r'FOLIO\s*\n(.+)\n', re.IGNORECASE)
# Nombre cliente: primera línea después de "CLIENTE Y DOMICILIO"
RE_NOMBRE_CLIENTE = re.compile(r'CLIENTE\s+Y\s+DOMICILIO\s*\n(.+)', re.IGNORECASE)
# Punto suministro: antes de "COMERCIALIZACION"
RE_PUNTO_SUMINISTRO = re.compile(
    r'PUNTO\s+DE\s+SUMINISTRO.*?\n(.+?)\s+COMERCIALIZACION',
    re.IGNORECASE,
)
# Bloque medidor: "TIPO DE MEDIDOR NÚMERO DE CASETA TIPO DE LECTURA\n11067 11067-01 REAL"
RE_MEDIDOR_BLOQUE = re.compile(
    r'TIPO\s+DE\s+MEDIDOR\s+N[ÚU]MERO\s+DE\s+CASETA\s+TIPO\s+DE\s+LECTURA'
    r'\s*\n\d+\s+(\S+)\s+(\w+)',
    re.IGNORECASE,
)
# Consumo: "2,960,411.81 0.00 0.035958531,Gj/m3"
RE_CONSUMO_BLOQUE = re.compile(
    r'CONSUMO\s+M3\s+CORREGIDOS.*?\n([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d.]+),Gj/m3',
    re.IGNORECASE | re.DOTALL,
)
# Líneas de conceptos
RE_COMPRAVENTA = re.compile(
    r'83101601\s+Compraventa de Gas Natural'
    r'\s+[\d.]+\s+[\d.]+\s+([\d,.]+)\s+GJ\s+\$([\d,.]+)\s+\$([\d,.]+)'
)
RE_TRANSPORTE = re.compile(
    r'78102101\s+Transporte por Ducto Gas Natural'
    r'\s+[\d.]+\s+[\d.]+\s+([\d,.]+)\s+GJ\s+\$([\d,.]+)\s+\$([\d,.]+)'
)
RE_SUBTOTAL = re.compile(r'SUB-TOTAL:\s*([\d,]+\.?\d*)')
RE_IVA = re.compile(r'TASA\s+IVA\s+16\s*%\s+([\d,]+\.?\d*)')
RE_TOTAL = re.compile(r'TOTAL\s*:\$\s*([\d,]+\.?\d*)')


def _parse_decimal(texto: str) -> Decimal:
    try:
        return Decimal(texto.strip().replace(",", ""))
    except InvalidOperation:
        raise ValueError(f"No se puede convertir a Decimal: '{texto}'")


def _parse_fecha(texto: str) -> date:
    """Convierte 'DD.MM.YYYY' a date."""
    d, m, y = texto.strip().split(".")
    return date(int(y), int(m), int(d))


class ENGIEParser(InvoiceParser):
    """Parser para facturas de gas natural ENGIE / GDF Suez Mexico."""

    def parse(self, pdf_path: Path) -> GasInvoice:
        pdf_path = Path(pdf_path)
        advertencias: list[str] = []

        with pdfplumber.open(pdf_path) as pdf:
            texto = pdf.pages[0].extract_text() or ""

        def _req(patron: re.Pattern, nombre: str) -> str | None:
            m = patron.search(texto)
            if m:
                return m.group(1).strip()
            advertencias.append(f"Campo no encontrado: {nombre}")
            return None

        def _d(raw: str | None) -> Decimal:
            return _parse_decimal(raw) if raw else Decimal("0")

        # UUID
        uuid_raw = _req(RE_UUID, "uuid_cfdi") or ""

        # Fecha de emisión
        m_emision = RE_FECHA_EMISION.search(texto)
        if m_emision:
            y, mo, d = m_emision.group(1).split("-")
            fecha_emision = date(int(y), int(mo), int(d))
        else:
            advertencias.append("Campo no encontrado: fecha_emision")
            fecha_emision = date.today()

        # Periodo
        m_periodo = RE_PERIODO.search(texto)
        if m_periodo:
            periodo_inicio = _parse_fecha(m_periodo.group(1))
            periodo_fin    = _parse_fecha(m_periodo.group(2))
        else:
            advertencias.append("Campo no encontrado: periodo")
            periodo_inicio = periodo_fin = date.today()

        # Bloque cliente: número de cliente, cuenta contrato, fecha límite
        m_bloque = RE_CLIENTE_BLOQUE.search(texto)
        if m_bloque:
            numero_cliente  = m_bloque.group(1)
            cuenta_contrato = m_bloque.group(2)
            fecha_limite    = _parse_fecha(m_bloque.group(3))
        else:
            advertencias.append("Campo no encontrado: bloque_cliente")
            numero_cliente = cuenta_contrato = ""
            fecha_limite = periodo_fin

        # Medidor / caseta / lectura
        m_med = RE_MEDIDOR_BLOQUE.search(texto)
        if m_med:
            numero_caseta = m_med.group(1)
            tipo_lectura  = m_med.group(2)
        else:
            advertencias.append("Campo no encontrado: medidor")
            numero_caseta = tipo_lectura = ""

        # Consumo
        m_consumo = RE_CONSUMO_BLOQUE.search(texto)
        if m_consumo:
            consumo_m3  = _parse_decimal(m_consumo.group(1))
            consumo_sin = _parse_decimal(m_consumo.group(2))
            poder_cal   = Decimal(m_consumo.group(3).strip())
        else:
            advertencias.append("Campo no encontrado: consumo_bloque")
            consumo_m3 = consumo_sin = poder_cal = Decimal("0")

        # Conceptos
        conceptos: list[GasConcepto] = []
        m_comp = RE_COMPRAVENTA.search(texto)
        if m_comp:
            conceptos.append(GasConcepto(
                descripcion="Compraventa de Gas Natural",
                clave_producto="83101601",
                cantidad_gj=_parse_decimal(m_comp.group(1)),
                precio_unitario_gj=_parse_decimal(m_comp.group(2)),
                importe_mxn=_parse_decimal(m_comp.group(3)),
            ))
        else:
            advertencias.append("Campo no encontrado: compraventa")

        m_trans = RE_TRANSPORTE.search(texto)
        if m_trans:
            conceptos.append(GasConcepto(
                descripcion="Transporte por Ducto Gas Natural",
                clave_producto="78102101",
                cantidad_gj=_parse_decimal(m_trans.group(1)),
                precio_unitario_gj=_parse_decimal(m_trans.group(2)),
                importe_mxn=_parse_decimal(m_trans.group(3)),
            ))
        else:
            advertencias.append("Campo no encontrado: transporte")

        consumo_total_gj    = conceptos[0].cantidad_gj if conceptos else Decimal("0")
        costo_unitario_total = sum((c.precio_unitario_gj for c in conceptos), Decimal("0"))

        return GasInvoice(
            uuid_cfdi=uuid_raw,
            folio=_req(RE_FOLIO, "folio") or "",
            fecha_emision=fecha_emision,
            periodo_inicio=periodo_inicio,
            periodo_fin=periodo_fin,
            fecha_limite_pago=fecha_limite,
            nombre_proveedor=_req(RE_NOMBRE_PROVEEDOR, "nombre_proveedor") or "",
            rfc_proveedor=_req(RE_RFC_PROVEEDOR, "rfc_proveedor") or "",
            nombre_cliente=_req(RE_NOMBRE_CLIENTE, "nombre_cliente") or "",
            rfc_cliente=_req(RE_RFC_CLIENTE, "rfc_cliente") or "",
            numero_cliente=numero_cliente,
            cuenta_contrato=cuenta_contrato,
            punto_suministro=_req(RE_PUNTO_SUMINISTRO, "punto_suministro") or "",
            numero_caseta=numero_caseta,
            tipo_lectura=tipo_lectura,
            consumo_m3_corregidos=consumo_m3,
            consumo_sin_corregir_m3=consumo_sin,
            poder_calorifico_gj_m3=poder_cal,
            consumo_total_gj=consumo_total_gj,
            conceptos=conceptos,
            costo_unitario_total_gj=costo_unitario_total,
            subtotal_mxn=_d(_req(RE_SUBTOTAL, "subtotal")),
            iva_mxn=_d(_req(RE_IVA, "iva")),
            total_mxn=_d(_req(RE_TOTAL, "total")),
            pdf_path=str(pdf_path),
            advertencias=advertencias,
        )

    def validate(self, invoice: GasInvoice) -> list[str]:
        """Valida coherencia interna. Devuelve lista de errores (vacía = válido)."""
        errores = []
        if invoice.periodo_fin <= invoice.periodo_inicio:
            errores.append("periodo_fin debe ser posterior a periodo_inicio")
        suma = sum(c.importe_mxn for c in invoice.conceptos)
        if abs(suma - invoice.subtotal_mxn) > Decimal("1.00"):
            errores.append(
                f"Subtotal no cuadra: suma_conceptos={suma}, subtotal={invoice.subtotal_mxn}"
            )
        total_calc = invoice.subtotal_mxn + invoice.iva_mxn
        if abs(total_calc - invoice.total_mxn) > Decimal("1.00"):
            errores.append(
                f"Total no cuadra: calculado={total_calc}, factura={invoice.total_mxn}"
            )
        return errores
```

- [ ] **Step 5: Correr los tests**

```bash
python3 -m pytest tests/parsers/test_engie.py -v
```
Expected: 22 tests PASS, 0 FAIL

- [ ] **Step 6: Commit**

```bash
git add parsers/gas/ tests/parsers/test_engie.py
git commit -m "feat: add ENGIE gas invoice parser (Task 1)"
```

---

## Task 2: Storage — tablas gas en SQLite

**Files:**
- Modify: `storage/schema.py`
- Create: `tests/storage/test_schema_gas.py`

- [ ] **Step 1: Escribir los tests fallidos**

```python
# tests/storage/test_schema_gas.py
from __future__ import annotations
import sqlite3
import pytest
from storage.schema import init_db


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    init_db(c)
    yield c
    c.close()


def test_gas_facturas_existe(conn):
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='gas_facturas'")
    assert cur.fetchone() is not None


def test_gas_conceptos_existe(conn):
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='gas_conceptos'")
    assert cur.fetchone() is not None


def test_gas_facturas_columnas(conn):
    cur = conn.execute("PRAGMA table_info(gas_facturas)")
    cols = {row[1] for row in cur.fetchall()}
    for expected in ("id", "cliente_id", "uuid_cfdi", "folio", "periodo_inicio",
                     "consumo_total_gj", "costo_unitario_total_gj", "subtotal_mxn",
                     "iva_mxn", "total_mxn", "advertencias"):
        assert expected in cols, f"Columna faltante: {expected}"


def test_gas_conceptos_fk_cascade(conn):
    """Borrar gas_factura elimina sus conceptos (ON DELETE CASCADE)."""
    conn.execute("INSERT INTO clientes (nombre, rfc) VALUES ('Test', 'TST010101AAA')")
    conn.execute(
        "INSERT INTO gas_facturas (cliente_id, uuid_cfdi, folio, fecha_emision, "
        "periodo_inicio, periodo_fin, fecha_limite_pago, nombre_proveedor, rfc_proveedor, "
        "numero_cliente, cuenta_contrato, punto_suministro, numero_caseta, tipo_lectura, "
        "consumo_m3_corregidos, consumo_sin_corregir_m3, poder_calorifico_gj_m3, "
        "consumo_total_gj, costo_unitario_total_gj, subtotal_mxn, iva_mxn, total_mxn, "
        "pdf_path, advertencias) "
        "VALUES (1,'uuid','F1','2023-01-01','2023-01-01','2023-01-31','2023-02-01',"
        "'PROV','TRA0002119W1','100','200','PUNTO','C1','REAL',"
        "'100','0','0.036','3.6','79.48','100','16','116','x.pdf','[]')"
    )
    conn.execute(
        "INSERT INTO gas_conceptos (factura_id, descripcion, clave_producto, "
        "cantidad_gj, precio_unitario_gj, importe_mxn) VALUES (1,'Compraventa','83101601','3.6','54.85','197.46')"
    )
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("DELETE FROM gas_facturas WHERE id = 1")
    conn.commit()
    cur = conn.execute("SELECT COUNT(*) FROM gas_conceptos WHERE factura_id = 1")
    assert cur.fetchone()[0] == 0
```

- [ ] **Step 2: Verificar que los tests fallan**

```bash
python3 -m pytest tests/storage/test_schema_gas.py -v 2>&1 | head -20
```
Expected: `AssertionError` — tablas no existen aún

- [ ] **Step 3: Agregar tablas a `storage/schema.py`**

Localizar la función `init_db` y agregar al final del SQL (después de `cfe_mem_componentes`):

```python
    conn.executescript("""
        ...existing tables...

        CREATE TABLE IF NOT EXISTS gas_facturas (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id               INTEGER NOT NULL REFERENCES clientes(id),
            uuid_cfdi                TEXT,
            folio                    TEXT    NOT NULL,
            fecha_emision            TEXT    NOT NULL,
            periodo_inicio           TEXT    NOT NULL,
            periodo_fin              TEXT    NOT NULL,
            fecha_limite_pago        TEXT    NOT NULL,
            nombre_proveedor         TEXT    NOT NULL,
            rfc_proveedor            TEXT    NOT NULL,
            numero_cliente           TEXT    NOT NULL,
            cuenta_contrato          TEXT    NOT NULL,
            punto_suministro         TEXT    NOT NULL,
            numero_caseta            TEXT    NOT NULL,
            tipo_lectura             TEXT    NOT NULL,
            consumo_m3_corregidos    TEXT    NOT NULL,
            consumo_sin_corregir_m3  TEXT    NOT NULL,
            poder_calorifico_gj_m3   TEXT    NOT NULL,
            consumo_total_gj         TEXT    NOT NULL,
            costo_unitario_total_gj  TEXT    NOT NULL,
            subtotal_mxn             TEXT    NOT NULL,
            iva_mxn                  TEXT    NOT NULL,
            total_mxn                TEXT    NOT NULL,
            pdf_path                 TEXT    NOT NULL,
            advertencias             TEXT    NOT NULL DEFAULT '[]',
            created_at               TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS gas_conceptos (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            factura_id          INTEGER NOT NULL REFERENCES gas_facturas(id) ON DELETE CASCADE,
            descripcion         TEXT    NOT NULL,
            clave_producto      TEXT    NOT NULL,
            cantidad_gj         TEXT    NOT NULL,
            precio_unitario_gj  TEXT    NOT NULL,
            importe_mxn         TEXT    NOT NULL
        );
    """)
```

> **Nota:** Agregar solo las dos nuevas tablas al bloque `executescript` existente, no reemplazar las tablas CFE.

- [ ] **Step 4: Correr los tests**

```bash
python3 -m pytest tests/storage/test_schema_gas.py tests/storage/test_schema.py -v
```
Expected: todos PASS (los 4 originales + los 4 nuevos)

- [ ] **Step 5: Commit**

```bash
git add storage/schema.py tests/storage/test_schema_gas.py
git commit -m "feat: add gas_facturas and gas_conceptos tables to schema (Task 2)"
```

---

## Task 3: Storage — repository para facturas de gas

**Files:**
- Modify: `storage/repository.py`
- Create: `tests/storage/test_repository_gas.py`

- [ ] **Step 1: Escribir los tests fallidos**

```python
# tests/storage/test_repository_gas.py
from __future__ import annotations
import sqlite3
import pytest
from datetime import date
from decimal import Decimal
from pathlib import Path

from models.gas_invoice import GasInvoice, GasConcepto
from storage.schema import init_db
from storage.repository import save_gas_invoice, load_gas_invoice, list_gas_invoices
from parsers.gas import get_gas_parser

FIXTURE = Path("invoices/Gas/TRA0002119W1_I_I0000054727751484 Nov 23.pdf")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    init_db(c)
    yield c
    c.close()


@pytest.fixture
def inv():
    return get_gas_parser().parse(FIXTURE)


def test_save_devuelve_id(conn, inv):
    fid = save_gas_invoice(conn, inv)
    assert isinstance(fid, int) and fid > 0


def test_load_recupera_campos_simples(conn, inv):
    fid = save_gas_invoice(conn, inv)
    cargada = load_gas_invoice(conn, fid)
    assert cargada.uuid_cfdi.lower() == "59030c00-01f5-4dc9-bda1-25d579b23095"
    assert cargada.periodo_inicio == date(2023, 11, 1)
    assert cargada.consumo_total_gj == Decimal("106445.1830")
    assert cargada.subtotal_mxn == Decimal("8460263.13")
    assert cargada.total_mxn == Decimal("9813905.23")


def test_load_recupera_conceptos(conn, inv):
    fid = save_gas_invoice(conn, inv)
    cargada = load_gas_invoice(conn, fid)
    assert len(cargada.conceptos) == 2
    claves = {c.clave_producto for c in cargada.conceptos}
    assert claves == {"83101601", "78102101"}


def test_load_factura_inexistente(conn):
    with pytest.raises(ValueError, match="Factura de gas"):
        load_gas_invoice(conn, 9999)


def test_list_devuelve_facturas(conn, inv):
    save_gas_invoice(conn, inv)
    rows = list_gas_invoices(conn)
    assert len(rows) == 1
    assert rows[0]["folio"] == "I00000547"


def test_mismo_cliente_no_duplica(conn, inv):
    save_gas_invoice(conn, inv)
    save_gas_invoice(conn, inv)
    cur = conn.execute("SELECT COUNT(*) FROM clientes WHERE rfc = 'ITI170630377'")
    assert cur.fetchone()[0] == 1
```

- [ ] **Step 2: Verificar que los tests fallan**

```bash
python3 -m pytest tests/storage/test_repository_gas.py -v 2>&1 | head -20
```
Expected: `ImportError: cannot import name 'save_gas_invoice'`

- [ ] **Step 3: Agregar funciones a `storage/repository.py`**

Agregar al final del archivo (después de las funciones CFE existentes):

```python
# ── Gas invoices ─────────────────────────────────────────────────────────────

def save_gas_invoice(conn: sqlite3.Connection, invoice: GasInvoice) -> int:
    """Persiste una GasInvoice completa. Devuelve el id de gas_facturas."""
    from models.gas_invoice import GasInvoice as _GI  # evita circular en type check
    cliente_id = _upsert_cliente(conn, invoice.nombre_cliente, invoice.rfc_cliente)
    cur = conn.execute(
        """INSERT INTO gas_facturas (
            cliente_id, uuid_cfdi, folio, fecha_emision, periodo_inicio, periodo_fin,
            fecha_limite_pago, nombre_proveedor, rfc_proveedor, numero_cliente,
            cuenta_contrato, punto_suministro, numero_caseta, tipo_lectura,
            consumo_m3_corregidos, consumo_sin_corregir_m3, poder_calorifico_gj_m3,
            consumo_total_gj, costo_unitario_total_gj,
            subtotal_mxn, iva_mxn, total_mxn, pdf_path, advertencias
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            cliente_id,
            invoice.uuid_cfdi,
            invoice.folio,
            invoice.fecha_emision.isoformat(),
            invoice.periodo_inicio.isoformat(),
            invoice.periodo_fin.isoformat(),
            invoice.fecha_limite_pago.isoformat(),
            invoice.nombre_proveedor,
            invoice.rfc_proveedor,
            invoice.numero_cliente,
            invoice.cuenta_contrato,
            invoice.punto_suministro,
            invoice.numero_caseta,
            invoice.tipo_lectura,
            str(invoice.consumo_m3_corregidos),
            str(invoice.consumo_sin_corregir_m3),
            str(invoice.poder_calorifico_gj_m3),
            str(invoice.consumo_total_gj),
            str(invoice.costo_unitario_total_gj),
            str(invoice.subtotal_mxn),
            str(invoice.iva_mxn),
            str(invoice.total_mxn),
            invoice.pdf_path,
            json.dumps(invoice.advertencias),
        ),
    )
    conn.commit()
    factura_id = cur.lastrowid

    for c in invoice.conceptos:
        conn.execute(
            """INSERT INTO gas_conceptos
               (factura_id, descripcion, clave_producto, cantidad_gj, precio_unitario_gj, importe_mxn)
               VALUES (?,?,?,?,?,?)""",
            (
                factura_id,
                c.descripcion,
                c.clave_producto,
                str(c.cantidad_gj),
                str(c.precio_unitario_gj),
                str(c.importe_mxn),
            ),
        )
    conn.commit()
    return factura_id


def load_gas_invoice(conn: sqlite3.Connection, factura_id: int) -> GasInvoice:
    """Carga una GasInvoice completa desde SQLite. Lanza ValueError si no existe."""
    from models.gas_invoice import GasConcepto, GasInvoice
    from datetime import date as _date

    row = conn.execute(
        "SELECT * FROM gas_facturas WHERE id = ?", (factura_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Factura de gas con id={factura_id} no encontrada")

    cols = [d[0] for d in conn.execute("SELECT * FROM gas_facturas WHERE id = ?", (factura_id,)).description]

    # Reconstruir usando nombre de columna
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM gas_facturas WHERE id = ?", (factura_id,)).fetchone()

    conceptos_rows = conn.execute(
        "SELECT * FROM gas_conceptos WHERE factura_id = ? ORDER BY id", (factura_id,)
    ).fetchall()
    conceptos = [
        GasConcepto(
            descripcion=c["descripcion"],
            clave_producto=c["clave_producto"],
            cantidad_gj=Decimal(c["cantidad_gj"]),
            precio_unitario_gj=Decimal(c["precio_unitario_gj"]),
            importe_mxn=Decimal(c["importe_mxn"]),
        )
        for c in conceptos_rows
    ]

    invoice = GasInvoice(
        uuid_cfdi=row["uuid_cfdi"] or "",
        folio=row["folio"],
        fecha_emision=_date.fromisoformat(row["fecha_emision"]),
        periodo_inicio=_date.fromisoformat(row["periodo_inicio"]),
        periodo_fin=_date.fromisoformat(row["periodo_fin"]),
        fecha_limite_pago=_date.fromisoformat(row["fecha_limite_pago"]),
        nombre_proveedor=row["nombre_proveedor"],
        rfc_proveedor=row["rfc_proveedor"],
        nombre_cliente="",  # no almacenado en gas_facturas, viene de clientes
        rfc_cliente="",
        numero_cliente=row["numero_cliente"],
        cuenta_contrato=row["cuenta_contrato"],
        punto_suministro=row["punto_suministro"],
        numero_caseta=row["numero_caseta"],
        tipo_lectura=row["tipo_lectura"],
        consumo_m3_corregidos=Decimal(row["consumo_m3_corregidos"]),
        consumo_sin_corregir_m3=Decimal(row["consumo_sin_corregir_m3"]),
        poder_calorifico_gj_m3=Decimal(row["poder_calorifico_gj_m3"]),
        consumo_total_gj=Decimal(row["consumo_total_gj"]),
        conceptos=conceptos,
        costo_unitario_total_gj=Decimal(row["costo_unitario_total_gj"]),
        subtotal_mxn=Decimal(row["subtotal_mxn"]),
        iva_mxn=Decimal(row["iva_mxn"]),
        total_mxn=Decimal(row["total_mxn"]),
        pdf_path=row["pdf_path"],
        advertencias=json.loads(row["advertencias"]),
    )
    conn.row_factory = None
    return invoice


def list_gas_invoices(conn: sqlite3.Connection) -> list[dict]:
    """Devuelve resumen de todas las facturas de gas guardadas."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT gf.id, gf.folio, gf.periodo_inicio, gf.periodo_fin,
                  gf.consumo_total_gj, gf.total_mxn, c.rfc AS rfc_cliente
           FROM gas_facturas gf
           JOIN clientes c ON c.id = gf.cliente_id
           ORDER BY gf.periodo_inicio"""
    ).fetchall()
    conn.row_factory = None
    return [dict(r) for r in rows]
```

> **Nota importante:** `load_gas_invoice` usa `conn.row_factory = sqlite3.Row` para acceso por nombre de columna. Al terminar, restablece `conn.row_factory = None` para no afectar otras consultas. El campo `nombre_cliente` y `rfc_cliente` no se almacenan en `gas_facturas` (están en `clientes`) — se dejan como strings vacíos en el objeto cargado. Si se necesitan, hacer JOIN con `clientes`.

- [ ] **Step 4: Correr los tests**

```bash
python3 -m pytest tests/storage/test_repository_gas.py tests/storage/test_repository.py -v
```
Expected: todos PASS (8 originales + 6 nuevos)

- [ ] **Step 5: Commit**

```bash
git add storage/repository.py tests/storage/test_repository_gas.py
git commit -m "feat: add gas invoice persistence to repository (Task 3)"
```

---

## Task 4: CLI — procesar_factura_gas

**Files:**
- Modify: `cli/main.py`
- Create: `tests/test_cli_gas.py`

- [ ] **Step 1: Escribir los tests fallidos**

```python
# tests/test_cli_gas.py
from __future__ import annotations
import sqlite3
import pytest
from pathlib import Path

from storage.schema import init_db
from storage.repository import load_gas_invoice
from cli.main import procesar_factura_gas

FIXTURE = Path("invoices/Gas/TRA0002119W1_I_I0000054727751484 Nov 23.pdf")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    init_db(c)
    yield c
    c.close()


def test_procesar_factura_gas_devuelve_id(conn):
    fid = procesar_factura_gas(FIXTURE, conn)
    assert isinstance(fid, int) and fid > 0


def test_factura_gas_persiste_en_db(conn):
    fid = procesar_factura_gas(FIXTURE, conn)
    inv = load_gas_invoice(conn, fid)
    assert inv.folio == "I00000547"


def test_pdf_gas_inexistente_lanza_error(conn):
    with pytest.raises(FileNotFoundError):
        procesar_factura_gas(Path("invoices/Gas/no_existe.pdf"), conn)
```

- [ ] **Step 2: Verificar que los tests fallan**

```bash
python3 -m pytest tests/test_cli_gas.py -v 2>&1 | head -20
```
Expected: `ImportError: cannot import name 'procesar_factura_gas'`

- [ ] **Step 3: Agregar `procesar_factura_gas` a `cli/main.py`**

Agregar al final del archivo (después de `procesar_factura_cfe`):

```python
def procesar_factura_gas(pdf_path: Path, conn: sqlite3.Connection) -> int:
    """Parsea y persiste una factura de gas ENGIE.

    Args:
        pdf_path: ruta al PDF.
        conn: conexión SQLite inicializada con init_db().

    Returns:
        id de la fila en gas_facturas.

    Raises:
        FileNotFoundError: si el PDF no existe.
    """
    from parsers.gas import get_gas_parser
    from storage.repository import save_gas_invoice

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF no encontrado: {pdf_path}")

    parser = get_gas_parser()
    invoice = parser.parse(pdf_path)
    errores = parser.validate(invoice)

    for adv in invoice.advertencias:
        print(f"  [ADVERTENCIA] {adv}")
    for err in errores:
        print(f"  [ERROR] {err}")

    factura_id = save_gas_invoice(conn, invoice)
    print(f"  [OK] {pdf_path.name} → gas_facturas.id={factura_id}  "
          f"GJ={invoice.consumo_total_gj:,.4f}  "
          f"total=${invoice.total_mxn:,.2f}")
    return factura_id
```

También verificar que los imports de `sqlite3` y `Path` ya están al inicio del archivo (si no, agregarlos).

- [ ] **Step 4: Correr todos los tests**

```bash
python3 -m pytest tests/ -v
```
Expected: todos PASS (62 originales + 3 + 4 + 6 = 75 tests totales)

- [ ] **Step 5: Prueba real — procesar las 12 facturas de gas**

```python
# Ejecutar desde la raíz del proyecto:
python3 -c "
import sqlite3
from pathlib import Path
from storage.schema import init_db
from cli.main import procesar_factura_gas

conn = sqlite3.connect(':memory:')
conn.execute('PRAGMA foreign_keys = ON')
init_db(conn)

files = sorted(Path('invoices/Gas').glob('*.pdf'))
print(f'Procesando {len(files)} facturas de gas...')
for f in files:
    try:
        procesar_factura_gas(f, conn)
    except Exception as e:
        print(f'  FAIL {f.name}: {e}')
"
```
Expected: 12 líneas `[OK]` sin errores de validación

- [ ] **Step 6: Commit final**

```bash
git add cli/main.py tests/test_cli_gas.py
git commit -m "feat: add procesar_factura_gas CLI function (Task 4)"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ `GasInvoice` con todos los campos del modelo: uuid, folio, fechas, cliente, consumo, conceptos, totales
- ✅ `GasConcepto`: descripcion, clave_producto, cantidad_gj, precio_unitario_gj, importe_mxn
- ✅ `consumo_total_gj` derivado de los line items
- ✅ `costo_unitario_total_gj` = suma de precios por GJ
- ✅ Factory `get_gas_parser()` en `parsers/gas/__init__.py`
- ✅ Validación interna en `ENGIEParser.validate()`
- ✅ Persistencia: `save_gas_invoice`, `load_gas_invoice`, `list_gas_invoices`
- ✅ CLI: `procesar_factura_gas()` con mismo patrón que CFE
- ✅ TDD en cada task

**2. Placeholder scan:** Ninguno encontrado.

**3. Type consistency:**
- `GasConcepto` y `GasInvoice` vienen de `models/gas_invoice.py` (ya definidos)
- `_parse_decimal` y `_parse_fecha` locales en `engie.py` (no comparten namespace con CFE)
- `save_gas_invoice` / `load_gas_invoice` / `list_gas_invoices` consistentes entre task 3 y task 4
