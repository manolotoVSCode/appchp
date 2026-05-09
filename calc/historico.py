# calc/historico.py
from __future__ import annotations

from datetime import date

from models.cfe_invoice import CFEInvoice
from models.gas_invoice import GasInvoice
from calc.periodo import mes_asociado, prorratear_cfe, UMBRAL_PRORRATEO_DIAS

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
    Devuelve dict con claves: consumos_demandas, costos_detallados, indicadores,
    costo_unit_promedio_total.
    Cada lista termina con una fila de totales ANUAL.
    """
    facturas_ordenadas = sorted(
        cfe_invoices,
        key=lambda inv: mes_asociado(inv.periodo_inicio, inv.periodo_fin),
    )

    consumos_demandas: list[dict] = []
    costos_detallados: list[dict] = []
    indicadores: list[dict] = []

    # Acumuladores para fila ANUAL — existentes
    sum_kwh_base = sum_kwh_inter = sum_kwh_punta = sum_kwh_total = 0.0
    sum_ce_base = sum_ce_inter = sum_ce_punta = sum_ce_total = 0.0
    sum_dist = sum_cap = sum_dem = 0.0
    sum_fp = sum_sub = 0.0
    sum_horas = 0.0
    max_demanda = 0.0
    # Acumuladores para costos totales por horario (solo meses con desglose disponible)
    sum_ct_base  = 0.0; sum_kwh_base_ct  = 0.0
    sum_ct_inter = 0.0; sum_kwh_inter_ct = 0.0
    sum_ct_punta = 0.0; sum_kwh_punta_ct = 0.0

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
        dist_disp = "Distribución" in comp
        cap_disp  = "Capacidad"    in comp
        costo_dist = float(comp["Distribución"].cargo_demanda_mxn) if dist_disp else 0.0
        costo_cap  = float(comp["Capacidad"].cargo_demanda_mxn)    if cap_disp  else 0.0
        costo_dem  = costo_dist + costo_cap

        cargo_fp = float(inv.cargo_factor_potencia_mxn)
        subtotal  = float(inv.subtotal_mxn)

        demanda_max  = max(kw_base, kw_inter, kw_punta)
        demanda_prom = round(kwh_total / horas, 1) if horas > 0 else 0.0
        costo_unit   = round(subtotal / kwh_total, 2) if kwh_total > 0 else 0.0
        pct_energia  = round(ce_total / subtotal * 100) if subtotal > 0 else 0
        pct_demanda  = round(costo_dem / subtotal * 100) if subtotal > 0 else 0
        factor_carga = round(demanda_prom / demanda_max * 100) if demanda_max > 0 else 0

        # Reparto de Distribución (proporcional entre Base e Intermedia) y Capacidad (100% Punta)
        kwh_bi = kwh_base + kwh_inter
        if dist_disp and kwh_bi > 0:
            ct_base  = ce_base  + costo_dist * kwh_base  / kwh_bi
            ct_inter = ce_inter + costo_dist * kwh_inter / kwh_bi
            cu_base_total  = round(ct_base  / kwh_base,  6) if kwh_base  > 0 else None
            cu_inter_total = round(ct_inter / kwh_inter, 6) if kwh_inter > 0 else None
        else:
            ct_base  = None
            ct_inter = None
            cu_base_total  = None
            cu_inter_total = None

        if cap_disp:
            ct_punta       = ce_punta + costo_cap
            cu_punta_total = round(ct_punta / kwh_punta, 6) if kwh_punta > 0 else None
        else:
            ct_punta       = None
            cu_punta_total = None

        # Acumular
        sum_kwh_base  += kwh_base;  sum_kwh_inter += kwh_inter
        sum_kwh_punta += kwh_punta; sum_kwh_total += kwh_total
        sum_ce_base   += ce_base;   sum_ce_inter  += ce_inter
        sum_ce_punta  += ce_punta;  sum_ce_total  += ce_total
        sum_dist      += costo_dist; sum_cap       += costo_cap
        sum_dem       += costo_dem;  sum_fp        += cargo_fp
        sum_sub       += subtotal;   sum_horas     += horas
        max_demanda    = max(max_demanda, demanda_max)
        if ct_base is not None:
            sum_ct_base  += ct_base;  sum_kwh_base_ct  += kwh_base
        if ct_inter is not None:
            sum_ct_inter += ct_inter; sum_kwh_inter_ct += kwh_inter
        if ct_punta is not None:
            sum_ct_punta += ct_punta; sum_kwh_punta_ct += kwh_punta

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
            "ct_base":  round(ct_base,  2) if ct_base  is not None else None,
            "ct_inter": round(ct_inter, 2) if ct_inter is not None else None,
            "ct_punta": round(ct_punta, 2) if ct_punta is not None else None,
            "cu_base_total":  cu_base_total,
            "cu_inter_total": cu_inter_total,
            "cu_punta_total": cu_punta_total,
        })

    # Fila ANUAL
    anual_prom   = round(sum_kwh_total / sum_horas, 1)       if sum_horas > 0    else 0.0
    anual_unit   = round(sum_sub / sum_kwh_total, 2)         if sum_kwh_total > 0 else 0.0
    anual_pct_e  = round(sum_ce_total / sum_sub * 100)       if sum_sub > 0      else 0
    anual_pct_d  = round(sum_dem / sum_sub * 100)            if sum_sub > 0      else 0
    anual_fc     = round(anual_prom / max_demanda * 100)     if max_demanda > 0  else 0

    anual_ct_base  = round(sum_ct_base,  2) if sum_kwh_base_ct  > 0 else None
    anual_ct_inter = round(sum_ct_inter, 2) if sum_kwh_inter_ct > 0 else None
    anual_ct_punta = round(sum_ct_punta, 2) if sum_kwh_punta_ct > 0 else None
    anual_cu_base  = round(sum_ct_base  / sum_kwh_base_ct,  6) if sum_kwh_base_ct  > 0 else None
    anual_cu_inter = round(sum_ct_inter / sum_kwh_inter_ct, 6) if sum_kwh_inter_ct > 0 else None
    anual_cu_punta = round(sum_ct_punta / sum_kwh_punta_ct, 6) if sum_kwh_punta_ct > 0 else None

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
        "ct_base": anual_ct_base, "ct_inter": anual_ct_inter, "ct_punta": anual_ct_punta,
        "cu_base_total": anual_cu_base, "cu_inter_total": anual_cu_inter,
        "cu_punta_total": anual_cu_punta,
    })

    costo_unit_promedio_total = {
        "base":       round(sum_ct_base  / sum_kwh_base_ct,  4) if sum_kwh_base_ct  > 0 else 0.0,
        "intermedio": round(sum_ct_inter / sum_kwh_inter_ct, 4) if sum_kwh_inter_ct > 0 else 0.0,
        "punta":      round(sum_ct_punta / sum_kwh_punta_ct, 4) if sum_kwh_punta_ct > 0 else 0.0,
    }

    return {
        "consumos_demandas": consumos_demandas,
        "costos_detallados": costos_detallados,
        "indicadores": indicadores,
        "costo_unit_promedio_total": costo_unit_promedio_total,
    }


_GJ_A_KWH = 277.778


def calcular_historico_gas(gas_invoices: list[GasInvoice]) -> dict | None:
    """Agrega datos históricos de gas natural para tabla y gráficas en el dashboard.

    Devuelve None si la lista está vacía (el template omite la sección de gas).
    Cada fila usa Decimal | None: None se renderiza como '—' en el template.
    Promedios de precio ($/GJ) son ponderados por consumo (GJ).
    """
    if not gas_invoices:
        return None

    facturas_ordenadas = sorted(
        gas_invoices,
        key=lambda inv: mes_asociado(inv.periodo_inicio, inv.periodo_fin),
    )

    filas: list[dict] = []

    sum_consumo = 0.0
    sum_costo_total = 0.0
    sum_mol_x_consumo = 0.0
    sum_tra_x_consumo = 0.0
    sum_costo_mol = 0.0
    sum_costo_tra = 0.0
    has_molecula = False
    has_transporte = False
    sum_pcs_x_consumo = 0.0
    sum_consumo_con_pcs = 0.0

    labels: list[str] = []
    consumos_gj: list[float] = []
    costos_unit_gj: list[float] = []
    costos_molecula_mxn: list[float] = []
    costos_transporte_mxn: list[float] = []

    for inv in facturas_ordenadas:
        ma = mes_asociado(inv.periodo_inicio, inv.periodo_fin)
        label = date(ma[0], ma[1], 1).strftime("%b %Y")
        labels.append(label)
        prorrateado = (inv.periodo_fin - inv.periodo_inicio).days < UMBRAL_PRORRATEO_DIAS

        consumo_gj = float(inv.consumo_total_gj) if float(inv.consumo_total_gj) > 0 else 0.0
        costo_unit_gj = float(inv.costo_unitario_total_gj)
        costo_total_mxn = float(inv.subtotal_mxn)
        costo_unit_kwh = round(costo_unit_gj / _GJ_A_KWH, 6) if costo_unit_gj > 0 else None

        # PCS: tratar 0 o negativo como sin dato
        try:
            pcs_val = float(inv.poder_calorifico_gj_m3)
            pcs_gj_m3 = pcs_val if pcs_val > 0 else None
        except (TypeError, ValueError):
            pcs_gj_m3 = None
        pcs_kwh_m3 = round(pcs_gj_m3 * _GJ_A_KWH, 5) if pcs_gj_m3 is not None else None

        # Conceptos por contenido de descripción (orden-independiente)
        molecula = next(
            (c for c in inv.conceptos if "Compraventa" in c.descripcion), None
        )
        transporte = next(
            (c for c in inv.conceptos if "Transporte" in c.descripcion), None
        )

        mol_precio_gj = float(molecula.precio_unitario_gj) if molecula else None
        tra_precio_gj = float(transporte.precio_unitario_gj) if transporte else None
        costo_mol_mxn = float(molecula.importe_mxn) if molecula else None
        costo_tra_mxn = float(transporte.importe_mxn) if transporte else None

        filas.append({
            "mes": label,
            "consumo_gj": consumo_gj,
            "molecula_precio_gj": mol_precio_gj,
            "transporte_precio_gj": tra_precio_gj,
            "costo_molecula_mxn": costo_mol_mxn,
            "costo_transporte_mxn": costo_tra_mxn,
            "costo_total_mxn": costo_total_mxn,
            "costo_unit_gj": costo_unit_gj,
            "costo_unit_kwh": costo_unit_kwh,
            "pcs_gj_m3": pcs_gj_m3,
            "pcs_kwh_m3": pcs_kwh_m3,
            "prorrateado": prorrateado,
        })

        # Acumuladores
        sum_consumo += consumo_gj
        sum_costo_total += costo_total_mxn
        if mol_precio_gj is not None:
            sum_mol_x_consumo += mol_precio_gj * consumo_gj
            sum_costo_mol += costo_mol_mxn
            has_molecula = True
        if tra_precio_gj is not None:
            sum_tra_x_consumo += tra_precio_gj * consumo_gj
            sum_costo_tra += costo_tra_mxn
            has_transporte = True
        if pcs_gj_m3 is not None:
            sum_pcs_x_consumo += pcs_gj_m3 * consumo_gj
            sum_consumo_con_pcs += consumo_gj

        consumos_gj.append(consumo_gj)
        costos_unit_gj.append(costo_unit_gj)
        costos_molecula_mxn.append(costo_mol_mxn or 0.0)
        costos_transporte_mxn.append(costo_tra_mxn or 0.0)

    # Fila TOTAL con promedios ponderados por consumo
    total_unit_gj = round(sum_costo_total / sum_consumo, 4) if sum_consumo > 0 else None
    total_unit_kwh = round(total_unit_gj / _GJ_A_KWH, 6) if total_unit_gj is not None else None
    total_mol_precio = round(sum_mol_x_consumo / sum_consumo, 4) if has_molecula and sum_consumo > 0 else None
    total_tra_precio = round(sum_tra_x_consumo / sum_consumo, 4) if has_transporte and sum_consumo > 0 else None
    total_pcs_gj = round(sum_pcs_x_consumo / sum_consumo_con_pcs, 5) if sum_consumo_con_pcs > 0 else None
    total_pcs_kwh = round(total_pcs_gj * _GJ_A_KWH, 5) if total_pcs_gj is not None else None

    total = {
        "consumo_gj": sum_consumo,
        "molecula_precio_gj": total_mol_precio,
        "transporte_precio_gj": total_tra_precio,
        "costo_molecula_mxn": sum_costo_mol if has_molecula else None,
        "costo_transporte_mxn": sum_costo_tra if has_transporte else None,
        "costo_total_mxn": sum_costo_total,
        "costo_unit_gj": total_unit_gj,
        "costo_unit_kwh": total_unit_kwh,
        "pcs_gj_m3": total_pcs_gj,
        "pcs_kwh_m3": total_pcs_kwh,
    }

    return {
        "filas": filas,
        "total": total,
        "labels": labels,
        "consumos_gj": consumos_gj,
        "costos_unit_gj": costos_unit_gj,
        "costos_molecula_mxn": costos_molecula_mxn,
        "costos_transporte_mxn": costos_transporte_mxn,
    }
