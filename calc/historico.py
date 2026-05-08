# calc/historico.py
from __future__ import annotations

from datetime import date

from models.cfe_invoice import CFEInvoice
from calc.periodo import mes_asociado, prorratear_cfe

_MESES_CORTO = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
    7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic",
}


def calcular_historico_cfe(cfe_invoices: list[CFEInvoice]) -> dict:
    """Agrega datos históricos de consumo eléctrico para visualización.

    No depende de parámetros del motor de cogeneración ni de facturas de gas.
    Devuelve un dict serializable como JSON listo para pasar al template.

    Nota: costo_punta se calcula como consumo_kwh_punta × costo_unitario_kwh_punta,
    que representa el componente de energía en horario punta. No incluye cargos por
    demanda asignables a punta porque el modelo de datos no tiene esa desagregación.
    """
    facturas_ordenadas = sorted(
        cfe_invoices,
        key=lambda inv: mes_asociado(inv.periodo_inicio, inv.periodo_fin),
    )

    labels: list[str] = []
    demanda_punta: list[float] = []
    demanda_intermedio: list[float] = []
    demanda_base: list[float] = []
    consumo_punta: list[float] = []
    consumo_intermedio: list[float] = []
    consumo_base: list[float] = []
    costo_unit_mes: list[float] = []
    tabla_punta: list[dict] = []

    suma_costo_punta = 0.0
    suma_kwh_punta = 0.0
    suma_facturacion_total = 0.0
    suma_kwh_by_horario: dict[str, float] = {"base": 0.0, "intermedio": 0.0, "punta": 0.0}
    suma_costo_by_horario: dict[str, float] = {"base": 0.0, "intermedio": 0.0, "punta": 0.0}

    for inv in facturas_ordenadas:
        ma = mes_asociado(inv.periodo_inicio, inv.periodo_fin)
        label = date(ma[0], ma[1], 1).strftime("%b %Y")
        labels.append(label)

        p_dict = {p.periodo: p for p in inv.periodos}

        # Demanda máxima por horario (kW)
        demanda_punta.append(float(p_dict["punta"].demanda_kw) if "punta" in p_dict else 0.0)
        demanda_intermedio.append(float(p_dict["intermedio"].demanda_kw) if "intermedio" in p_dict else 0.0)
        demanda_base.append(float(p_dict["base"].demanda_kw) if "base" in p_dict else 0.0)

        # Consumo por horario (kWh)
        kwh_p = float(p_dict["punta"].consumo_kwh) if "punta" in p_dict else 0.0
        kwh_i = float(p_dict["intermedio"].consumo_kwh) if "intermedio" in p_dict else 0.0
        kwh_b = float(p_dict["base"].consumo_kwh) if "base" in p_dict else 0.0
        consumo_punta.append(kwh_p)
        consumo_intermedio.append(kwh_i)
        consumo_base.append(kwh_b)

        # Costo unitario total del mes = subtotal (pre-IVA) / kWh_total
        kwh_total = kwh_p + kwh_i + kwh_b
        facturacion = float(inv.subtotal_mxn)
        costo_unit_mes.append(round(facturacion / kwh_total, 4) if kwh_total > 0 else 0.0)

        # Tabla punta: costo energético punta, % sobre total facturado, costo unitario punta
        if "punta" in p_dict:
            pp = p_dict["punta"]
            cp = float(pp.consumo_kwh * pp.costo_unitario_kwh)
            pct = round(cp / facturacion * 100, 1) if facturacion > 0 else 0.0
            cu_punta = round(float(pp.costo_unitario_kwh), 4)
        else:
            cp = 0.0
            pct = 0.0
            cu_punta = 0.0

        tabla_punta.append({
            "mes": label,
            "costo_punta": round(cp, 2),
            "pct": pct,
            "costo_unit_punta": cu_punta,
        })

        # Acumuladores para fila de totales y promedios ponderados
        suma_costo_punta += cp
        suma_kwh_punta += kwh_p
        suma_facturacion_total += facturacion
        for nombre, kwh in [("punta", kwh_p), ("intermedio", kwh_i), ("base", kwh_b)]:
            suma_kwh_by_horario[nombre] += kwh
            if nombre in p_dict:
                suma_costo_by_horario[nombre] += float(
                    p_dict[nombre].consumo_kwh * p_dict[nombre].costo_unitario_kwh
                )

    # Fila de totales / promedios ponderados para la tabla punta
    pct_total = round(suma_costo_punta / suma_facturacion_total * 100, 1) if suma_facturacion_total > 0 else 0.0
    cu_punta_total = round(suma_costo_punta / suma_kwh_punta, 4) if suma_kwh_punta > 0 else 0.0
    tabla_punta.append({
        "mes": "TOTAL ANUAL",
        "costo_punta": round(suma_costo_punta, 2),
        "pct": pct_total,
        "costo_unit_punta": cu_punta_total,
    })

    # Costo unitario promedio ponderado por consumo para cada horario
    costo_unit_promedio = {
        nombre: round(suma_costo_by_horario[nombre] / suma_kwh_by_horario[nombre], 4)
        if suma_kwh_by_horario[nombre] > 0 else 0.0
        for nombre in ["base", "intermedio", "punta"]
    }

    return {
        "labels": labels,
        "demanda_punta": demanda_punta,
        "demanda_intermedio": demanda_intermedio,
        "demanda_base": demanda_base,
        "consumo_punta": consumo_punta,
        "consumo_intermedio": consumo_intermedio,
        "consumo_base": consumo_base,
        "costo_unit_mes": costo_unit_mes,
        "tabla_punta": tabla_punta,
        "costo_unit_promedio": costo_unit_promedio,
    }


