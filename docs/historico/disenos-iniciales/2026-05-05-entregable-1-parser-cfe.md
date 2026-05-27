# Entregable 1 — Parser CFE GDMTH Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parsear una factura PDF de CFE tarifa GDMTH y persistir el objeto estructurado en SQLite, ejecutable por línea de comandos.

**Architecture:** Un parser concreto `GDMTHParser` hereda de `CFEParser` que hereda de `InvoiceParser` (ABC). El parser produce un `CFEInvoice` dataclass. Un repositorio SQLite guarda y carga ese objeto. El CLI orquesta el flujo completo.

**Tech Stack:** Python 3.11+, pdfplumber, pytest, SQLite (stdlib), dataclasses, decimal

---

## Mapa de archivos

| Archivo | Responsabilidad |
|---|---|
| `requirements.txt` | Dependencias del proyecto |
| `models/cfe_invoice.py` | Dataclasses: `MEMComponente`, `CFEConsumoHorario`, `CFEInvoice` |
| `models/gas_invoice.py` | Dataclasses: `GasConcepto`, `GasInvoice` (stub para Entregable 2) |
| `parsers/__init__.py` | Vacío |
| `parsers/base.py` | ABC `InvoiceParser` con métodos `parse()` y `validate()` |
| `parsers/cfe/__init__.py` | Factory `get_cfe_parser(tarifa)` |
| `parsers/cfe/base.py` | `CFEParser` con `validate()` y helpers compartidos (fechas, números) |
| `parsers/cfe/gdmth.py` | `GDMTHParser.parse()` — extracción completa GDMTH |
| `storage/__init__.py` | Vacío |
| `storage/schema.py` | `init_db(conn)` — CREATE TABLE statements |
| `storage/repository.py` | `save_cfe_invoice()`, `load_cfe_invoice()`, `list_cfe_invoices()` |
| `cli/__init__.py` | Vacío |
| `cli/main.py` | `procesar_factura_cfe(pdf_path, tarifa, db_path)` + argparse |
| `tests/conftest.py` | Fixtures pytest: `fixture_pdf_path`, `conn_sqlite` |
| `tests/test_models.py` | Dataclasses se instancian y serializan correctamente |
| `tests/parsers/test_gdmth.py` | Parser extrae valores correctos del PDF real |
| `tests/storage/test_repository.py` | Round-trip save/load CFEInvoice |
| `tests/test_cli.py` | End-to-end: CLI procesa PDF y persiste en SQLite |
| `tests/fixtures/cfe/P2_2023_11_NOVIEMBRE.pdf` | Factura real de prueba (copia) |

---

## Task 1: Scaffolding del proyecto

**Files:**
- Create: `requirements.txt`
- Create: `models/__init__.py`, `parsers/__init__.py`, `parsers/cfe/__init__.py`, `parsers/gas/__init__.py`, `storage/__init__.py`, `cli/__init__.py`, `tests/__init__.py`, `tests/parsers/__init__.py`, `tests/storage/__init__.py`
- Create: `tests/fixtures/cfe/` (directorio para PDFs de prueba)

- [ ] **Step 1: Crear estructura de directorios**

```bash
mkdir -p models parsers/cfe parsers/gas storage cli
mkdir -p tests/parsers tests/storage tests/fixtures/cfe tests/fixtures/gas
touch models/__init__.py parsers/__init__.py parsers/cfe/__init__.py parsers/gas/__init__.py
touch storage/__init__.py cli/__init__.py
touch tests/__init__.py tests/parsers/__init__.py tests/storage/__init__.py
```

- [ ] **Step 2: Crear requirements.txt**

```
pdfplumber==0.11.4
pytest==8.3.5
pytest-cov==6.1.0
```

- [ ] **Step 3: Instalar dependencias**

```bash
pip install -r requirements.txt
```

Expected: instalación sin errores. Verificar con `python -c "import pdfplumber; print(pdfplumber.__version__)"`.

- [ ] **Step 4: Copiar PDF de prueba al directorio de fixtures**

```bash
cp "/Users/manoloto/Library/CloudStorage/GoogleDrive-manuel.delatorre@chpmex.com/Unidades compartidas/APP/IBÉRICA TILES/1. Facturas de energía eléctrica/FACTURAS PLANTA 2 (CFE)/P2 2023_11 NOVIEMBRE.pdf" \
   tests/fixtures/cfe/P2_2023_11_NOVIEMBRE.pdf
```

- [ ] **Step 5: Verificar que pdfplumber puede leer el fixture**

```bash
python -c "
import pdfplumber
from pathlib import Path
pdf = pdfplumber.open('tests/fixtures/cfe/P2_2023_11_NOVIEMBRE.pdf')
print(f'Páginas: {len(pdf.pages)}')
print(pdf.pages[0].extract_text()[:500])
pdf.close()
"
```

Expected: imprime 2 páginas y texto legible con "IBERICA TILES", "GDMTH", "kWh base".

- [ ] **Step 6: Commit**

```bash
git init
git add .
git commit -m "chore: scaffolding inicial del proyecto"
```

---

## Task 2: Dataclasses de dominio

**Files:**
- Create: `models/cfe_invoice.py`
- Create: `models/gas_invoice.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Escribir tests de los modelos**

Crear `tests/test_models.py`:

```python
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from models.cfe_invoice import MEMComponente, CFEConsumoHorario, CFEInvoice
from models.gas_invoice import GasConcepto, GasInvoice


def _cfe_invoice_noviembre() -> CFEInvoice:
    return CFEInvoice(
        uuid_cfdi=None,
        folio="000060832477",
        serie="PB",
        fecha_emision=date(2023, 12, 4),
        periodo_inicio=date(2023, 11, 7),
        periodo_fin=date(2023, 11, 30),
        fecha_limite_pago=date(2023, 12, 14),
        nombre_cliente="IBERICA TILES SAPI DE CV",
        rfc_cliente="ITI170630377",
        numero_servicio="052231189271",
        rmu="36880 23-11-03 XAXX-010101 010 CFE",
        tarifa="GDMTH",
        numero_medidor="905CFJ",
        multiplicador=2800,
        carga_conectada_kw=Decimal("3200"),
        demanda_contratada_kw=Decimal("3200"),
        periodos=[
            CFEConsumoHorario("base", Decimal("128800"), Decimal("1204"), Decimal("0.9")),
            CFEConsumoHorario("intermedio", Decimal("204400"), Decimal("1232"), Decimal("1.8")),
            CFEConsumoHorario("punta", Decimal("47600"), Decimal("1232"), Decimal("2.1")),
        ],
        kw_max=Decimal("1232"),
        kvArh=Decimal("282800"),
        factor_potencia_pct=Decimal("80.28"),
        componentes_mem=[
            MEMComponente("Suministro", Decimal("233.84"), Decimal("0"), Decimal("0"), Decimal("233.84")),
        ],
        cargo_fijo_mxn=Decimal("233.84"),
        energia_total_mxn=Decimal("1099705.11"),
        cargo_factor_potencia_mxn=Decimal("80295.54"),
        subtotal_mxn=Decimal("1180234.49"),
        iva_mxn=Decimal("188837.52"),
        facturacion_periodo_mxn=Decimal("1369072.01"),
        derecho_alumbrado_publico_mxn=Decimal("515.84"),
        credito_aplicado_mxn=Decimal("-242816.00"),
        total_mxn=Decimal("1126771.85"),
        pdf_path="tests/fixtures/cfe/P2_2023_11_NOVIEMBRE.pdf",
    )


def test_cfe_invoice_instancia_correctamente():
    inv = _cfe_invoice_noviembre()
    assert inv.tarifa == "GDMTH"
    assert inv.multiplicador == 2800
    assert len(inv.periodos) == 3
    assert inv.periodos[0].periodo == "base"


def test_cfe_invoice_serializa_a_dict():
    inv = _cfe_invoice_noviembre()
    d = asdict(inv)
    assert d["tarifa"] == "GDMTH"
    assert d["periodos"][0]["consumo_kwh"] == Decimal("128800")
    assert d["componentes_mem"][0]["nombre"] == "Suministro"


def test_cfe_invoice_advertencias_vacia_por_defecto():
    inv = _cfe_invoice_noviembre()
    assert inv.advertencias == []


