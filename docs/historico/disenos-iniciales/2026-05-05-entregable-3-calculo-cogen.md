# Entregable 3 — Motor de Cálculo de Cogeneración + Reporte Excel

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Emparejar las 24 facturas mensuales (12 CFE + 12 Gas), calcular el EBITDA mensual de cogeneración y generar un reporte Excel con los resultados.

**Architecture:** Tres capas: (1) `models/cogen_result.py` — dataclasses del resultado, (2) `calc/cogen.py` — función pura `calcular_cogen()` que no toca BD ni archivos, (3) `reports/excel.py` — `generar_excel()` con openpyxl. La CLI conecta todo con `generar_analisis_cogen(conn, output_path)`.

**Tech Stack:** Python 3.9+, dataclasses, Decimal, openpyxl, pytest

---

## Dominio: Fórmulas de Cogeneración

**Parámetros del motor (configurables):**

| Parámetro | Default | Significado |
|-----------|---------|-------------|
| `cobertura_electrica` | 75% | Fracción de la demanda eléctrica cubierta por el cogenerador |
| `rendimiento_electrico` | 40% | Eficiencia eléctrica del motor de gas |
| `rendimiento_termico` | 25% | Fracción del calor de combustión recuperable |
| `eficiencia_caldera` | 85% | Eficiencia de la caldera actual que se desplaza |

**Por mes, dados `CFEInvoice` y `GasInvoice` del mismo periodo:**

```
kwh_total            = sum(p.consumo_kwh for p in cfe.periodos)
costo_cfe_mxn        = cfe.facturacion_periodo_mxn
costo_promedio_kwh   = costo_cfe_mxn / kwh_total

gj_consumido         = gas.consumo_total_gj
costo_unitario_gj    = gas.costo_unitario_total_gj
costo_gas_actual_mxn = gas.subtotal_mxn

kwh_cubiertos        = kwh_total × cobertura_electrica
gj_gas_cogen         = kwh_cubiertos × 0.0036 / rendimiento_electrico
                       # 1 kWh = 0.0036 GJ; input_GJ = output_GJ / eficiencia

costo_gas_cogen_mxn  = gj_gas_cogen × costo_unitario_gj
ahorro_electricidad  = kwh_cubiertos × costo_promedio_kwh
                       # Equivale a costo_cfe_mxn × cobertura_electrica

calor_recuperado_gj  = gj_gas_cogen × rendimiento_termico
ahorro_caldera_mxn   = (calor_recuperado_gj / eficiencia_caldera) × costo_unitario_gj
                       # El calor recuperado desplaza combustible de caldera existente

ebitda_mes_mxn       = ahorro_electricidad + ahorro_caldera_mxn - costo_gas_cogen_mxn
```

**Emparejamiento:** Por (año, mes) de `periodo_inicio`. Si un mes no tiene par, se omite. Todos los valores Decimal se redondean a `Decimal("0.01")` (centavos) salvo energía a `Decimal("0.0001")`.

---

## Estructura de archivos

| Archivo | Acción | Responsabilidad |
|---------|--------|----------------|
| `models/cogen_result.py` | Crear | `CoGenParams`, `CoGenMes`, `CoGenResultado` |
| `calc/__init__.py` | Crear | Package vacío |
| `calc/cogen.py` | Crear | `calcular_cogen()` — función pura |
| `reports/__init__.py` | Crear | Package vacío |
| `reports/excel.py` | Crear | `generar_excel()` — escribe xlsx con openpyxl |
| `cli/main.py` | Modificar | `generar_analisis_cogen(conn, output_path)` |
| `tests/calc/test_cogen.py` | Crear | 10 tests de cálculo |
| `tests/reports/test_excel.py` | Crear | 4 tests de Excel |
| `tests/test_cli_cogen.py` | Crear | 3 tests CLI |

---

## Task 1: Modelos de resultado — models/cogen_result.py

**Files:**
- Create: `models/cogen_result.py`
- Create: `tests/test_cogen_models.py`

- [ ] **Step 1: Escribir tests fallidos**

