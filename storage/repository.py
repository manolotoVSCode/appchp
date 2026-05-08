# storage/repository.py
from __future__ import annotations

import json
import logging
import os
from datetime import date
from decimal import Decimal

from supabase import create_client, Client

from models.cfe_invoice import CFEInvoice, CFEConsumoHorario, MEMComponente
from models.gas_invoice import GasInvoice, GasConcepto
from calc.nombre_canonico import generar_nombre_canonico

logger = logging.getLogger(__name__)

_supabase: Client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_KEY"],
)


# ── Clientes ──────────────────────────────────────────────────────────────────

def _upsert_cliente(nombre: str, rfc: str) -> int:
    """Inserta o reutiliza el cliente por RFC. Devuelve su id."""
    result = _supabase.table("clientes").upsert(
        {"nombre": nombre, "rfc": rfc},
        on_conflict="rfc",
    ).execute()
    return result.data[0]["id"]


# ── CFE invoices ──────────────────────────────────────────────────────────────

def save_cfe_invoice(invoice: CFEInvoice) -> tuple[int, str]:
    """Persiste un CFEInvoice completo. Devuelve (id de cfe_facturas, nombre_canonico)."""
    cliente_id = _upsert_cliente(invoice.nombre_cliente, invoice.rfc_cliente)
    nombre_canonico = generar_nombre_canonico(invoice)

    row = {
        "cliente_id": cliente_id,
        "uuid_cfdi": invoice.uuid_cfdi,
        "folio": invoice.folio,
        "serie": invoice.serie,
        "fecha_emision": invoice.fecha_emision.isoformat(),
        "periodo_inicio": invoice.periodo_inicio.isoformat(),
        "periodo_fin": invoice.periodo_fin.isoformat(),
        "fecha_limite_pago": invoice.fecha_limite_pago.isoformat(),
        "numero_servicio": invoice.numero_servicio,
        "rmu": invoice.rmu,
        "tarifa": invoice.tarifa,
        "numero_medidor": invoice.numero_medidor,
        "multiplicador": invoice.multiplicador,
        "carga_conectada_kw": str(invoice.carga_conectada_kw),
        "demanda_contratada_kw": str(invoice.demanda_contratada_kw),
        "kw_max": str(invoice.kw_max),
        "kvarh": str(invoice.kvArh),
        "factor_potencia_pct": str(invoice.factor_potencia_pct),
        "cargo_fijo_mxn": str(invoice.cargo_fijo_mxn),
        "energia_total_mxn": str(invoice.energia_total_mxn),
        "cargo_factor_potencia_mxn": str(invoice.cargo_factor_potencia_mxn),
        "subtotal_mxn": str(invoice.subtotal_mxn),
        "iva_mxn": str(invoice.iva_mxn),
        "facturacion_periodo_mxn": str(invoice.facturacion_periodo_mxn),
        "derecho_alumbrado_publico_mxn": str(invoice.derecho_alumbrado_publico_mxn),
        "credito_aplicado_mxn": str(invoice.credito_aplicado_mxn),
        "total_mxn": str(invoice.total_mxn),
        "pdf_path": invoice.pdf_path,
        "nombre_canonico": nombre_canonico,
        "advertencias": json.dumps(invoice.advertencias, ensure_ascii=False),
    }
    try:
        result = _supabase.table("cfe_facturas").insert(row).execute()
    except Exception as exc:
        logger.error(
            "Error insertando cfe_factura: folio=%s, rfc=%s, periodo=%s→%s — %s",
            invoice.folio, invoice.rfc_cliente,
            invoice.periodo_inicio, invoice.periodo_fin, exc,
        )
        raise
    factura_id = result.data[0]["id"]

    periodos = [
        {
            "factura_id": factura_id,
            "periodo": p.periodo,
            "consumo_kwh": str(p.consumo_kwh),
            "demanda_kw": str(p.demanda_kw),
            "costo_unitario_kwh": str(p.costo_unitario_kwh),
        }
        for p in invoice.periodos
    ]
    if periodos:
        try:
            _supabase.table("cfe_periodos").insert(periodos).execute()
        except Exception as exc:
            logger.error(
                "Error insertando cfe_periodos para factura_id=%d: %s", factura_id, exc,
            )
            raise

    componentes = [
        {
            "factura_id": factura_id,
            "nombre": c.nombre,
            "cargo_fijo_mxn": str(c.cargo_fijo_mxn),
            "cargo_demanda_mxn": str(c.cargo_demanda_mxn),
            "cargo_energia_mxn": str(c.cargo_energia_mxn),
            "importe_mxn": str(c.importe_mxn),
        }
        for c in invoice.componentes_mem
    ]
    if componentes:
        try:
            _supabase.table("cfe_mem_componentes").insert(componentes).execute()
        except Exception as exc:
            logger.error(
                "Error insertando cfe_mem_componentes para factura_id=%d: %s", factura_id, exc,
            )
            raise

    return factura_id, nombre_canonico