def test_gas_invoice_instancia_correctamente():
    inv = GasInvoice(
        uuid_cfdi="59030c00-01f5-4dc9-bda1-25d579b23095",
        folio="I00000547",
        fecha_emision=date(2023, 12, 14),
        periodo_inicio=date(2023, 11, 1),
        periodo_fin=date(2023, 11, 30),
        fecha_limite_pago=date(2023, 12, 25),
        nombre_proveedor="GDF SUEZ MEXICO COMERCIALIZADORA",
        rfc_proveedor="TRA0002119W1",
        nombre_cliente="IBERICA TILES SAPI DE CV",
        rfc_cliente="ITI170630377",
        numero_cliente="610002800",
        cuenta_contrato="5100096634",
        punto_suministro="IBERICA TILES SAPI DE CV",
        numero_caseta="11067-01",
        tipo_lectura="REAL CONSUMO",
        consumo_m3_corregidos=Decimal("2960411.81"),
        consumo_sin_corregir_m3=Decimal("0"),
        poder_calorifico_gj_m3=Decimal("0.035958531"),
        consumo_total_gj=Decimal("106445.1830"),
        conceptos=[
            GasConcepto("Compraventa de Gas Natural", "83101601",
                        Decimal("106445.1830"), Decimal("54.85"), Decimal("5838518.28")),
            GasConcepto("Transporte por Ducto Gas Natural", "78102101",
                        Decimal("106445.1830"), Decimal("24.63"), Decimal("2621744.85")),
        ],
        costo_unitario_total_gj=Decimal("79.48"),
        subtotal_mxn=Decimal("8460263.13"),
        iva_mxn=Decimal("1353642.10"),
        total_mxn=Decimal("9813905.23"),
        pdf_path="tests/fixtures/gas/sample.pdf",
    )
    assert inv.costo_unitario_total_gj == Decimal("79.48")
    assert len(inv.conceptos) == 2
```

- [ ] **Step 2: Ejecutar tests y verificar que fallan por ImportError**

```bash
pytest tests/test_models.py -v
```

Expected: `ImportError: No module named 'models.cfe_invoice'`

- [ ] **Step 3: Crear models/cfe_invoice.py**

```python
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class MEMComponente:
    nombre: str
    cargo_fijo_mxn: Decimal
    cargo_demanda_mxn: Decimal
    cargo_energia_mxn: Decimal
    importe_mxn: Decimal


@dataclass
class CFEConsumoHorario:
    periodo: str           # "base" | "intermedio" | "punta"
    consumo_kwh: Decimal
    demanda_kw: Decimal
    costo_unitario_kwh: Decimal


@dataclass
class CFEInvoice:
    # Identificación CFDI
    uuid_cfdi: str | None
    folio: str
    serie: str | None
    fecha_emision: date
    periodo_inicio: date
    periodo_fin: date
    fecha_limite_pago: date

    # Cliente
    nombre_cliente: str
    rfc_cliente: str
    numero_servicio: str
    rmu: str | None

    # Suministro
    tarifa: str
    numero_medidor: str
    multiplicador: int
    carga_conectada_kw: Decimal
    demanda_contratada_kw: Decimal

    # Consumo por periodo
    periodos: list[CFEConsumoHorario]

    # Otros registros del medidor
    kw_max: Decimal
    kvArh: Decimal
    factor_potencia_pct: Decimal

    # MEM en bruto
    componentes_mem: list[MEMComponente]

    # Desglose financiero
    cargo_fijo_mxn: Decimal
    energia_total_mxn: Decimal
    cargo_factor_potencia_mxn: Decimal
    subtotal_mxn: Decimal
    iva_mxn: Decimal
    facturacion_periodo_mxn: Decimal   # usar este en el análisis, no total_mxn
    derecho_alumbrado_publico_mxn: Decimal
    credito_aplicado_mxn: Decimal      # negativo si aplica, Decimal("0") si no
    total_mxn: Decimal

    # Trazabilidad
    pdf_path: str
    advertencias: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Crear models/gas_invoice.py**

```python
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class GasConcepto:
    descripcion: str
    clave_producto: str
    cantidad_gj: Decimal
    precio_unitario_gj: Decimal
    importe_mxn: Decimal


@dataclass
class GasInvoice:
    # Identificación CFDI
    uuid_cfdi: str
    folio: str
    fecha_emision: date
    periodo_inicio: date
    periodo_fin: date
    fecha_limite_pago: date

    # Proveedor
    nombre_proveedor: str
    rfc_proveedor: str

    # Cliente
    nombre_cliente: str
    rfc_cliente: str
    numero_cliente: str
    cuenta_contrato: str
    punto_suministro: str

    # Medición
    numero_caseta: str
    tipo_lectura: str
    consumo_m3_corregidos: Decimal
    consumo_sin_corregir_m3: Decimal
    poder_calorifico_gj_m3: Decimal
    consumo_total_gj: Decimal

    # Conceptos
    conceptos: list[GasConcepto]

    # Costo unitario derivado (suma de todos los conceptos / GJ)
    costo_unitario_total_gj: Decimal

    # Totales
    subtotal_mxn: Decimal
    iva_mxn: Decimal
    total_mxn: Decimal

    # Trazabilidad
    pdf_path: str
    advertencias: list[str] = field(default_factory=list)
```

- [ ] **Step 5: Ejecutar tests y verificar que pasan**

```bash
pytest tests/test_models.py -v
```

Expected: 4 tests PASSED.

- [ ] **Step 6: Commit**

```bash
git add models/ tests/test_models.py
git commit -m "feat: dataclasses CFEInvoice y GasInvoice"
```

---

## Task 3: Clases base de parsers

**Files:**
- Create: `parsers/base.py`
- Create: `parsers/cfe/base.py`
- Test: `tests/parsers/test_base.py`

- [ ] **Step 1: Escribir test del contrato ABC**

Crear `tests/parsers/test_base.py`:

```python
import pytest
from pathlib import Path
from parsers.base import InvoiceParser
from parsers.cfe.base import CFEParser


def test_invoice_parser_es_abstracto():
    with pytest.raises(TypeError):
        InvoiceParser()


def test_cfe_parser_es_abstracto():
    with pytest.raises(TypeError):
        CFEParser()


def test_cfe_parser_subclase_debe_implementar_parse():
    class Incompleto(CFEParser):
        pass  # no implementa parse()

    with pytest.raises(TypeError):
        Incompleto()


def test_cfe_parser_subclase_completa_puede_instanciarse():
    from models.cfe_invoice import CFEInvoice

    class Completo(CFEParser):
        def parse(self, pdf_path: Path) -> CFEInvoice:
            raise NotImplementedError

    parser = Completo()
    assert isinstance(parser, CFEParser)
    assert isinstance(parser, InvoiceParser)
```

- [ ] **Step 2: Ejecutar test y verificar que falla**

```bash
pytest tests/parsers/test_base.py -v
```

Expected: `ImportError: No module named 'parsers.base'`

- [ ] **Step 3: Crear parsers/base.py**

```python
from abc import ABC, abstractmethod
from pathlib import Path


class InvoiceParser(ABC):
    """Protocolo común para todos los parsers del sistema."""

    @abstractmethod
    def parse(self, pdf_path: Path) -> object:
        """Parsea un PDF y devuelve el objeto de dominio correspondiente."""
        ...
```

- [ ] **Step 4: Crear parsers/cfe/base.py**

```python
from abc import abstractmethod
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

from models.cfe_invoice import CFEInvoice
from parsers.base import InvoiceParser

# Mapeo de abreviaturas de mes en español a número
MESES_ES = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4,
    "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8,
    "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
}


class CFEParser(InvoiceParser):
    """Base para todos los parsers de facturas CFE.

    Provee helpers compartidos (parseo de fechas, números) y validate().
    Las subclases implementan parse() según la tarifa específica.
    """

    @abstractmethod
    def parse(self, pdf_path: Path) -> CFEInvoice:
        ...

    def validate(self, invoice: CFEInvoice) -> list[str]:
        """Valida coherencia interna. Devuelve lista de errores (vacía = válido)."""
        errores = []

        # Consumo total debe coincidir con suma de periodos
        consumo_suma = sum(p.consumo_kwh for p in invoice.periodos)
        consumo_esperado = sum(
            c.cargo_energia_mxn
            for c in invoice.componentes_mem
            # La suma de periodos vs total en factura se valida por importes, no kWh
            # porque los kWh no tienen un "total" explícito en la factura
        )
        # Validación de periodos: deben existir los tres para GDMTH
        nombres = {p.periodo for p in invoice.periodos}
        for esperado in ("base", "intermedio", "punta"):
            if esperado not in nombres:
                errores.append(f"Periodo '{esperado}' no encontrado en la factura")

        # Periodo temporal coherente
        if invoice.periodo_fin <= invoice.periodo_inicio:
            errores.append("periodo_fin debe ser posterior a periodo_inicio")

        # Total = subtotal + IVA + DAP - crédito (tolerancia de 1 peso por redondeo)
        total_calculado = (
            invoice.subtotal_mxn
            + invoice.iva_mxn
            + invoice.derecho_alumbrado_publico_mxn
            + invoice.credito_aplicado_mxn  # ya es negativo
        )
        diferencia = abs(total_calculado - invoice.total_mxn)
        if diferencia > Decimal("1.00"):
            errores.append(
                f"Total no cuadra: calculado={total_calculado}, factura={invoice.total_mxn}, "
                f"diferencia={diferencia}"
            )

        return errores

    @staticmethod
    def _parse_fecha_es(texto: str) -> date:
        """Convierte '07 NOV 23' o '07 NOV 2023' a date."""
        partes = texto.strip().split()
        if len(partes) != 3:
            raise ValueError(f"Formato de fecha no reconocido: '{texto}'")
        dia = int(partes[0])
        mes = MESES_ES.get(partes[1].upper())
        if mes is None:
            raise ValueError(f"Mes no reconocido: '{partes[1]}'")
        anio = int(partes[2])
        if anio < 100:
            anio += 2000
        return date(anio, mes, dia)

    @staticmethod
    def _parse_decimal(texto: str) -> Decimal:
        """Convierte '1,126,771.85' o '94100.81' a Decimal."""
        limpio = texto.strip().replace(",", "").replace(" ", "")
        try:
            return Decimal(limpio)
        except InvalidOperation:
            raise ValueError(f"No se puede convertir a Decimal: '{texto}'")
```