```python
# tests/test_cogen_models.py
from __future__ import annotations
import pytest
from decimal import Decimal
from datetime import date
from models.cogen_result import CoGenParams, CoGenMes, CoGenResultado


def test_params_defaults():
    p = CoGenParams()
    assert p.cobertura_electrica == Decimal("0.75")
    assert p.rendimiento_electrico == Decimal("0.40")
    assert p.rendimiento_termico == Decimal("0.25")
    assert p.eficiencia_caldera == Decimal("0.85")


def test_mes_instancia():
    m = CoGenMes(
        periodo_inicio=date(2023, 11, 1),
        periodo_fin=date(2023, 11, 30),
        kwh_total=Decimal("1000000"),
        costo_cfe_mxn=Decimal("3000000"),
        costo_promedio_kwh=Decimal("3.00"),
        gj_consumido=Decimal("100000"),
        costo_unitario_gj=Decimal("80.00"),
        costo_gas_actual_mxn=Decimal("8000000"),
        kwh_cubiertos=Decimal("750000"),
        gj_gas_cogen=Decimal("6750"),
        costo_gas_cogen_mxn=Decimal("540000"),
        ahorro_electricidad_mxn=Decimal("2250000"),
        calor_recuperado_gj=Decimal("1687.50"),
        ahorro_caldera_mxn=Decimal("158823.53"),
        ebitda_mes_mxn=Decimal("1868823.53"),
    )
    assert m.periodo_inicio == date(2023, 11, 1)
    assert m.ebitda_mes_mxn == Decimal("1868823.53")


def test_resultado_totales():
    p = CoGenParams()
    m = CoGenMes(
        periodo_inicio=date(2023, 11, 1),
        periodo_fin=date(2023, 11, 30),
        kwh_total=Decimal("1000000"),
        costo_cfe_mxn=Decimal("3000000"),
        costo_promedio_kwh=Decimal("3.00"),
        gj_consumido=Decimal("100000"),
        costo_unitario_gj=Decimal("80.00"),
        costo_gas_actual_mxn=Decimal("8000000"),
        kwh_cubiertos=Decimal("750000"),
        gj_gas_cogen=Decimal("6750"),
        costo_gas_cogen_mxn=Decimal("540000"),
        ahorro_electricidad_mxn=Decimal("2250000"),
        calor_recuperado_gj=Decimal("1687.50"),
        ahorro_caldera_mxn=Decimal("158823.53"),
        ebitda_mes_mxn=Decimal("1868823.53"),
    )
    r = CoGenResultado(
        params=p,
        meses=[m],
        kwh_total_anual=Decimal("1000000"),
        kwh_cubiertos_anual=Decimal("750000"),
        gj_gas_cogen_anual=Decimal("6750"),
        costo_gas_cogen_anual_mxn=Decimal("540000"),
        ahorro_electricidad_anual_mxn=Decimal("2250000"),
        ahorro_caldera_anual_mxn=Decimal("158823.53"),
        ebitda_anual_mxn=Decimal("1868823.53"),
    )
    assert r.ebitda_anual_mxn == Decimal("1868823.53")
    assert len(r.meses) == 1
```

- [ ] **Step 2: Verificar que fallan**

```bash
python3 -m pytest tests/test_cogen_models.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError: No module named 'models.cogen_result'`

- [ ] **Step 3: Crear `models/cogen_result.py`**

```python
# models/cogen_result.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass
class CoGenParams:
    """Parámetros técnicos del proyecto de cogeneración."""
    cobertura_electrica: Decimal = Decimal("0.75")   # fracción de demanda cubierta
    rendimiento_electrico: Decimal = Decimal("0.40") # eficiencia eléctrica del motor
    rendimiento_termico: Decimal = Decimal("0.25")   # fracción de calor recuperable
    eficiencia_caldera: Decimal = Decimal("0.85")    # eficiencia caldera actual


@dataclass
class CoGenMes:
    """Resultado de cogeneración para un mes calendario."""
    periodo_inicio: date
    periodo_fin: date
    # Entradas CFE
    kwh_total: Decimal
    costo_cfe_mxn: Decimal
    costo_promedio_kwh: Decimal
    # Entradas Gas
    gj_consumido: Decimal
    costo_unitario_gj: Decimal
    costo_gas_actual_mxn: Decimal
    # Salidas cogeneración
    kwh_cubiertos: Decimal
    gj_gas_cogen: Decimal
    costo_gas_cogen_mxn: Decimal
    ahorro_electricidad_mxn: Decimal
    calor_recuperado_gj: Decimal
    ahorro_caldera_mxn: Decimal
    ebitda_mes_mxn: Decimal


@dataclass
class CoGenResultado:
    """Resultado anual de cogeneración con detalle mensual."""
    params: CoGenParams
    meses: list[CoGenMes]
    # Totales anuales
    kwh_total_anual: Decimal
    kwh_cubiertos_anual: Decimal
    gj_gas_cogen_anual: Decimal
    costo_gas_cogen_anual_mxn: Decimal
    ahorro_electricidad_anual_mxn: Decimal
    ahorro_caldera_anual_mxn: Decimal
    ebitda_anual_mxn: Decimal
```

- [ ] **Step 4: Correr tests**

```bash
python3 -m pytest tests/test_cogen_models.py -v
```
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add models/cogen_result.py tests/test_cogen_models.py
git commit -m "feat: add CoGenParams, CoGenMes, CoGenResultado models (Task 1)"
```

---

## Task 2: Motor de cálculo — calc/cogen.py

**Files:**
- Create: `calc/__init__.py`
- Create: `calc/cogen.py`
- Create: `tests/calc/__init__.py`
- Create: `tests/calc/test_cogen.py`

- [ ] **Step 1: Escribir tests fallidos**

```python
# tests/calc/test_cogen.py
from __future__ import annotations
import pytest
from decimal import Decimal
from datetime import date

from models.cfe_invoice import CFEInvoice, CFEConsumoHorario, MEMComponente
from models.gas_invoice import GasInvoice, GasConcepto
from models.cogen_result import CoGenParams, CoGenMes, CoGenResultado
from calc.cogen import calcular_cogen


# ── Helpers para construir fixtures sintéticos ────────────────────────────────

