# calc/cfe_util.py
"""Cálculo de costos unitarios CFE GDMTH — función compartida parser/backend."""
from __future__ import annotations

from decimal import Decimal

_PREC = Decimal("0.000001")


def calcular_costos_unitarios_kwh(
    kwh_base: Decimal,
    kwh_inter: Decimal,
    kwh_punta: Decimal,
    gen_b_mxn: Decimal,
    gen_i_mxn: Decimal,
    gen_p_mxn: Decimal,
    transmision_mxn: Decimal,
    cenace_mxn: Decimal,
    scnmem_mxn: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    """Devuelve (costo_base, costo_inter, costo_punta) en MXN/kWh.

    Fórmula (misma que el parser gdmth.py):
        shared = (transmision + cenace + scnmem) / kwh_total
        costo_h = gen_h / kwh_h + shared   (0 si kwh_h == 0)
    """
    kwh_total = kwh_base + kwh_inter + kwh_punta
    if kwh_total == 0:
        return Decimal("0"), Decimal("0"), Decimal("0")

    shared = (transmision_mxn + cenace_mxn + scnmem_mxn) / kwh_total
    costo_base  = (gen_b_mxn / kwh_base  + shared).quantize(_PREC) if kwh_base  > 0 else Decimal("0")
    costo_inter = (gen_i_mxn / kwh_inter + shared).quantize(_PREC) if kwh_inter > 0 else Decimal("0")
    costo_punta = (gen_p_mxn / kwh_punta + shared).quantize(_PREC) if kwh_punta > 0 else Decimal("0")
    return costo_base, costo_inter, costo_punta