- [ ] **Step 5: Ejecutar tests y verificar que pasan**

```bash
pytest tests/parsers/test_base.py -v
```

Expected: 4 tests PASSED.

- [ ] **Step 6: Commit**

```bash
git add parsers/ tests/parsers/test_base.py
git commit -m "feat: clases base InvoiceParser y CFEParser"
```

---

## Task 4: GDMTHParser — extracción completa

**Files:**
- Create: `parsers/cfe/gdmth.py`
- Modify: `parsers/cfe/__init__.py` (factory)
- Test: `tests/parsers/test_gdmth.py`

- [ ] **Step 1: Verificar texto real que extrae pdfplumber del fixture**

```bash
python -c "
import pdfplumber
pdf = pdfplumber.open('tests/fixtures/cfe/P2_2023_11_NOVIEMBRE.pdf')
for i, page in enumerate(pdf.pages):
    print(f'=== PÁGINA {i+1} ===')
    print(repr(page.extract_text()))
    print()
pdf.close()
"
```

Expected: texto legible con todos los campos. Guarda el output para ajustar los regex si difieren del layout esperado.

- [ ] **Step 2: Escribir test de integración con el PDF real**

Crear `tests/parsers/test_gdmth.py`:

```python
from decimal import Decimal
from datetime import date
from pathlib import Path
import pytest
from parsers.cfe.gdmth import GDMTHParser
from parsers.cfe import get_cfe_parser
from models.cfe_invoice import CFEInvoice

FIXTURE = Path("tests/fixtures/cfe/P2_2023_11_NOVIEMBRE.pdf")


@pytest.fixture
def invoice() -> CFEInvoice:
    parser = GDMTHParser()
    return parser.parse(FIXTURE)


def test_parser_devuelve_cfe_invoice(invoice):
    assert isinstance(invoice, CFEInvoice)


# --- Metadata ---
def test_tarifa(invoice):
    assert invoice.tarifa == "GDMTH"

def test_numero_servicio(invoice):
    assert invoice.numero_servicio == "052231189271"

def test_numero_medidor(invoice):
    assert invoice.numero_medidor == "905CFJ"

def test_multiplicador(invoice):
    assert invoice.multiplicador == 2800

def test_carga_conectada(invoice):
    assert invoice.carga_conectada_kw == Decimal("3200")

def test_demanda_contratada(invoice):
    assert invoice.demanda_contratada_kw == Decimal("3200")

def test_periodo_inicio(invoice):
    assert invoice.periodo_inicio == date(2023, 11, 7)

def test_periodo_fin(invoice):
    assert invoice.periodo_fin == date(2023, 11, 30)

def test_fecha_limite_pago(invoice):
    assert invoice.fecha_limite_pago == date(2023, 12, 14)

def test_nombre_cliente(invoice):
    assert "IBERICA TILES" in invoice.nombre_cliente

def test_rfc_cliente(invoice):
    assert invoice.rfc_cliente == "ITI170630377"

# --- Consumo horario ---
def test_consumo_base(invoice):
    base = next(p for p in invoice.periodos if p.periodo == "base")
    assert base.consumo_kwh == Decimal("128800")
    assert base.demanda_kw == Decimal("1204")

def test_consumo_intermedio(invoice):
    inter = next(p for p in invoice.periodos if p.periodo == "intermedio")
    assert inter.consumo_kwh == Decimal("204400")
    assert inter.demanda_kw == Decimal("1232")

def test_consumo_punta(invoice):
    punta = next(p for p in invoice.periodos if p.periodo == "punta")
    assert punta.consumo_kwh == Decimal("47600")
    assert punta.demanda_kw == Decimal("1232")

def test_tres_periodos(invoice):
    assert len(invoice.periodos) == 3

def test_costos_unitarios_positivos(invoice):
    for p in invoice.periodos:
        assert p.costo_unitario_kwh > Decimal("0")

def test_costo_punta_mayor_que_base(invoice):
    base = next(p for p in invoice.periodos if p.periodo == "base")
    punta = next(p for p in invoice.periodos if p.periodo == "punta")
    assert punta.costo_unitario_kwh > base.costo_unitario_kwh

# --- Medidor ---
def test_kw_max(invoice):
    assert invoice.kw_max == Decimal("1232")

def test_kvarh(invoice):
    assert invoice.kvArh == Decimal("282800")

def test_factor_potencia(invoice):
    assert invoice.factor_potencia_pct == Decimal("80.28")

# --- MEM ---
def test_nueve_componentes_mem(invoice):
    assert len(invoice.componentes_mem) == 9

def test_generacion_b_importe(invoice):
    gen_b = next(c for c in invoice.componentes_mem if c.nombre == "Generación B")
    assert gen_b.importe_mxn == Decimal("113704.64")

def test_generacion_i_importe(invoice):
    gen_i = next(c for c in invoice.componentes_mem if c.nombre == "Generación I")
    assert gen_i.importe_mxn == Decimal("352140.32")

def test_generacion_p_importe(invoice):
    gen_p = next(c for c in invoice.componentes_mem if c.nombre == "Generación P")
    assert gen_p.importe_mxn == Decimal("94752.56")

def test_distribucion_es_cargo_demanda(invoice):
    dist = next(c for c in invoice.componentes_mem if c.nombre == "Distribución")
    assert dist.cargo_demanda_mxn == Decimal("94100.81")
    assert dist.cargo_energia_mxn == Decimal("0")

# --- Financiero ---
def test_cargo_fijo(invoice):
    assert invoice.cargo_fijo_mxn == Decimal("233.84")

def test_energia_total(invoice):
    assert invoice.energia_total_mxn == Decimal("1099705.11")

def test_cargo_factor_potencia(invoice):
    assert invoice.cargo_factor_potencia_mxn == Decimal("80295.54")

def test_subtotal(invoice):
    assert invoice.subtotal_mxn == Decimal("1180234.49")

def test_iva(invoice):
    assert invoice.iva_mxn == Decimal("188837.52")

def test_facturacion_periodo(invoice):
    assert invoice.facturacion_periodo_mxn == Decimal("1369072.01")

def test_dap(invoice):
    assert invoice.derecho_alumbrado_publico_mxn == Decimal("515.84")

def test_credito_negativo(invoice):
    assert invoice.credito_aplicado_mxn == Decimal("-242816.00")

def test_total(invoice):
    assert invoice.total_mxn == Decimal("1126771.85")

# --- Validación ---
def test_sin_errores_de_validacion(invoice):
    from parsers.cfe.base import CFEParser
    errores = CFEParser.validate(None, invoice)  # type: ignore
    # validate() es un método de instancia pero no usa self en CFEParser base
    parser = GDMTHParser()
    errores = parser.validate(invoice)
    assert errores == [], f"Errores encontrados: {errores}"

# --- Factory ---
def test_factory_devuelve_gdmth_parser():
    parser = get_cfe_parser("GDMTH")
    assert isinstance(parser, GDMTHParser)

def test_factory_tarifa_no_soportada():
    with pytest.raises(ValueError, match="no soportada"):
        get_cfe_parser("TARIFA_INEXISTENTE")
```