def calcular_tablas_cfe(cfe_invoices: list[CFEInvoice]) -> dict:
    """Calcula las tres tablas de análisis histórico CFE para el dashboard.

    Aplica prorrateo a facturas con periodo corto (< umbral días).
    Periodos faltantes en una factura devuelven 0.0 (no excepción).
    Devuelve dict con claves: consumos_demandas, costos_detallados, indicadores.
    Cada lista termina con una fila de totales ANUAL.
    """
    facturas_ordenadas = sorted(
        cfe_invoices,
        key=lambda inv: mes_asociado(inv.periodo_inicio, inv.periodo_fin),
    )

    consumos_demandas: list[dict] = []
    costos_detallados: list[dict] = []
    indicadores: list[dict] = []

    # Acumuladores para fila ANUAL
    sum_kwh_base = sum_kwh_inter = sum_kwh_punta = sum_kwh_total = 0.0
    sum_ce_base = sum_ce_inter = sum_ce_punta = sum_ce_total = 0.0
    sum_dist = sum_cap = sum_dem = 0.0
    sum_fp = sum_sub = 0.0
    sum_horas = 0.0
    max_demanda = 0.0

    for inv_orig in facturas_ordenadas:
        inv, factor = prorratear_cfe(inv_orig)
        prorrateado = factor is not None

        ma = mes_asociado(inv.periodo_inicio, inv.periodo_fin)
        mes_label = f"{_MESES_CORTO[ma[1]]}-{str(ma[0])[2:]}"

        # Horas reales del periodo (usar 720 si prorrateado porque datos ya escalados)
        if prorrateado:
            horas = 720.0
        else:
            horas = float((inv_orig.periodo_fin - inv_orig.periodo_inicio).days * 24)

        p = {p_.periodo: p_ for p_ in inv.periodos}

        kwh_base  = float(p["base"].consumo_kwh)        if "base"        in p else 0.0
        kwh_inter = float(p["intermedio"].consumo_kwh)  if "intermedio"  in p else 0.0
        kwh_punta = float(p["punta"].consumo_kwh)       if "punta"       in p else 0.0
        kwh_total = kwh_base + kwh_inter + kwh_punta

        kw_base   = float(p["base"].demanda_kw)         if "base"        in p else 0.0
        kw_inter  = float(p["intermedio"].demanda_kw)   if "intermedio"  in p else 0.0
        kw_punta  = float(p["punta"].demanda_kw)        if "punta"       in p else 0.0

        ce_base  = kwh_base  * (float(p["base"].costo_unitario_kwh)       if "base"       in p else 0.0)
        ce_inter = kwh_inter * (float(p["intermedio"].costo_unitario_kwh) if "intermedio" in p else 0.0)
        ce_punta = kwh_punta * (float(p["punta"].costo_unitario_kwh)      if "punta"      in p else 0.0)
        ce_total = ce_base + ce_inter + ce_punta

        comp = {c.nombre: c for c in inv.componentes_mem}
        costo_dist = float(comp["Distribución"].cargo_demanda_mxn) if "Distribución" in comp else 0.0
        costo_cap  = float(comp["Capacidad"].cargo_demanda_mxn)    if "Capacidad"    in comp else 0.0
        costo_dem  = costo_dist + costo_cap

        cargo_fp = float(inv.cargo_factor_potencia_mxn)
        subtotal  = float(inv.subtotal_mxn)

        demanda_max  = max(kw_base, kw_inter, kw_punta)
        demanda_prom = round(kwh_total / horas, 1) if horas > 0 else 0.0
        costo_unit   = round(subtotal / kwh_total, 2) if kwh_total > 0 else 0.0
        pct_energia  = round(ce_total / subtotal * 100) if subtotal > 0 else 0
        pct_demanda  = round(costo_dem / subtotal * 100) if subtotal > 0 else 0
        factor_carga = round(demanda_prom / demanda_max * 100) if demanda_max > 0 else 0

        # Acumular
        sum_kwh_base  += kwh_base;  sum_kwh_inter += kwh_inter
        sum_kwh_punta += kwh_punta; sum_kwh_total += kwh_total
        sum_ce_base   += ce_base;   sum_ce_inter  += ce_inter
        sum_ce_punta  += ce_punta;  sum_ce_total  += ce_total
        sum_dist      += costo_dist; sum_cap       += costo_cap
        sum_dem       += costo_dem;  sum_fp        += cargo_fp
        sum_sub       += subtotal;   sum_horas     += horas
        max_demanda    = max(max_demanda, demanda_max)

        consumos_demandas.append({
            "mes": mes_label, "prorrateado": prorrateado,
            "kwh_base": kwh_base, "kwh_inter": kwh_inter,
            "kwh_punta": kwh_punta, "kwh_total": kwh_total,
            "kw_base": kw_base, "kw_inter": kw_inter, "kw_punta": kw_punta,
        })
        costos_detallados.append({
            "mes": mes_label, "prorrateado": prorrateado,
            "ce_base": ce_base, "ce_inter": ce_inter,
            "ce_punta": ce_punta, "ce_total": ce_total,
            "costo_dist": costo_dist, "costo_cap": costo_cap, "costo_dem": costo_dem,
            "cargo_fp": cargo_fp, "subtotal": subtotal,
        })
        indicadores.append({
            "mes": mes_label, "prorrateado": prorrateado,
            "costo_unit": costo_unit, "pct_energia": pct_energia,
            "pct_demanda": pct_demanda, "factor_carga": factor_carga,
            "demanda_prom": demanda_prom,
        })

    # Fila ANUAL
    anual_prom   = round(sum_kwh_total / sum_horas, 1)       if sum_horas > 0    else 0.0
    anual_unit   = round(sum_sub / sum_kwh_total, 2)         if sum_kwh_total > 0 else 0.0
    anual_pct_e  = round(sum_ce_total / sum_sub * 100)       if sum_sub > 0      else 0
    anual_pct_d  = round(sum_dem / sum_sub * 100)            if sum_sub > 0      else 0
    anual_fc     = round(anual_prom / max_demanda * 100)     if max_demanda > 0  else 0

    consumos_demandas.append({
        "mes": "ANUAL", "prorrateado": False,
        "kwh_base": sum_kwh_base, "kwh_inter": sum_kwh_inter,
        "kwh_punta": sum_kwh_punta, "kwh_total": sum_kwh_total,
        "kw_base": None, "kw_inter": None, "kw_punta": None,
    })
    costos_detallados.append({
        "mes": "ANUAL", "prorrateado": False,
        "ce_base": sum_ce_base, "ce_inter": sum_ce_inter,
        "ce_punta": sum_ce_punta, "ce_total": sum_ce_total,
        "costo_dist": sum_dist, "costo_cap": sum_cap, "costo_dem": sum_dem,
        "cargo_fp": sum_fp, "subtotal": sum_sub,
    })
    indicadores.append({
        "mes": "ANUAL", "prorrateado": False,
        "costo_unit": anual_unit, "pct_energia": anual_pct_e,
        "pct_demanda": anual_pct_d, "factor_carga": anual_fc,
        "demanda_prom": anual_prom,
    })

    return {
        "consumos_demandas": consumos_demandas,
        "costos_detallados": costos_detallados,
        "indicadores": indicadores,
    }
