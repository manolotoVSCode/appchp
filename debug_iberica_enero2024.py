"""
Debug: valores intermedios cogeneración — IBERICA enero 2024
Ejecutar desde la raíz del proyecto:
  python debug_iberica_enero2024.py

Nota: las facturas de enero 2024 deben estar seleccionadas en el sidebar
del dashboard para que get_facturas_para_dashboard las devuelva.
"""
import os
import sys
from decimal import Decimal
from pathlib import Path

# ── Cargar .env si existe ─────────────────────────────────────────────────────
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

# ── Forzar HTTP/1.1 (LibreSSL en Python 3.9 no soporta HTTP/2) ───────────────
import httpx
_orig_init = httpx.Client.__init__
def _patched_init(self, *args, **kwargs):
    kwargs["http2"] = False
    _orig_init(self, *args, **kwargs)
httpx.Client.__init__ = _patched_init

# ── Importar stack del proyecto ───────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from storage.repository import get_all_clientes_con_conteos, get_facturas_para_dashboard
from calc.cogen import calcular_cogen
from models.cogen_result import CoGenParams

# ── Buscar cliente IBERICA ────────────────────────────────────────────────────
clientes = get_all_clientes_con_conteos()
cliente = next((c for c in clientes if "IBERICA" in c["nombre"].upper()), None)
if cliente is None:
    print("ERROR: No se encontró cliente con 'IBERICA' en el nombre.")
    print("Clientes disponibles:", [c["nombre"] for c in clientes])
    sys.exit(1)

cliente_id = cliente["id"]
print(f"Cliente: {cliente['nombre']}  (id={cliente_id})\n")

# ── Cargar facturas seleccionadas ─────────────────────────────────────────────
cfe_all, gas_all = get_facturas_para_dashboard(cliente_id)

cfe_ene = [f for f in cfe_all if f.anio == 2024 and f.mes == 1]
gas_ene = [f for f in gas_all if f.anio == 2024 and f.mes == 1]

print(f"Facturas CFE  para ene-2024: {len(cfe_ene)}")
print(f"Facturas gas  para ene-2024: {len(gas_ene)}")

if not cfe_ene or not gas_ene:
    print("\nFaltó una o ambas facturas. Facturas seleccionadas disponibles:")
    print("  CFE:", sorted({(f.anio, f.mes) for f in cfe_all}))
    print("  Gas:", sorted({(f.anio, f.mes) for f in gas_all}))
    print("\n→ Asegúrate de tener enero 2024 seleccionado en el sidebar.")
    sys.exit(1)

# ── Parámetros por defecto ────────────────────────────────────────────────────
params = CoGenParams(
    cobertura_electrica=Decimal("0.75"),
    rendimiento_electrico=Decimal("0.40"),
    rendimiento_termico=Decimal("0.25"),
    eficiencia_caldera=Decimal("0.85"),
)

# ── Calcular ──────────────────────────────────────────────────────────────────
resultado = calcular_cogen(cfe_ene, gas_ene, params)

if not resultado.meses:
    print("\nERROR: calcular_cogen no produjo resultados.")
    sys.exit(1)

m = resultado.meses[0]
gj_caldera_ahorrado = m.calor_recuperado_gj / params.eficiencia_caldera

# ── Imprimir valores intermedios ──────────────────────────────────────────────
print("\n" + "─" * 57)
print(f"  COGENERACIÓN — {m.periodo_inicio.strftime('%B %Y').upper()}")
print("─" * 57)
print(f"  1. kWh cubiertos            {float(m.kwh_cubiertos):>14,.2f}  kWh")
print(f"  2. GJ gas cogen (PCS)       {float(m.gj_gas_cogen):>14,.4f}  GJ")
print(f"  3. GJ calor recuperado      {float(m.calor_recuperado_gj):>14,.4f}  GJ")
print(f"  4. GJ caldera ahorrado      {float(gj_caldera_ahorrado):>14,.4f}  GJ")
print(f"  5. Precio gas $/GJ          {float(m.costo_unitario_gj):>14,.4f}  MXN/GJ")
print(f"  6. Ahorro caldera           {float(m.ahorro_caldera_mxn):>14,.2f}  MXN")
print("─" * 57)
print(f"\n     cobertura={float(params.cobertura_electrica)*100:.0f}%  "
      f"η_elec={float(params.rendimiento_electrico)*100:.0f}%  "
      f"η_term={float(params.rendimiento_termico)*100:.0f}%  "
      f"η_caldera={float(params.eficiencia_caldera)*100:.0f}%")