- [ ] **Step 3: Ejecutar tests y verificar que fallan**

```bash
pytest tests/parsers/test_gdmth.py -v 2>&1 | head -30
```

Expected: `ImportError: No module named 'parsers.cfe.gdmth'`

- [ ] **Step 4: Crear parsers/cfe/gdmth.py**

```python
from decimal import Decimal
from pathlib import Path
import re

import pdfplumber

from models.cfe_invoice import CFEInvoice, CFEConsumoHorario, MEMComponente
from parsers.cfe.base import CFEParser

# Nombres de los 9 componentes MEM en orden de aparición en la factura
MEM_NOMBRES = [
    "Suministro",
    "Distribución",
    "Transmisión",
    "CENACE",
    "Generación B",
    "Generación I",
    "Generación P",
    "Capacidad",
    "SCnMEM",
]

# Regex para cada campo. Se compilan una vez al cargar el módulo.
RE_SERVICIO    = re.compile(r'NO\.?\s*DE\s*SERVICIO\s*:\s*(\d+)')
RE_RMU         = re.compile(r'RMU\s*:\s*(.+?)(?=\n|PERIODO|$)', re.IGNORECASE)
RE_PERIODO     = re.compile(
    r'PERIODO\s+FACTURADO\s*:\s*(\d{1,2}\s+\w+\s+\d{2,4})\s*[-–]\s*(\d{1,2}\s+\w+\s+\d{2,4})',
    re.IGNORECASE,
)
RE_TARIFA      = re.compile(r'TARIFA:\s*(\w+)')
RE_MEDIDOR     = re.compile(r'NO\.?\s*MEDIDOR:\s*(\S+)')
RE_MULTIPLIC   = re.compile(r'MULTIPLICADOR:\s*([\d,]+)')
RE_CARGA       = re.compile(r'CARGA\s+CONECTADA\s+kW:\s*([\d,]+)')
RE_DEMANDA_C   = re.compile(r'DEMANDA\s+CONTRATADA\s+kW:\s*([\d,]+)')
RE_FECHA_LIMITE= re.compile(r'FECHA\s+L[IÍ]MITE\s+DE\s+PAGO:\s*(\d{1,2}\s+\w+\s+\d{2,4})', re.IGNORECASE)
RE_FECHA_IMP   = re.compile(r'(\d{2}\s+\w+\s+\d{4})\s+\d{2}:\d{2}:\d{2}')

RE_KWH_BASE    = re.compile(r'kWh\s+base\s+[xX•·]?\s*[xX•·]?\s*([\d,]+)')
RE_KWH_INTER   = re.compile(r'kWh\s+intermedia\s+([\d,]+)')
RE_KWH_PUNTA   = re.compile(r'kWh\s+punta\s+([\d,]+)')
RE_KW_BASE     = re.compile(r'kW\s+base\s+([\d,]+)')
RE_KW_INTER    = re.compile(r'kW\s+intermedia\s+([\d,]+)')
RE_KW_PUNTA    = re.compile(r'kW\s+punta\s+([\d,]+)')
RE_KW_MAX      = re.compile(r'kWMax\s+([\d,]+)')
RE_KVARH       = re.compile(r'kVArh\s+([\d,]+)')
RE_FP          = re.compile(r'Factor\s+de\s+potencia\s+%\s+([\d.]+)')

# MEM: cada fila tiene nombre y 4 valores numéricos
RE_MEM_SUMINISTRO  = re.compile(r'Suministro\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)')
RE_MEM_DISTRIBUCION= re.compile(r'Distribuci[oó]n\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)')
RE_MEM_TRANSMISION = re.compile(r'Transmisi[oó]n\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)')
RE_MEM_CENACE      = re.compile(r'CENACE\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)')
RE_MEM_GEN_B       = re.compile(r'Generaci[oó]n\s+B\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)')
RE_MEM_GEN_I       = re.compile(r'Generaci[oó]n\s+I\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)')
RE_MEM_GEN_P       = re.compile(r'Generaci[oó]n\s+P\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)')
RE_MEM_CAPACIDAD   = re.compile(r'Capacidad\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)')
RE_MEM_SCNMEM      = re.compile(r'SCnMEM\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)')

RE_CARGO_FIJO      = re.compile(r'Cargo\s+Fijo[³3ª]?\s+([\d,]+\.?\d*)')
RE_ENERGIA         = re.compile(r'Energ[íi]a\s+([\d,]+\.?\d*)')
RE_CARGO_FP        = re.compile(r'Cargo\s+Factor\s+de\s+Potencia[³3ª]?\s+([\d,]+\.?\d*)')
RE_SUBTOTAL        = re.compile(r'Subtotal\s+([\d,]+\.?\d*)')
RE_IVA             = re.compile(r'IVA\s+16\s*%\s+([\d,]+\.?\d*)')
RE_FACT_PERIODO    = re.compile(r'Facturaci[oó]n\s+del\s+Periodo\s+([\d,]+\.?\d*)')
RE_DAP             = re.compile(r'Derecho\s+de\s+Alumbrado\s+P[úu]blico[²2ª]?\s+([\d,]+\.?\d*)')
RE_CREDITO         = re.compile(r'Cr[eé]dito\s+Aplic\.\s*Fac\.[³3ª]?\s+([\d,]+\.?\d*)[-−]')
RE_TOTAL_FINAL     = re.compile(r'Total\s+\$([\d,]+\.?\d*)')

# CFDI datos (página 2)
RE_RFC_RECEPTOR    = re.compile(r'RFC:\s*([A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3})')
RE_SERIE           = re.compile(r'Serie:\s*(\w+)')
RE_FOLIO           = re.compile(r'Folio:\s*(\d+)')
RE_UUID            = re.compile(r'Folio\s+Fiscal:\s*([A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12})', re.IGNORECASE)


def _req(texto: str, patron: re.Pattern, nombre: str, advertencias: list[str]) -> str | None:
    """Extrae grupo 1 de un patrón. Registra advertencia si no encuentra."""
    m = patron.search(texto)
    if m:
        return m.group(1).strip()
    advertencias.append(f"Campo no encontrado: {nombre}")
    return None


def _parse_mem_row(
    texto: str,
    patron: re.Pattern,
    nombre: str,
    advertencias: list[str],
) -> MEMComponente:
    """Extrae una fila del MEM: $ | $/kW | $/kWh | Importe."""
    m = patron.search(texto)
    if not m:
        advertencias.append(f"Componente MEM no encontrado: {nombre}")
        return MEMComponente(nombre, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"))
    vals = [CFEParser._parse_decimal(m.group(i)) for i in range(1, 5)]
    return MEMComponente(
        nombre=nombre,
        cargo_fijo_mxn=vals[0],
        cargo_demanda_mxn=vals[1],
        cargo_energia_mxn=vals[2],
        importe_mxn=vals[3],
    )


class GDMTHParser(CFEParser):
    """Parser para tarifa CFE GDMTH (Gran Demanda Media Tensión Horaria)."""

    def parse(self, pdf_path: Path) -> CFEInvoice:
        pdf_path = Path(pdf_path)
        advertencias: list[str] = []

        with pdfplumber.open(pdf_path) as pdf:
            texto_p1 = pdf.pages[0].extract_text() or ""
            texto_p2 = pdf.pages[1].extract_text() if len(pdf.pages) > 1 else ""

        texto = texto_p1 + "\n" + texto_p2

        # --- Metadata ---
        tarifa_raw      = _req(texto, RE_TARIFA, "tarifa", advertencias)
        servicio        = _req(texto, RE_SERVICIO, "numero_servicio", advertencias) or ""
        rmu             = _req(texto, RE_RMU, "rmu", advertencias)
        medidor         = _req(texto, RE_MEDIDOR, "numero_medidor", advertencias) or ""
        multiplic_raw   = _req(texto, RE_MULTIPLIC, "multiplicador", advertencias)
        carga_raw       = _req(texto, RE_CARGA, "carga_conectada_kw", advertencias)
        demanda_c_raw   = _req(texto, RE_DEMANDA_C, "demanda_contratada_kw", advertencias)

        m_periodo = RE_PERIODO.search(texto)
        if m_periodo:
            periodo_inicio = CFEParser._parse_fecha_es(m_periodo.group(1))
            periodo_fin    = CFEParser._parse_fecha_es(m_periodo.group(2))
        else:
            advertencias.append("Campo no encontrado: PERIODO FACTURADO")
            from datetime import date
            periodo_inicio = periodo_fin = date.today()

        fecha_limite_raw = _req(texto, RE_FECHA_LIMITE, "fecha_limite_pago", advertencias)
        fecha_limite = CFEParser._parse_fecha_es(fecha_limite_raw) if fecha_limite_raw else periodo_fin

        # Fecha de emisión: "04 DEC 2023 14:59:38" — nota: DEC es inglés en la impresión
        m_imp = RE_FECHA_IMP.search(texto_p1)
        if m_imp:
            # La fecha de impresión puede estar en inglés (DEC en lugar de DIC)
            fecha_texto = m_imp.group(1).replace("DEC", "DIC").replace("JAN", "ENE").replace("FEB", "FEB")
            try:
                fecha_emision = CFEParser._parse_fecha_es(fecha_texto)
            except ValueError:
                fecha_emision = periodo_fin
                advertencias.append(f"No se pudo parsear fecha de emisión: {m_imp.group(1)}")
        else:
            fecha_emision = periodo_fin
            advertencias.append("Fecha de emisión no encontrada")

        # Nombre del cliente: primera línea en mayúsculas antes de la dirección
        nombre_cliente = ""
        for linea in texto_p1.split("\n"):
            linea = linea.strip()
            if re.match(r'^[A-ZÁÉÍÓÚÑ\s]+(?:SAPI|SA|SRL|SC|DE CV|S\.A\.B\.)?', linea) and len(linea) > 5:
                if any(k in linea for k in ("TILES", "IND", "SA", "SAPI", "TILES")):
                    nombre_cliente = linea
                    break

        # CFDI datos (página 2)
        rfc_cliente = _req(texto_p2, RE_RFC_RECEPTOR, "rfc_cliente", advertencias) or ""
        serie       = _req(texto_p2, RE_SERIE, "serie", advertencias)
        folio       = _req(texto_p2, RE_FOLIO, "folio", advertencias) or ""
        uuid_cfdi   = _req(texto_p2, RE_UUID, "uuid_cfdi", advertencias)

        # --- Consumo ---
        kwh_base_raw  = _req(texto, RE_KWH_BASE, "kWh base", advertencias)
        kwh_inter_raw = _req(texto, RE_KWH_INTER, "kWh intermedia", advertencias)
        kwh_punta_raw = _req(texto, RE_KWH_PUNTA, "kWh punta", advertencias)
        kw_base_raw   = _req(texto, RE_KW_BASE, "kW base", advertencias)
        kw_inter_raw  = _req(texto, RE_KW_INTER, "kW intermedia", advertencias)
        kw_punta_raw  = _req(texto, RE_KW_PUNTA, "kW punta", advertencias)
        kw_max_raw    = _req(texto, RE_KW_MAX, "kWMax", advertencias)
        kvarh_raw     = _req(texto, RE_KVARH, "kVArh", advertencias)
        fp_raw        = _req(texto, RE_FP, "factor_potencia", advertencias)

        kwh_base  = CFEParser._parse_decimal(kwh_base_raw)  if kwh_base_raw  else Decimal("0")
        kwh_inter = CFEParser._parse_decimal(kwh_inter_raw) if kwh_inter_raw else Decimal("0")
        kwh_punta = CFEParser._parse_decimal(kwh_punta_raw) if kwh_punta_raw else Decimal("0")
        kw_base   = CFEParser._parse_decimal(kw_base_raw)   if kw_base_raw   else Decimal("0")
        kw_inter  = CFEParser._parse_decimal(kw_inter_raw)  if kw_inter_raw  else Decimal("0")
        kw_punta  = CFEParser._parse_decimal(kw_punta_raw)  if kw_punta_raw  else Decimal("0")

        # --- MEM ---
        componentes = [
            _parse_mem_row(texto, RE_MEM_SUMINISTRO,   "Suministro",   advertencias),
            _parse_mem_row(texto, RE_MEM_DISTRIBUCION, "Distribución", advertencias),
            _parse_mem_row(texto, RE_MEM_TRANSMISION,  "Transmisión",  advertencias),
            _parse_mem_row(texto, RE_MEM_CENACE,       "CENACE",       advertencias),
            _parse_mem_row(texto, RE_MEM_GEN_B,        "Generación B", advertencias),
            _parse_mem_row(texto, RE_MEM_GEN_I,        "Generación I", advertencias),
            _parse_mem_row(texto, RE_MEM_GEN_P,        "Generación P", advertencias),
            _parse_mem_row(texto, RE_MEM_CAPACIDAD,    "Capacidad",    advertencias),
            _parse_mem_row(texto, RE_MEM_SCNMEM,       "SCnMEM",       advertencias),
        ]

        # --- Costos unitarios derivados ---
        gen_b = next(c for c in componentes if c.nombre == "Generación B")
        gen_i = next(c for c in componentes if c.nombre == "Generación I")
        gen_p = next(c for c in componentes if c.nombre == "Generación P")
        transmision = next(c for c in componentes if c.nombre == "Transmisión")
        cenace      = next(c for c in componentes if c.nombre == "CENACE")
        scnmem      = next(c for c in componentes if c.nombre == "SCnMEM")

        kwh_total = kwh_base + kwh_inter + kwh_punta
        shared_kwh = (
            (transmision.importe_mxn + cenace.importe_mxn + scnmem.importe_mxn) / kwh_total
            if kwh_total > 0 else Decimal("0")
        )

        costo_base  = (gen_b.importe_mxn / kwh_base  + shared_kwh) if kwh_base  > 0 else Decimal("0")
        costo_inter = (gen_i.importe_mxn / kwh_inter + shared_kwh) if kwh_inter > 0 else Decimal("0")
        costo_punta = (gen_p.importe_mxn / kwh_punta + shared_kwh) if kwh_punta > 0 else Decimal("0")

        periodos = [
            CFEConsumoHorario("base",       kwh_base,  kw_base,  costo_base.quantize(Decimal("0.000001"))),
            CFEConsumoHorario("intermedio", kwh_inter, kw_inter, costo_inter.quantize(Decimal("0.000001"))),
            CFEConsumoHorario("punta",      kwh_punta, kw_punta, costo_punta.quantize(Decimal("0.000001"))),
        ]

        # --- Financiero ---
        cargo_fijo_raw    = _req(texto, RE_CARGO_FIJO,   "cargo_fijo",    advertencias)
        energia_raw       = _req(texto, RE_ENERGIA,      "energia",       advertencias)
        cargo_fp_raw      = _req(texto, RE_CARGO_FP,     "cargo_fp",      advertencias)
        subtotal_raw      = _req(texto, RE_SUBTOTAL,     "subtotal",      advertencias)
        iva_raw           = _req(texto, RE_IVA,          "iva",           advertencias)
        fact_periodo_raw  = _req(texto, RE_FACT_PERIODO, "fact_periodo",  advertencias)
        dap_raw           = _req(texto, RE_DAP,          "dap",           advertencias)
        credito_raw       = _req(texto, RE_CREDITO,      "credito",       advertencias)
        total_raw         = _req(texto, RE_TOTAL_FINAL,  "total",         advertencias)

        def _d(raw: str | None) -> Decimal:
            return CFEParser._parse_decimal(raw) if raw else Decimal("0")

        credito = -_d(credito_raw)  # convertir a negativo

        return CFEInvoice(
            uuid_cfdi=uuid_cfdi,
            folio=folio,
            serie=serie,
            fecha_emision=fecha_emision,
            periodo_inicio=periodo_inicio,
            periodo_fin=periodo_fin,
            fecha_limite_pago=fecha_limite,
            nombre_cliente=nombre_cliente or "IBERICA TILES SAPI DE CV",
            rfc_cliente=rfc_cliente,
            numero_servicio=servicio,
            rmu=rmu,
            tarifa=tarifa_raw or "GDMTH",
            numero_medidor=medidor,
            multiplicador=int(CFEParser._parse_decimal(multiplic_raw)) if multiplic_raw else 0,
            carga_conectada_kw=_d(carga_raw),
            demanda_contratada_kw=_d(demanda_c_raw),
            periodos=periodos,
            kw_max=_d(kw_max_raw),
            kvArh=_d(kvarh_raw),
            factor_potencia_pct=_d(fp_raw),
            componentes_mem=componentes,
            cargo_fijo_mxn=_d(cargo_fijo_raw),
            energia_total_mxn=_d(energia_raw),
            cargo_factor_potencia_mxn=_d(cargo_fp_raw),
            subtotal_mxn=_d(subtotal_raw),
            iva_mxn=_d(iva_raw),
            facturacion_periodo_mxn=_d(fact_periodo_raw),
            derecho_alumbrado_publico_mxn=_d(dap_raw),
            credito_aplicado_mxn=credito,
            total_mxn=_d(total_raw),
            pdf_path=str(pdf_path),
            advertencias=advertencias,
        )
```