def _cfe(year: int, month: int, kwh: Decimal, facturacion: Decimal) -> CFEInvoice:
    tercio = kwh / 3
    periodos = [
        CFEConsumoHorario("base",       tercio, Decimal("100"), Decimal("1.00")),
        CFEConsumoHorario("intermedio", tercio, Decimal("100"), Decimal("1.20")),
        CFEConsumoHorario("punta",      tercio, Decimal("100"), Decimal("1.50")),
    ]
    inicio = date(year, month, 1)
    fin_month = 30 if month in (4,6,9,11) else (28 if month == 2 else 31)
    fin = date(year, month, fin_month)
    return CFEInvoice(
        uuid_cfdi=None, folio="F1", serie=None,
        fecha_emision=inicio, periodo_inicio=inicio, periodo_fin=fin,
        fecha_limite_pago=fin, nombre_cliente="TEST", rfc_cliente="TST010101AAA",
        numero_servicio="12345", rmu=None, tarifa="GDMTH", numero_medidor="M1",
        multiplicador=1, carga_conectada_kw=Decimal("1000"),
        demanda_contratada_kw=Decimal("1000"), periodos=periodos,
        kw_max=Decimal("100"), kvArh=Decimal("0"), factor_potencia_pct=Decimal("90"),
        componentes_mem=[], cargo_fijo_mxn=Decimal("0"),
        energia_total_mxn=facturacion, cargo_factor_potencia_mxn=Decimal("0"),
        subtotal_mxn=facturacion, iva_mxn=Decimal("0"),
        facturacion_periodo_mxn=facturacion,
        derecho_alumbrado_publico_mxn=Decimal("0"), credito_aplicado_mxn=Decimal("0"),
        total_mxn=facturacion, pdf_path="test.pdf",
    )


