# calc/historico.py
from __future__ import annotations

from datetime import date

from models.cfe_invoice import CFEInvoice
from calc.periodo import mes_asociado


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