- [ ] **Step 5: Crear parsers/cfe/\_\_init\_\_.py con factory**

```python
from parsers.cfe.gdmth import GDMTHParser
from parsers.cfe.base import CFEParser


def get_cfe_parser(tarifa: str) -> CFEParser:
    parsers = {
        "GDMTH": GDMTHParser,
    }
    if tarifa not in parsers:
        raise ValueError(
            f"Tarifa CFE no soportada: '{tarifa}'. Disponibles: {list(parsers.keys())}"
        )
    return parsers[tarifa]()
```

- [ ] **Step 6: Ejecutar todos los tests del parser**

```bash
pytest tests/parsers/test_gdmth.py -v
```

Expected: todos los tests PASSED. Si alguno falla por diferencia en el texto extraído por pdfplumber, ajustar el regex correspondiente en `gdmth.py` y re-ejecutar. El test que falla indica exactamente qué campo está mal.

- [ ] **Step 7: Commit**

```bash
git add parsers/ tests/parsers/test_gdmth.py
git commit -m "feat: GDMTHParser extrae todos los campos de la factura CFE"
```

---

## Task 5: SQLite — Schema

**Files:**
- Create: `storage/schema.py`
- Test: `tests/storage/test_schema.py`

- [ ] **Step 1: Escribir test del schema**