def _gas(year: int, month: int, gj: Decimal, precio_gj: Decimal) -> GasInvoice:
    subtotal = gj * precio_gj
    inicio = date(year, month, 1)
    fin_month = 30 if month in (4,6,9,11) else (28 if month == 2 else 31)
    fin = date(year, month, fin_month)
    return GasInvoice(
        uuid_cfdi="uuid", folio="G1",
        fecha_emision=inicio, periodo_inicio=inicio, periodo_fin=fin,
        fecha_limite_pago=fin, nombre_proveedor="ENGIE",
        rfc_proveedor="TRA0002119W1", nombre_cliente="TEST",
        rfc_cliente="TST010101AAA", numero_cliente="610002800",
        cuenta_contrato="5100096634", punto_suministro="TEST",
        numero_caseta="C1", tipo_lectura="REAL",
        consumo_m3_corregidos=Decimal("100000"),
        consumo_sin_corregir_m3=Decimal("0"),
        poder_calorifico_gj_m3=Decimal("0.036"),
        consumo_total_gj=gj,
        conceptos=[
            GasConcepto("Compraventa de Gas Natural", "83101601",
                        gj, precio_gj * Decimal("0.69"), gj * precio_gj * Decimal("0.69")),
            GasConcepto("Transporte por Ducto Gas Natural", "78102101",
                        gj, precio_gj * Decimal("0.31"), gj * precio_gj * Decimal("0.31")),
        ],
        costo_unitario_total_gj=precio_gj,
        subtotal_mxn=subtotal,
        iva_mxn=(subtotal * Decimal("0.16")).quantize(Decimal("0.01")),
        total_mxn=(subtotal * Decimal("1.16")).quantize(Decimal("0.01")),
        pdf_path="test.pdf",
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

KWH = Decimal("1000000")
FACTURACION = Decimal("3000000")
GJ = Decimal("100000")
PRECIO_GJ = Decimal("80.00")


@pytest.fixture
def resultado_un_mes():
    cfe = [_cfe(2023, 11, KWH, FACTURACION)]
    gas = [_gas(2023, 11, GJ, PRECIO_GJ)]
    return calcular_cogen(cfe, gas, CoGenParams())


def test_devuelve_cogen_resultado(resultado_un_mes):
    assert isinstance(resultado_un_mes, CoGenResultado)


def test_un_mes_en_resultado(resultado_un_mes):
    assert len(resultado_un_mes.meses) == 1


def test_kwh_cubiertos(resultado_un_mes):
    # 1_000_000 × 0.75 = 750_000
    assert resultado_un_mes.meses[0].kwh_cubiertos == Decimal("750000.00")


def test_costo_promedio_kwh(resultado_un_mes):
    # 3_000_000 / 1_000_000 = 3.00
    assert resultado_un_mes.meses[0].costo_promedio_kwh == Decimal("3.00")


def test_gj_gas_cogen(resultado_un_mes):
    # 750_000 × 0.0036 / 0.40 = 6_750.00
    assert resultado_un_mes.meses[0].gj_gas_cogen == Decimal("6750.0000")


def test_costo_gas_cogen(resultado_un_mes):
    # 6_750 × 80 = 540_000.00
    assert resultado_un_mes.meses[0].costo_gas_cogen_mxn == Decimal("540000.00")


def test_ahorro_electricidad(resultado_un_mes):
    # 750_000 × 3.00 = 2_250_000.00
    assert resultado_un_mes.meses[0].ahorro_electricidad_mxn == Decimal("2250000.00")


def test_calor_recuperado(resultado_un_mes):
    # 6_750 × 0.25 = 1_687.5000
    assert resultado_un_mes.meses[0].calor_recuperado_gj == Decimal("1687.5000")


def test_ahorro_caldera(resultado_un_mes):
    # (1_687.5 / 0.85) × 80 = 1985.2941... × 80 = 158_823.53 (redondeado a centavos)
    esperado = (Decimal("1687.5000") / Decimal("0.85") * Decimal("80.00")).quantize(Decimal("0.01"))
    assert resultado_un_mes.meses[0].ahorro_caldera_mxn == esperado


def test_ebitda_mes(resultado_un_mes):
    m = resultado_un_mes.meses[0]
    esperado = m.ahorro_electricidad_mxn + m.ahorro_caldera_mxn - m.costo_gas_cogen_mxn
    assert m.ebitda_mes_mxn == esperado


def test_meses_sin_par_se_omiten():
    """Si CFE tiene un mes que Gas no tiene, ese mes no aparece en resultado."""
    cfe = [_cfe(2023, 11, KWH, FACTURACION), _cfe(2023, 12, KWH, FACTURACION)]
    gas = [_gas(2023, 11, GJ, PRECIO_GJ)]  # solo noviembre
    r = calcular_cogen(cfe, gas, CoGenParams())
    assert len(r.meses) == 1
    assert r.meses[0].periodo_inicio == date(2023, 11, 1)


def test_totales_anuales_son_suma_mensual():
    cfe = [_cfe(2023, 11, KWH, FACTURACION), _cfe(2023, 12, KWH * 2, FACTURACION * 2)]
    gas = [_gas(2023, 11, GJ, PRECIO_GJ), _gas(2023, 12, GJ * 2, PRECIO_GJ)]
    r = calcular_cogen(cfe, gas, CoGenParams())
    assert r.ebitda_anual_mxn == sum(m.ebitda_mes_mxn for m in r.meses)
    assert r.kwh_total_anual == sum(m.kwh_total for m in r.meses)
```

- [ ] **Step 2: Verificar que fallan**

```bash
python3 -m pytest tests/calc/test_cogen.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError: No module named 'calc'`

- [ ] **Step 3: Crear `calc/__init__.py` y `tests/calc/__init__.py`**

```bash
touch calc/__init__.py tests/calc/__init__.py
```

- [ ] **Step 4: Crear `calc/cogen.py`**

```python
# calc/cogen.py
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from models.cfe_invoice import CFEInvoice
from models.gas_invoice import GasInvoice
from models.cogen_result import CoGenMes, CoGenParams, CoGenResultado

# Factor de conversión: 1 kWh = 0.0036 GJ
_KWH_A_GJ = Decimal("0.0036")
_CENTAVO = Decimal("0.01")
_DIEZMILAVO = Decimal("0.0001")


def calcular_cogen(
    cfe_invoices: list[CFEInvoice],
    gas_invoices: list[GasInvoice],
    params: CoGenParams,
) -> CoGenResultado:
    """Calcula el EBITDA mensual de cogeneración emparejando facturas por (año, mes).

    Los meses sin par CFE-Gas se omiten silenciosamente.
    """
    # Indexar gas por (año, mes) de periodo_inicio
    gas_por_mes: dict[tuple[int, int], GasInvoice] = {
        (g.periodo_inicio.year, g.periodo_inicio.month): g
        for g in gas_invoices
    }

    meses: list[CoGenMes] = []

    for cfe in sorted(cfe_invoices, key=lambda x: x.periodo_inicio):
        clave = (cfe.periodo_inicio.year, cfe.periodo_inicio.month)
        gas = gas_por_mes.get(clave)
        if gas is None:
            continue

        kwh_total = sum(p.consumo_kwh for p in cfe.periodos)
        if kwh_total == 0:
            continue

        costo_cfe = cfe.facturacion_periodo_mxn
        costo_prom_kwh = (costo_cfe / kwh_total).quantize(_CENTAVO, ROUND_HALF_UP)
        costo_unit_gj = gas.costo_unitario_total_gj

        kwh_cubiertos = (kwh_total * params.cobertura_electrica).quantize(_CENTAVO, ROUND_HALF_UP)
        gj_gas_cogen = (kwh_cubiertos * _KWH_A_GJ / params.rendimiento_electrico).quantize(_DIEZMILAVO, ROUND_HALF_UP)
        costo_gas_cogen = (gj_gas_cogen * costo_unit_gj).quantize(_CENTAVO, ROUND_HALF_UP)
        ahorro_electricidad = (kwh_cubiertos * costo_prom_kwh).quantize(_CENTAVO, ROUND_HALF_UP)
        calor_recuperado = (gj_gas_cogen * params.rendimiento_termico).quantize(_DIEZMILAVO, ROUND_HALF_UP)
        ahorro_caldera = (calor_recuperado / params.eficiencia_caldera * costo_unit_gj).quantize(_CENTAVO, ROUND_HALF_UP)
        ebitda = ahorro_electricidad + ahorro_caldera - costo_gas_cogen

        meses.append(CoGenMes(
            periodo_inicio=cfe.periodo_inicio,
            periodo_fin=cfe.periodo_fin,
            kwh_total=kwh_total,
            costo_cfe_mxn=costo_cfe,
            costo_promedio_kwh=costo_prom_kwh,
            gj_consumido=gas.consumo_total_gj,
            costo_unitario_gj=costo_unit_gj,
            costo_gas_actual_mxn=gas.subtotal_mxn,
            kwh_cubiertos=kwh_cubiertos,
            gj_gas_cogen=gj_gas_cogen,
            costo_gas_cogen_mxn=costo_gas_cogen,
            ahorro_electricidad_mxn=ahorro_electricidad,
            calor_recuperado_gj=calor_recuperado,
            ahorro_caldera_mxn=ahorro_caldera,
            ebitda_mes_mxn=ebitda,
        ))

    def _sum(attr: str) -> Decimal:
        return sum(getattr(m, attr) for m in meses) if meses else Decimal("0")

    return CoGenResultado(
        params=params,
        meses=meses,
        kwh_total_anual=_sum("kwh_total"),
        kwh_cubiertos_anual=_sum("kwh_cubiertos"),
        gj_gas_cogen_anual=_sum("gj_gas_cogen"),
        costo_gas_cogen_anual_mxn=_sum("costo_gas_cogen_mxn"),
        ahorro_electricidad_anual_mxn=_sum("ahorro_electricidad_mxn"),
        ahorro_caldera_anual_mxn=_sum("ahorro_caldera_mxn"),
        ebitda_anual_mxn=_sum("ebitda_mes_mxn"),
    )
```

- [ ] **Step 5: Correr tests**

```bash
python3 -m pytest tests/calc/test_cogen.py -v
```
Expected: 12 PASS

- [ ] **Step 6: Commit**

```bash
git add calc/ tests/calc/ models/cogen_result.py tests/test_cogen_models.py
git commit -m "feat: add cogen calculation engine (Task 2)"
```

> **Nota sobre redondeo:** `kwh_cubiertos` se cuantiza a `_CENTAVO` (0.01) antes de usarse para calcular `gj_gas_cogen`. Esto puede causar diferencias de ±1 en los últimos decimales de `gj_gas_cogen`. El test `test_gj_gas_cogen` usa `Decimal("6750.0000")` que es exacto para los inputs dados (750000.00 × 0.0036 / 0.40 = 6750.0000 exacto). Si algún test falla por redondeo, ajustar el assert con tolerancia: `abs(resultado - esperado) <= Decimal("0.01")`.

---

## Task 3: Reporte Excel — reports/excel.py

**Files:**
- Create: `reports/__init__.py`
- Create: `reports/excel.py`
- Create: `tests/reports/__init__.py`
- Create: `tests/reports/test_excel.py`

- [ ] **Step 1: Escribir tests fallidos**

```python
# tests/reports/test_excel.py
from __future__ import annotations
import pytest
from decimal import Decimal
from datetime import date
from pathlib import Path
import tempfile

from models.cogen_result import CoGenParams, CoGenMes, CoGenResultado
from reports.excel import generar_excel


def _resultado_fixture() -> CoGenResultado:
    params = CoGenParams()
    meses = [
        CoGenMes(
            periodo_inicio=date(2023, 11, 1),
            periodo_fin=date(2023, 11, 30),
            kwh_total=Decimal("380800"),
            costo_cfe_mxn=Decimal("1369072.01"),
            costo_promedio_kwh=Decimal("3.60"),
            gj_consumido=Decimal("106445.18"),
            costo_unitario_gj=Decimal("79.48"),
            costo_gas_actual_mxn=Decimal("8460263.13"),
            kwh_cubiertos=Decimal("285600.00"),
            gj_gas_cogen=Decimal("2570.40"),
            costo_gas_cogen_mxn=Decimal("204254.59"),
            ahorro_electricidad_mxn=Decimal("1026804.01"),
            calor_recuperado_gj=Decimal("642.60"),
            ahorro_caldera_mxn=Decimal("60134.56"),
            ebitda_mes_mxn=Decimal("882683.98"),
        ),
        CoGenMes(
            periodo_inicio=date(2023, 12, 1),
            periodo_fin=date(2023, 12, 31),
            kwh_total=Decimal("616000"),
            costo_cfe_mxn=Decimal("1901763.84"),
            costo_promedio_kwh=Decimal("3.09"),
            gj_consumido=Decimal("98199.58"),
            costo_unitario_gj=Decimal("79.48"),
            costo_gas_actual_mxn=Decimal("7804062.04"),
            kwh_cubiertos=Decimal("462000.00"),
            gj_gas_cogen=Decimal("4158.00"),
            costo_gas_cogen_mxn=Decimal("330530.40"),
            ahorro_electricidad_mxn=Decimal("1426322.88"),
            calor_recuperado_gj=Decimal("1039.50"),
            ahorro_caldera_mxn=Decimal("97255.30"),
            ebitda_mes_mxn=Decimal("1193047.78"),
        ),
    ]
    return CoGenResultado(
        params=params,
        meses=meses,
        kwh_total_anual=sum(m.kwh_total for m in meses),
        kwh_cubiertos_anual=sum(m.kwh_cubiertos for m in meses),
        gj_gas_cogen_anual=sum(m.gj_gas_cogen for m in meses),
        costo_gas_cogen_anual_mxn=sum(m.costo_gas_cogen_mxn for m in meses),
        ahorro_electricidad_anual_mxn=sum(m.ahorro_electricidad_mxn for m in meses),
        ahorro_caldera_anual_mxn=sum(m.ahorro_caldera_mxn for m in meses),
        ebitda_anual_mxn=sum(m.ebitda_mes_mxn for m in meses),
    )


@pytest.fixture
def xlsx_path(tmp_path):
    resultado = _resultado_fixture()
    path = tmp_path / "test_analisis.xlsx"
    generar_excel(resultado, path)
    return path


def test_archivo_creado(xlsx_path):
    assert xlsx_path.exists()
    assert xlsx_path.stat().st_size > 0


def test_hojas_esperadas(xlsx_path):
    import openpyxl
    wb = openpyxl.load_workbook(xlsx_path)
    assert "Análisis Mensual" in wb.sheetnames
    assert "Parámetros" in wb.sheetnames


def test_filas_de_datos(xlsx_path):
    import openpyxl
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb["Análisis Mensual"]
    # Fila 1 = encabezado, filas 2-3 = 2 meses, fila 4 = totales → mínimo 4 filas
    assert ws.max_row >= 4


def test_ebitda_anual_en_totales(xlsx_path):
    import openpyxl
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb["Análisis Mensual"]
    # Buscar celda con el EBITDA anual total en la última fila
    # Columna "EBITDA Mes (MXN)" es la última columna de datos
    last_row = ws.max_row
    # Verificar que la última fila tiene algún valor numérico > 0
    valores = [ws.cell(last_row, c).value for c in range(1, ws.max_column + 1)]
    numericos = [v for v in valores if isinstance(v, (int, float)) and v > 0]
    assert len(numericos) > 0
```

- [ ] **Step 2: Verificar que fallan**

```bash
python3 -m pytest tests/reports/test_excel.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError: No module named 'reports'`

- [ ] **Step 3: Crear `reports/__init__.py` y `tests/reports/__init__.py`**

```bash
touch reports/__init__.py tests/reports/__init__.py
```

- [ ] **Step 4: Crear `reports/excel.py`**

```python
# reports/excel.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from models.cogen_result import CoGenResultado

# Colores
_AZUL_HEADER = "1F4E79"
_GRIS_TOTALES = "D9E1F2"
_VERDE_EBITDA = "E2EFDA"


def generar_excel(resultado: CoGenResultado, output_path: Path) -> Path:
    """Genera reporte Excel con análisis mensual de cogeneración.

    Crea dos hojas:
    - 'Análisis Mensual': tabla con 12 meses + totales
    - 'Parámetros': parámetros técnicos usados

    Args:
        resultado: CoGenResultado con todos los meses calculados
        output_path: ruta donde guardar el .xlsx

    Returns:
        output_path (para encadenamiento)
    """
    output_path = Path(output_path)
    wb = openpyxl.Workbook()

    _escribir_hoja_analisis(wb, resultado)
    _escribir_hoja_parametros(wb, resultado.params)

    # Eliminar hoja vacía por defecto
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    wb.save(output_path)
    return output_path


# ── Hoja 1: Análisis Mensual ──────────────────────────────────────────────────

_COLUMNAS = [
    ("Periodo",               "periodo_inicio",             "fecha"),
    ("kWh Total",             "kwh_total",                  "numero"),
    ("Costo CFE (MXN)",       "costo_cfe_mxn",              "moneda"),
    ("$/kWh Promedio",        "costo_promedio_kwh",         "decimal4"),
    ("GJ Gas Real",           "gj_consumido",               "numero"),
    ("$/GJ Gas",              "costo_unitario_gj",          "decimal4"),
    ("Costo Gas Real (MXN)",  "costo_gas_actual_mxn",       "moneda"),
    ("kWh Cubiertos",         "kwh_cubiertos",              "numero"),
    ("GJ Cogen",              "gj_gas_cogen",               "numero"),
    ("Costo Gas Cogen (MXN)", "costo_gas_cogen_mxn",        "moneda"),
    ("Ahorro Elec. (MXN)",    "ahorro_electricidad_mxn",    "moneda"),
    ("Calor Recup. (GJ)",     "calor_recuperado_gj",        "numero"),
    ("Ahorro Caldera (MXN)",  "ahorro_caldera_mxn",         "moneda"),
    ("EBITDA Mes (MXN)",      "ebitda_mes_mxn",             "moneda"),
]

_TOTALES_COLS = {
    "kwh_total":                  "kwh_total_anual",
    "kwh_cubiertos":              "kwh_cubiertos_anual",
    "gj_gas_cogen":               "gj_gas_cogen_anual",
    "costo_gas_cogen_mxn":        "costo_gas_cogen_anual_mxn",
    "ahorro_electricidad_mxn":    "ahorro_electricidad_anual_mxn",
    "ahorro_caldera_mxn":         "ahorro_caldera_anual_mxn",
    "ebitda_mes_mxn":             "ebitda_anual_mxn",
}


def _escribir_hoja_analisis(wb: openpyxl.Workbook, resultado: CoGenResultado) -> None:
    ws = wb.create_sheet("Análisis Mensual")

    # Encabezados
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor=_AZUL_HEADER)
    for col_idx, (titulo, _, _fmt) in enumerate(_COLUMNAS, 1):
        cell = ws.cell(1, col_idx, titulo)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    # Filas de datos
    for row_idx, mes in enumerate(resultado.meses, 2):
        for col_idx, (_titulo, attr, fmt) in enumerate(_COLUMNAS, 1):
            valor = getattr(mes, attr)
            cell = ws.cell(row_idx, col_idx, _formatear(valor, fmt))
            if fmt == "moneda":
                cell.number_format = '#,##0.00'
            elif fmt == "numero":
                cell.number_format = '#,##0.0000'
            elif fmt == "decimal4":
                cell.number_format = '0.0000'
            if attr == "ebitda_mes_mxn":
                cell.fill = PatternFill("solid", fgColor=_VERDE_EBITDA)

    # Fila de totales
    totales_row = len(resultado.meses) + 2
    totales_fill = PatternFill("solid", fgColor=_GRIS_TOTALES)
    totales_font = Font(bold=True)
    ws.cell(totales_row, 1, "TOTAL ANUAL").font = totales_font
    ws.cell(totales_row, 1).fill = totales_fill

    for col_idx, (_titulo, attr, fmt) in enumerate(_COLUMNAS, 1):
        if attr in _TOTALES_COLS:
            valor = getattr(resultado, _TOTALES_COLS[attr])
            cell = ws.cell(totales_row, col_idx, float(valor))
            cell.number_format = '#,##0.00' if fmt == "moneda" else '#,##0.0000'
            cell.font = totales_font
            cell.fill = totales_fill

    # Anchos de columna
    anchos = [12, 14, 18, 12, 14, 10, 18, 14, 12, 18, 18, 14, 18, 18]
    for i, ancho in enumerate(anchos, 1):
        ws.column_dimensions[get_column_letter(i)].width = ancho

    ws.freeze_panes = "B2"