def get_all_cfe_invoices() -> list[CFEInvoice]:
    """Carga todas las facturas CFE con sus relaciones. Ordenadas por periodo_inicio."""
    result = _supabase.table("cfe_facturas").select(
        "*, clientes(nombre, rfc), cfe_periodos(*), cfe_mem_componentes(*)"
    ).order("periodo_inicio").execute()

    return [_row_to_cfe_invoice(row) for row in result.data]


def _row_to_cfe_invoice(row: dict) -> CFEInvoice:
    periodos = [
        CFEConsumoHorario(
            periodo=p["periodo"],
            consumo_kwh=Decimal(p["consumo_kwh"]),
            demanda_kw=Decimal(p["demanda_kw"]),
            costo_unitario_kwh=Decimal(p["costo_unitario_kwh"]),
        )
        for p in sorted(row["cfe_periodos"], key=lambda x: x["id"])
    ]
    componentes_mem = [
        MEMComponente(
            nombre=c["nombre"],
            cargo_fijo_mxn=Decimal(c["cargo_fijo_mxn"]),
            cargo_demanda_mxn=Decimal(c["cargo_demanda_mxn"]),
            cargo_energia_mxn=Decimal(c["cargo_energia_mxn"]),
            importe_mxn=Decimal(c["importe_mxn"]),
        )
        for c in sorted(row["cfe_mem_componentes"], key=lambda x: x["id"])
    ]
    cliente = row["clientes"]
    return CFEInvoice(
        uuid_cfdi=row["uuid_cfdi"],
        folio=row["folio"],
        serie=row["serie"],
        fecha_emision=date.fromisoformat(row["fecha_emision"]),
        periodo_inicio=date.fromisoformat(row["periodo_inicio"]),
        periodo_fin=date.fromisoformat(row["periodo_fin"]),
        fecha_limite_pago=date.fromisoformat(row["fecha_limite_pago"]),
        nombre_cliente=cliente["nombre"],
        rfc_cliente=cliente["rfc"],
        numero_servicio=row["numero_servicio"],
        rmu=row["rmu"],
        tarifa=row["tarifa"],
        numero_medidor=row["numero_medidor"],
        multiplicador=row["multiplicador"],
        carga_conectada_kw=Decimal(row["carga_conectada_kw"]),
        demanda_contratada_kw=Decimal(row["demanda_contratada_kw"]),
        periodos=periodos,
        kw_max=Decimal(row["kw_max"]),
        kvArh=Decimal(row["kvarh"]),
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
        advertencias=json.loads(row["advertencias"]) if row.get("advertencias") else [],
    )


# ── Gas invoices ──────────────────────────────────────────────────────────────