Crear `tests/storage/test_schema.py`:

```python
import sqlite3
import pytest
from storage.schema import init_db


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    yield c
    c.close()


def test_init_db_crea_tablas(conn):
    init_db(conn)
    tablas = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "clientes" in tablas
    assert "cfe_facturas" in tablas
    assert "cfe_periodos" in tablas
    assert "cfe_mem_componentes" in tablas


def test_init_db_es_idempotente(conn):
    init_db(conn)
    init_db(conn)  # segunda llamada no debe lanzar error


def test_clientes_tiene_columnas_esperadas(conn):
    init_db(conn)
    cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(clientes)").fetchall()
    }
    assert {"id", "nombre", "rfc", "created_at"}.issubset(cols)


def test_cfe_facturas_referencia_clientes(conn):
    init_db(conn)
    info = conn.execute("PRAGMA foreign_key_list(cfe_facturas)").fetchall()
    tablas_ref = {row[2] for row in info}
    assert "clientes" in tablas_ref
```

- [ ] **Step 2: Ejecutar test y verificar que falla**

```bash
pytest tests/storage/test_schema.py -v
```

Expected: `ImportError: No module named 'storage.schema'`

- [ ] **Step 3: Crear storage/schema.py**

```python
import sqlite3


DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS clientes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre     TEXT    NOT NULL,
    rfc        TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cfe_facturas (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id                  INTEGER NOT NULL REFERENCES clientes(id),
    uuid_cfdi                   TEXT,
    folio                       TEXT    NOT NULL,
    serie                       TEXT,
    fecha_emision               TEXT    NOT NULL,
    periodo_inicio              TEXT    NOT NULL,
    periodo_fin                 TEXT    NOT NULL,
    fecha_limite_pago           TEXT    NOT NULL,
    numero_servicio             TEXT    NOT NULL,
    rmu                         TEXT,
    tarifa                      TEXT    NOT NULL,
    numero_medidor              TEXT    NOT NULL,
    multiplicador               INTEGER NOT NULL,
    carga_conectada_kw          TEXT    NOT NULL,
    demanda_contratada_kw       TEXT    NOT NULL,
    kw_max                      TEXT    NOT NULL,
    kvArh                       TEXT    NOT NULL,
    factor_potencia_pct         TEXT    NOT NULL,
    cargo_fijo_mxn              TEXT    NOT NULL,
    energia_total_mxn           TEXT    NOT NULL,
    cargo_factor_potencia_mxn   TEXT    NOT NULL,
    subtotal_mxn                TEXT    NOT NULL,
    iva_mxn                     TEXT    NOT NULL,
    facturacion_periodo_mxn     TEXT    NOT NULL,
    derecho_alumbrado_publico_mxn TEXT  NOT NULL,
    credito_aplicado_mxn        TEXT    NOT NULL,
    total_mxn                   TEXT    NOT NULL,
    pdf_path                    TEXT    NOT NULL,
    advertencias                TEXT    NOT NULL DEFAULT '[]',
    created_at                  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cfe_periodos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    factura_id          INTEGER NOT NULL REFERENCES cfe_facturas(id) ON DELETE CASCADE,
    periodo             TEXT    NOT NULL,
    consumo_kwh         TEXT    NOT NULL,
    demanda_kw          TEXT    NOT NULL,
    costo_unitario_kwh  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS cfe_mem_componentes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    factura_id          INTEGER NOT NULL REFERENCES cfe_facturas(id) ON DELETE CASCADE,
    nombre              TEXT    NOT NULL,
    cargo_fijo_mxn      TEXT    NOT NULL,
    cargo_demanda_mxn   TEXT    NOT NULL,
    cargo_energia_mxn   TEXT    NOT NULL,
    importe_mxn         TEXT    NOT NULL
);
"""


def init_db(conn: sqlite3.Connection) -> None:
    """Crea las tablas si no existen. Seguro de llamar múltiples veces."""
    conn.executescript(DDL)
    conn.commit()
```

- [ ] **Step 4: Ejecutar tests y verificar que pasan**

```bash
pytest tests/storage/test_schema.py -v
```

Expected: 4 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add storage/schema.py tests/storage/test_schema.py
git commit -m "feat: schema SQLite con tablas clientes, cfe_facturas, periodos y MEM"
```

---

## Task 6: Repositorio CFEInvoice

**Files:**
- Create: `storage/repository.py`
- Test: `tests/storage/test_repository.py`

- [ ] **Step 1: Escribir test de round-trip**

Crear `tests/storage/test_repository.py`:

```python
import json
import sqlite3
from dataclasses import asdict
from datetime import date
from decimal import Decimal
import pytest

from models.cfe_invoice import CFEInvoice, CFEConsumoHorario, MEMComponente
from storage.schema import init_db
from storage.repository import save_cfe_invoice, load_cfe_invoice, list_cfe_invoices


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    init_db(c)
    yield c
    c.close()


def _invoice_minima() -> CFEInvoice:
    return CFEInvoice(
        uuid_cfdi=None,
        folio="000060832477",
        serie="PB",
        fecha_emision=date(2023, 12, 4),
        periodo_inicio=date(2023, 11, 7),
        periodo_fin=date(2023, 11, 30),
        fecha_limite_pago=date(2023, 12, 14),
        nombre_cliente="IBERICA TILES SAPI DE CV",
        rfc_cliente="ITI170630377",
        numero_servicio="052231189271",
        rmu="36880 23-11-03",
        tarifa="GDMTH",
        numero_medidor="905CFJ",
        multiplicador=2800,
        carga_conectada_kw=Decimal("3200"),
        demanda_contratada_kw=Decimal("3200"),
        periodos=[
            CFEConsumoHorario("base",       Decimal("128800"), Decimal("1204"), Decimal("0.882900")),
            CFEConsumoHorario("intermedio", Decimal("204400"), Decimal("1232"), Decimal("1.722781")),
            CFEConsumoHorario("punta",      Decimal("47600"),  Decimal("1232"), Decimal("1.990648")),
        ],
        kw_max=Decimal("1232"),
        kvArh=Decimal("282800"),
        factor_potencia_pct=Decimal("80.28"),
        componentes_mem=[
            MEMComponente("Suministro",   Decimal("233.84"), Decimal("0"),       Decimal("0"),        Decimal("233.84")),
            MEMComponente("Distribución", Decimal("0"),      Decimal("94100.81"),Decimal("0"),        Decimal("94100.81")),
            MEMComponente("Generación B", Decimal("0"),      Decimal("0"),       Decimal("113704.64"),Decimal("113704.64")),
        ],
        cargo_fijo_mxn=Decimal("233.84"),
        energia_total_mxn=Decimal("1099705.11"),
        cargo_factor_potencia_mxn=Decimal("80295.54"),
        subtotal_mxn=Decimal("1180234.49"),
        iva_mxn=Decimal("188837.52"),
        facturacion_periodo_mxn=Decimal("1369072.01"),
        derecho_alumbrado_publico_mxn=Decimal("515.84"),
        credito_aplicado_mxn=Decimal("-242816.00"),
        total_mxn=Decimal("1126771.85"),
        pdf_path="tests/fixtures/cfe/P2_2023_11_NOVIEMBRE.pdf",
        advertencias=["advertencia de prueba"],
    )