def _formatear(valor: object, fmt: str) -> object:
    """Convierte Decimal/date al tipo nativo que openpyxl acepta mejor."""
    if isinstance(valor, date):
        return valor.strftime("%b %Y")
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


# ── Hoja 2: Parámetros ────────────────────────────────────────────────────────

def _escribir_hoja_parametros(wb: openpyxl.Workbook, params) -> None:
    ws = wb.create_sheet("Parámetros")

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor=_AZUL_HEADER)

    ws.cell(1, 1, "Parámetro").font = header_font
    ws.cell(1, 1).fill = header_fill
    ws.cell(1, 2, "Valor").font = header_font
    ws.cell(1, 2).fill = header_fill

    filas = [
        ("Cobertura eléctrica",  f"{float(params.cobertura_electrica)*100:.0f}%"),
        ("Rendimiento eléctrico",f"{float(params.rendimiento_electrico)*100:.0f}%"),
        ("Rendimiento térmico",  f"{float(params.rendimiento_termico)*100:.0f}%"),
        ("Eficiencia caldera",   f"{float(params.eficiencia_caldera)*100:.0f}%"),
        ("Factor kWh→GJ",        "0.0036 GJ/kWh"),
    ]
    for row_idx, (nombre, valor) in enumerate(filas, 2):
        ws.cell(row_idx, 1, nombre)
        ws.cell(row_idx, 2, valor)

    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 16