def save_gas_invoice(invoice: GasInvoice) -> tuple[int, str]:
    """Persiste una GasInvoice completa. Devuelve (id de gas_facturas, nombre_canonico)."""
    cliente_id = _upsert_cliente(invoice.nombre_cliente, invoice.rfc_cliente)
    nombre_canonico = generar_nombre_canonico(invoice)

    row = {
        "cliente_id": cliente_id,
        "uuid_cfdi": invoice.uuid_cfdi,
        "folio": invoice.folio,
        "fecha_emision": invoice.fecha_emision.isoformat(),
        "periodo_inicio": invoice.periodo_inicio.isoformat(),
        "periodo_fin": invoice.periodo_fin.isoformat(),
        "fecha_limite_pago": invoice.fecha_limite_pago.isoformat(),
        "nombre_proveedor": invoice.nombre_proveedor,
        "rfc_proveedor": invoice.rfc_proveedor,
        "numero_cliente": invoice.numero_cliente,
        "cuenta_contrato": invoice.cuenta_contrato,
        "punto_suministro": invoice.punto_suministro,
        "numero_caseta": invoice.numero_caseta,
        "tipo_lectura": invoice.tipo_lectura,
        "consumo_m3_corregidos": str(invoice.consumo_m3_corregidos),
        "consumo_sin_corregir_m3": str(invoice.consumo_sin_corregir_m3),
        "poder_calorifico_gj_m3": str(invoice.poder_calorifico_gj_m3),
        "consumo_total_gj": str(invoice.consumo_total_gj),
        "costo_unitario_total_gj": str(invoice.costo_unitario_total_gj),
        "subtotal_mxn": str(invoice.subtotal_mxn),
        "iva_mxn": str(invoice.iva_mxn),
        "total_mxn": str(invoice.total_mxn),
        "pdf_path": invoice.pdf_path,
        "nombre_canonico": nombre_canonico,
        "advertencias": json.dumps(invoice.advertencias, ensure_ascii=False),
    }
    try:
        result = _supabase.table("gas_facturas").insert(row).execute()
    except Exception as exc:
        logger.error(
            "Error insertando gas_factura: folio=%s, rfc=%s, periodo=%s→%s — %s",
            invoice.folio, invoice.rfc_cliente,
            invoice.periodo_inicio, invoice.periodo_fin, exc,
        )
        raise
    factura_id = result.data[0]["id"]

    conceptos = [
        {
            "factura_id": factura_id,
            "descripcion": c.descripcion,
            "clave_producto": c.clave_producto,
            "cantidad_gj": str(c.cantidad_gj),
            "precio_unitario_gj": str(c.precio_unitario_gj),
            "importe_mxn": str(c.importe_mxn),
        }
        for c in invoice.conceptos
    ]
    if conceptos:
        try:
            _supabase.table("gas_conceptos").insert(conceptos).execute()
        except Exception as exc:
            logger.error(
                "Error insertando gas_conceptos para factura_id=%d: %s", factura_id, exc,
            )
            raise

    return factura_id, nombre_canonico


def get_all_gas_invoices() -> list[GasInvoice]:
    """Carga todas las facturas de gas con sus relaciones. Ordenadas por periodo_inicio."""
    result = _supabase.table("gas_facturas").select(
        "*, clientes(nombre, rfc), gas_conceptos(*)"
    ).order("periodo_inicio").execute()

    return [_row_to_gas_invoice(row) for row in result.data]


def _row_to_gas_invoice(row: dict) -> GasInvoice:
    conceptos = [
        GasConcepto(
            descripcion=c["descripcion"],
            clave_producto=c["clave_producto"],
            cantidad_gj=Decimal(c["cantidad_gj"]),
            precio_unitario_gj=Decimal(c["precio_unitario_gj"]),
            importe_mxn=Decimal(c["importe_mxn"]),
        )
        for c in sorted(row["gas_conceptos"], key=lambda x: x["id"])
    ]
    cliente = row["clientes"]
    return GasInvoice(
        uuid_cfdi=row["uuid_cfdi"] or "",
        folio=row["folio"],
        fecha_emision=date.fromisoformat(row["fecha_emision"]),
        periodo_inicio=date.fromisoformat(row["periodo_inicio"]),
        periodo_fin=date.fromisoformat(row["periodo_fin"]),
        fecha_limite_pago=date.fromisoformat(row["fecha_limite_pago"]),
        nombre_proveedor=row["nombre_proveedor"],
        rfc_proveedor=row["rfc_proveedor"],
        nombre_cliente=cliente["nombre"],
        rfc_cliente=cliente["rfc"],
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
        pdf_path=row.get("pdf_path", ""),
        advertencias=json.loads(row["advertencias"]) if row.get("advertencias") else [],
    )