def test_save_devuelve_id_entero(conn):
    inv = _invoice_minima()
    factura_id = save_cfe_invoice(conn, inv)
    assert isinstance(factura_id, int)
    assert factura_id > 0


def test_load_recupera_campos_simples(conn):
    inv = _invoice_minima()
    factura_id = save_cfe_invoice(conn, inv)
    cargada = load_cfe_invoice(conn, factura_id)

    assert cargada.folio == "000060832477"
    assert cargada.tarifa == "GDMTH"
    assert cargada.multiplicador == 2800
    assert cargada.rfc_cliente == "ITI170630377"
    assert cargada.credito_aplicado_mxn == Decimal("-242816.00")


def test_load_recupera_periodos(conn):
    inv = _invoice_minima()
    factura_id = save_cfe_invoice(conn, inv)
    cargada = load_cfe_invoice(conn, factura_id)

    assert len(cargada.periodos) == 3
    base = next(p for p in cargada.periodos if p.periodo == "base")
    assert base.consumo_kwh == Decimal("128800")
    assert base.costo_unitario_kwh == Decimal("0.882900")


def test_load_recupera_mem_componentes(conn):
    inv = _invoice_minima()
    factura_id = save_cfe_invoice(conn, inv)
    cargada = load_cfe_invoice(conn, factura_id)

    assert len(cargada.componentes_mem) == 3
    gen_b = next(c for c in cargada.componentes_mem if c.nombre == "Generación B")
    assert gen_b.importe_mxn == Decimal("113704.64")


def test_load_recupera_advertencias(conn):
    inv = _invoice_minima()
    factura_id = save_cfe_invoice(conn, inv)
    cargada = load_cfe_invoice(conn, factura_id)
    assert "advertencia de prueba" in cargada.advertencias


def test_load_factura_inexistente_lanza_error(conn):
    with pytest.raises(ValueError, match="no encontrada"):
        load_cfe_invoice(conn, 9999)


def test_list_devuelve_facturas_guardadas(conn):
    inv = _invoice_minima()
    save_cfe_invoice(conn, inv)
    save_cfe_invoice(conn, inv)  # mismo RFC, misma factura (sin constraint UNIQUE en folio)
    facturas = list_cfe_invoices(conn)
    assert len(facturas) == 2


def test_mismo_cliente_no_duplica_en_clientes(conn):
    inv = _invoice_minima()
    save_cfe_invoice(conn, inv)
    save_cfe_invoice(conn, inv)
    count = conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
    assert count == 1
```

- [ ] **Step 2: Ejecutar test y verificar que falla**

```bash
pytest tests/storage/test_repository.py -v 2>&1 | head -20
```

Expected: `ImportError: No module named 'storage.repository'`

- [ ] **Step 3: Crear storage/repository.py**

```python
import json
import sqlite3
from datetime import date
from decimal import Decimal

from models.cfe_invoice import CFEInvoice, CFEConsumoHorario, MEMComponente