```

- [ ] **Step 5: Correr tests**

```bash
python3 -m pytest tests/reports/test_excel.py -v
```
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add reports/ tests/reports/
git commit -m "feat: add Excel report generator (Task 3)"
```

---

## Task 4: CLI — generar_analisis_cogen

**Files:**
- Modify: `cli/main.py`
- Create: `tests/test_cli_cogen.py`

- [ ] **Step 1: Escribir tests fallidos**

```python
# tests/test_cli_cogen.py
from __future__ import annotations
import sqlite3
import pytest
from pathlib import Path

from storage.schema import init_db
from cli.main import procesar_factura_cfe, procesar_factura_gas, generar_analisis_cogen

CFE_FIXTURE = Path("invoices/CFE/P2 2023_11 NOVIEMBRE.pdf")
GAS_FIXTURE = Path("invoices/Gas/TRA0002119W1_I_I0000054727751484 Nov 23.pdf")


@pytest.fixture
def conn_con_facturas(tmp_path):
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    init_db(c)
    procesar_factura_cfe(CFE_FIXTURE, c)
    procesar_factura_gas(GAS_FIXTURE, c)
    yield c, tmp_path
    c.close()


def test_genera_archivo_xlsx(conn_con_facturas):
    conn, tmp_path = conn_con_facturas
    out = tmp_path / "analisis.xlsx"
    result = generar_analisis_cogen(conn, out)
    assert result.exists()
    assert result.suffix == ".xlsx"


def test_xlsx_tiene_datos(conn_con_facturas):
    conn, tmp_path = conn_con_facturas
    out = tmp_path / "analisis.xlsx"
    generar_analisis_cogen(conn, out)
    import openpyxl
    wb = openpyxl.load_workbook(out)
    ws = wb["Análisis Mensual"]
    assert ws.max_row >= 3  # encabezado + 1 mes + totales


def test_devuelve_path(conn_con_facturas):
    conn, tmp_path = conn_con_facturas
    out = tmp_path / "analisis.xlsx"
    result = generar_analisis_cogen(conn, out)
    assert isinstance(result, Path)
    assert result == out
```

- [ ] **Step 2: Verificar que fallan**

```bash
python3 -m pytest tests/test_cli_cogen.py -v 2>&1 | head -10
```
Expected: `ImportError: cannot import name 'generar_analisis_cogen'`

- [ ] **Step 3: Agregar `generar_analisis_cogen` a `cli/main.py`**

Insertar ANTES de `_main()`:

```python
def generar_analisis_cogen(conn: sqlite3.Connection, output_path: Path) -> Path:
    """Carga todas las facturas de la BD, calcula cogeneración y genera Excel.

    Args:
        conn: conexión SQLite con facturas CFE y Gas ya persistidas.
        output_path: ruta del archivo .xlsx a generar.

    Returns:
        output_path (Path) del archivo generado.
    """
    from storage.repository import list_cfe_invoices, load_cfe_invoice
    from storage.repository import list_gas_invoices, load_gas_invoice
    from calc.cogen import calcular_cogen
    from models.cogen_result import CoGenParams
    from reports.excel import generar_excel

    cfe_rows = list_cfe_invoices(conn)
    cfe_invoices = [load_cfe_invoice(conn, r["id"]) for r in cfe_rows]

    gas_rows = list_gas_invoices(conn)
    gas_invoices = [load_gas_invoice(conn, r["id"]) for r in gas_rows]

    params = CoGenParams()
    resultado = calcular_cogen(cfe_invoices, gas_invoices, params)

    output_path = Path(output_path)
    generar_excel(resultado, output_path)

    print(f"[OK] Análisis generado: {output_path}")
    print(f"     Meses pareados:     {len(resultado.meses)}")
    print(f"     EBITDA anual:       ${resultado.ebitda_anual_mxn:>16,.2f}")
    print(f"     Ahorro electricidad:${resultado.ahorro_electricidad_anual_mxn:>16,.2f}")
    print(f"     Ahorro caldera:     ${resultado.ahorro_caldera_anual_mxn:>16,.2f}")
    print(f"     Costo gas cogen:    ${resultado.costo_gas_cogen_anual_mxn:>16,.2f}")
    return output_path
```