def _upsert_cliente(conn: sqlite3.Connection, nombre: str, rfc: str) -> int:
    """Inserta o reutiliza el cliente por RFC. Devuelve su id."""
    row = conn.execute("SELECT id FROM clientes WHERE rfc = ?", (rfc,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO clientes (nombre, rfc) VALUES (?, ?)",
        (nombre, rfc),
    )
    conn.commit()
    return cur.lastrowid


def save_cfe_invoice(conn: sqlite3.Connection, invoice: CFEInvoice) -> int:
    """Persiste un CFEInvoice completo. Devuelve el id de la fila en cfe_facturas."""
    cliente_id = _upsert_cliente(conn, invoice.nombre_cliente, invoice.rfc_cliente)

    cur = conn.execute(
        """
        INSERT INTO cfe_facturas (
            cliente_id, uuid_cfdi, folio, serie,
            fecha_emision, periodo_inicio, periodo_fin, fecha_limite_pago,
            numero_servicio, rmu, tarifa, numero_medidor, multiplicador,
            carga_conectada_kw, demanda_contratada_kw,
            kw_max, kvArh, factor_potencia_pct,
            cargo_fijo_mxn, energia_total_mxn, cargo_factor_potencia_mxn,
            subtotal_mxn, iva_mxn, facturacion_periodo_mxn,
            derecho_alumbrado_publico_mxn, credito_aplicado_mxn, total_mxn,
            pdf_path, advertencias
        ) VALUES (
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
        )
        """,
        (
            cliente_id,
            invoice.uuid_cfdi,
            invoice.folio,
            invoice.serie,
            invoice.fecha_emision.isoformat(),
            invoice.periodo_inicio.isoformat(),
            invoice.periodo_fin.isoformat(),
            invoice.fecha_limite_pago.isoformat(),
            invoice.numero_servicio,
            invoice.rmu,
            invoice.tarifa,
            invoice.numero_medidor,
            invoice.multiplicador,
            str(invoice.carga_conectada_kw),
            str(invoice.demanda_contratada_kw),
            str(invoice.kw_max),
            str(invoice.kvArh),
            str(invoice.factor_potencia_pct),
            str(invoice.cargo_fijo_mxn),
            str(invoice.energia_total_mxn),
            str(invoice.cargo_factor_potencia_mxn),
            str(invoice.subtotal_mxn),
            str(invoice.iva_mxn),
            str(invoice.facturacion_periodo_mxn),
            str(invoice.derecho_alumbrado_publico_mxn),
            str(invoice.credito_aplicado_mxn),
            str(invoice.total_mxn),
            invoice.pdf_path,
            json.dumps(invoice.advertencias, ensure_ascii=False),
        ),
    )
    factura_id = cur.lastrowid

    for p in invoice.periodos:
        conn.execute(
            "INSERT INTO cfe_periodos (factura_id, periodo, consumo_kwh, demanda_kw, costo_unitario_kwh) "
            "VALUES (?,?,?,?,?)",
            (factura_id, p.periodo, str(p.consumo_kwh), str(p.demanda_kw), str(p.costo_unitario_kwh)),
        )

    for c in invoice.componentes_mem:
        conn.execute(
            "INSERT INTO cfe_mem_componentes "
            "(factura_id, nombre, cargo_fijo_mxn, cargo_demanda_mxn, cargo_energia_mxn, importe_mxn) "
            "VALUES (?,?,?,?,?,?)",
            (factura_id, c.nombre, str(c.cargo_fijo_mxn), str(c.cargo_demanda_mxn),
             str(c.cargo_energia_mxn), str(c.importe_mxn)),
        )

    conn.commit()
    return factura_id


def load_cfe_invoice(conn: sqlite3.Connection, factura_id: int) -> CFEInvoice:
    """Carga un CFEInvoice completo desde SQLite."""
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT f.*, cl.nombre AS nombre_cliente, cl.rfc AS rfc_cliente
        FROM cfe_facturas f
        JOIN clientes cl ON cl.id = f.cliente_id
        WHERE f.id = ?
        """,
        (factura_id,),
    ).fetchone()

    if row is None:
        raise ValueError(f"Factura CFE con id={factura_id} no encontrada")

    periodos_rows = conn.execute(
        "SELECT * FROM cfe_periodos WHERE factura_id = ? ORDER BY id",
        (factura_id,),
    ).fetchall()

    mem_rows = conn.execute(
        "SELECT * FROM cfe_mem_componentes WHERE factura_id = ? ORDER BY id",
        (factura_id,),
    ).fetchall()

    periodos = [
        CFEConsumoHorario(
            periodo=r["periodo"],
            consumo_kwh=Decimal(r["consumo_kwh"]),
            demanda_kw=Decimal(r["demanda_kw"]),
            costo_unitario_kwh=Decimal(r["costo_unitario_kwh"]),
        )
        for r in periodos_rows
    ]

    componentes_mem = [
        MEMComponente(
            nombre=r["nombre"],
            cargo_fijo_mxn=Decimal(r["cargo_fijo_mxn"]),
            cargo_demanda_mxn=Decimal(r["cargo_demanda_mxn"]),
            cargo_energia_mxn=Decimal(r["cargo_energia_mxn"]),
            importe_mxn=Decimal(r["importe_mxn"]),
        )
        for r in mem_rows
    ]

    return CFEInvoice(
        uuid_cfdi=row["uuid_cfdi"],
        folio=row["folio"],
        serie=row["serie"],
        fecha_emision=date.fromisoformat(row["fecha_emision"]),
        periodo_inicio=date.fromisoformat(row["periodo_inicio"]),
        periodo_fin=date.fromisoformat(row["periodo_fin"]),
        fecha_limite_pago=date.fromisoformat(row["fecha_limite_pago"]),
        nombre_cliente=row["nombre_cliente"],
        rfc_cliente=row["rfc_cliente"],
        numero_servicio=row["numero_servicio"],
        rmu=row["rmu"],
        tarifa=row["tarifa"],
        numero_medidor=row["numero_medidor"],
        multiplicador=row["multiplicador"],
        carga_conectada_kw=Decimal(row["carga_conectada_kw"]),
        demanda_contratada_kw=Decimal(row["demanda_contratada_kw"]),
        periodos=periodos,
        kw_max=Decimal(row["kw_max"]),
        kvArh=Decimal(row["kvArh"]),
        factor_potencia_pct=Decimal(row["factor_potencia_pct"]),
        componentes_mem=componentes_mem,
        cargo_fijo_mxn=Decimal(row["cargo_fijo_mxn"]),
        energia_total_mxn=Decimal(row["energia_total_mxn"]),
        cargo_factor_potencia_mxn=Decimal(row["cargo_factor_potencia_mxn"]),
        subtotal_mxn=Decimal(row["subtotal_mxn"]),
        iva_mxn=Decimal(row["iva_mxn"]),
        facturacion_periodo_mxn=Decimal(row["facturacion_periodo_mxn"]),
        derecho_alumbrado_publico_mxn=Decimal(row["derecho_alumbrado_publico_mxn"]),
        credito_aplicado_mxn=Decimal(row["credito_aplicado_mxn"]),
        total_mxn=Decimal(row["total_mxn"]),
        pdf_path=row["pdf_path"],
        advertencias=json.loads(row["advertencias"]),
    )


def list_cfe_invoices(conn: sqlite3.Connection) -> list[dict]:
    """Devuelve resumen de todas las facturas CFE (id, rfc, periodo, total)."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT f.id, cl.rfc, cl.nombre, f.tarifa, f.periodo_inicio, f.periodo_fin,
               f.facturacion_periodo_mxn, f.total_mxn
        FROM cfe_facturas f
        JOIN clientes cl ON cl.id = f.cliente_id
        ORDER BY f.periodo_inicio
        """
    ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Ejecutar tests y verificar que pasan**

```bash
pytest tests/storage/test_repository.py -v
```

Expected: 8 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add storage/repository.py tests/storage/test_repository.py
git commit -m "feat: repositorio SQLite para CFEInvoice con save/load/list"
```

---

## Task 7: CLI — entry point

**Files:**
- Create: `cli/main.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Escribir test end-to-end**

Crear `tests/test_cli.py`:

```python
import sqlite3
from pathlib import Path
import pytest
from cli.main import procesar_factura_cfe
from storage.schema import init_db
from storage.repository import load_cfe_invoice

FIXTURE = Path("tests/fixtures/cfe/P2_2023_11_NOVIEMBRE.pdf")


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    yield conn
    conn.close()


def test_procesar_factura_cfe_devuelve_id(db_conn):
    factura_id = procesar_factura_cfe(FIXTURE, db_conn, tarifa="GDMTH")
    assert isinstance(factura_id, int)
    assert factura_id > 0


def test_factura_persiste_en_db(db_conn):
    factura_id = procesar_factura_cfe(FIXTURE, db_conn, tarifa="GDMTH")
    inv = load_cfe_invoice(db_conn, factura_id)
    assert inv.tarifa == "GDMTH"
    assert inv.numero_servicio == "052231189271"


def test_procesar_tarifa_no_soportada_lanza_error(db_conn):
    with pytest.raises(ValueError, match="no soportada"):
        procesar_factura_cfe(FIXTURE, db_conn, tarifa="GDMTO")


def test_procesar_pdf_inexistente_lanza_error(db_conn):
    with pytest.raises(FileNotFoundError):
        procesar_factura_cfe(Path("no_existe.pdf"), db_conn)
```

- [ ] **Step 2: Ejecutar test y verificar que falla**

```bash
pytest tests/test_cli.py -v 2>&1 | head -20
```

Expected: `ImportError: No module named 'cli.main'`

- [ ] **Step 3: Crear cli/main.py**

```python
"""
CLI para procesar facturas CFE e insertarlas en SQLite.

Uso:
    python -m cli.main ruta/factura.pdf [--tarifa GDMTH] [--db chpapp.db]
"""
import argparse
import sqlite3
from pathlib import Path

from parsers.cfe import get_cfe_parser
from storage.schema import init_db
from storage.repository import save_cfe_invoice, list_cfe_invoices


def procesar_factura_cfe(
    pdf_path: Path,
    conn: sqlite3.Connection,
    tarifa: str = "GDMTH",
) -> int:
    """
    Parsea una factura CFE, valida coherencia y persiste en SQLite.

    Args:
        pdf_path: Ruta al archivo PDF.
        conn: Conexión SQLite ya inicializada.
        tarifa: Código de tarifa CFE. Default "GDMTH".

    Returns:
        ID de la factura insertada en cfe_facturas.

    Raises:
        FileNotFoundError: Si el PDF no existe.
        ValueError: Si la tarifa no está soportada.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF no encontrado: {pdf_path}")

    parser = get_cfe_parser(tarifa)  # lanza ValueError si tarifa no existe
    invoice = parser.parse(pdf_path)
    errores = parser.validate(invoice)

    if errores:
        print(f"[ADVERTENCIA] Errores de validación ({len(errores)}):")
        for e in errores:
            print(f"  - {e}")

    if invoice.advertencias:
        print(f"[ADVERTENCIA] Campos no encontrados en el PDF ({len(invoice.advertencias)}):")
        for a in invoice.advertencias:
            print(f"  - {a}")

    factura_id = save_cfe_invoice(conn, invoice)
    print(f"[OK] Factura guardada: id={factura_id}, periodo={invoice.periodo_inicio}→{invoice.periodo_fin}, "
          f"total_periodo=${invoice.facturacion_periodo_mxn:,.2f}")
    return factura_id


def _main() -> None:
    parser = argparse.ArgumentParser(description="Procesador de facturas CFE")
    parser.add_argument("pdf", help="Ruta al PDF de la factura CFE")
    parser.add_argument("--tarifa", default="GDMTH", help="Tarifa CFE (default: GDMTH)")
    parser.add_argument("--db", default="chpapp.db", help="Ruta a la base de datos SQLite")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)

    try:
        procesar_factura_cfe(Path(args.pdf), conn, tarifa=args.tarifa)
    finally:
        conn.close()


if __name__ == "__main__":
    _main()
```

- [ ] **Step 4: Ejecutar todos los tests**

```bash
pytest tests/test_cli.py -v
```

Expected: 4 tests PASSED.

- [ ] **Step 5: Ejecutar suite completa**

```bash
pytest -v
```

Expected: todos los tests PASSED. Zero failures.

- [ ] **Step 6: Probar CLI manualmente con el PDF real**

```bash
python -m cli.main "tests/fixtures/cfe/P2_2023_11_NOVIEMBRE.pdf" --db /tmp/prueba.db
```

Expected:
```
[OK] Factura guardada: id=1, periodo=2023-11-07→2023-11-30, total_periodo=$1,369,072.01
```

- [ ] **Step 7: Commit final**

```bash
git add cli/ tests/test_cli.py
git commit -m "feat: CLI procesar_factura_cfe end-to-end — Entregable 1 completo"
```

---

## Self-Review

**Spec coverage:**

| Requisito (CLAUDE.md) | Tarea que lo implementa |
|---|---|
| Parser CFE funcional sobre factura real | Task 4 |
| Devuelve objeto estructurado con todos los campos | Tasks 2 + 4 |
| Persistencia básica en SQLite | Tasks 5 + 6 |
| Ejecución por línea de comandos | Task 7 |
| Parsers intercambiables vía interfaz común | Task 3 (InvoiceParser ABC) |
| Arquitectura extensible a múltiples tarifas | Task 3 (CFEParser base) + `get_cfe_parser()` factory |
| DB multi-cliente desde el inicio | Task 5 (tabla `clientes` separada) |
| Modelo de datos GasInvoice listo para Entregable 2 | Task 2 |
| Decimal para valores monetarios | Tasks 2, 4, 6 |
| `facturacion_periodo_mxn` (no `total_mxn`) como costo real | Tasks 2, 4, 6 |

**Placeholder scan:** Ninguno encontrado. Todo el código está completo.

**Type consistency:** Los métodos estáticos `_parse_fecha_es` y `_parse_decimal` se definen en `CFEParser` (Task 3) y se usan en `GDMTHParser` (Task 4) con la misma signature. El `procesar_factura_cfe` en CLI recibe `conn: sqlite3.Connection` ya inicializado, consistente con los fixtures de test.