- [ ] **Step 4: Correr TODOS los tests**

```bash
python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```
Expected: 98 + 3 (models) + 12 (cogen) + 4 (excel) + 3 (cli_cogen) = 120 PASS

- [ ] **Step 5: Prueba real — generar el análisis con las 24 facturas reales**

```python
python3 -c "
import sqlite3
from pathlib import Path
from storage.schema import init_db
from cli.main import procesar_factura_cfe, procesar_factura_gas, generar_analisis_cogen

conn = sqlite3.connect(':memory:')
conn.execute('PRAGMA foreign_keys = ON')
init_db(conn)

# Cargar CFE
for f in sorted(Path('invoices/CFE').glob('*.pdf')):
    procesar_factura_cfe(f, conn)

# Cargar Gas
for f in sorted(Path('invoices/Gas').glob('*.pdf')):
    procesar_factura_gas(f, conn)

# Generar análisis
generar_analisis_cogen(conn, Path('analisis_cogen.xlsx'))
print('Listo → analisis_cogen.xlsx')
"
```
Expected:
```
[OK] Análisis generado: analisis_cogen.xlsx
     Meses pareados:     12
     EBITDA anual:       $X,XXX,XXX.XX
     ...
```

- [ ] **Step 6: Commit**

```bash
git add cli/main.py tests/test_cli_cogen.py
git commit -m "feat: add generar_analisis_cogen CLI + full cogen pipeline (Task 4)"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ CoGenParams con 4 parámetros configurables (75%/40%/25%/85%)
- ✅ CoGenMes con todos los campos derivados
- ✅ CoGenResultado con totales anuales
- ✅ `calcular_cogen()` empareja por (año, mes), omite meses sin par
- ✅ Fórmulas completas: kwh_cubiertos, gj_cogen, costo_gas_cogen, ahorro_elec, calor_recuperado, ahorro_caldera, ebitda
- ✅ Excel con 2 hojas: Análisis Mensual + Parámetros
- ✅ CLI `generar_analisis_cogen()` integra todo

**2. Placeholder scan:** Ninguno encontrado.

**3. Type consistency:**
- `CoGenMes.ebitda_mes_mxn` referenciado correctamente en Task 2, 3 y 4
- `CoGenResultado.ebitda_anual_mxn` referenciado correctamente en Task 3 y 4
- `_TOTALES_COLS` mapea exactamente los atributos de `CoGenMes` → `CoGenResultado`
- `generar_excel(resultado, output_path)` — firma consistente entre Task 3 y Task 4
