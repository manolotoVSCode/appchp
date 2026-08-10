# storage/repository.py
from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

import httpx
from supabase import create_client, Client, ClientOptions

from models.cfe_invoice import CFEInvoice, CFEConsumoHorario, MEMComponente
from models.gas_invoice import GasInvoice, GasConcepto
from models.contrato import Contrato, TIPO_ELECTRICO_CALIFICADO
from models.factura_calificado import FacturaCalificado
from calc.nombre_canonico import generar_nombre_canonico
from calc.periodo import mes_asociado as _mes_asociado
from calc.modelado_chp import MODELADO_CHP_VERSION as _MODELADO_CHP_VERSION

logger = logging.getLogger(__name__)

_supabase: Client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_KEY"],
    options=ClientOptions(postgrest_client_timeout=30),
)

# ── Retry ante saturación de conexiones HTTP/2 a Supabase ────────────────────

_RETRIES = 3
_BACKOFF_S = (2, 4, 8)  # segundos entre reintentos


def _ejecutar_con_reintentos(fn):
    """Ejecuta fn() con hasta 3 reintentos ante errores de red a Supabase.

    Backoff: 2s tras el intento 1, 4s tras el intento 2. Si el intento 3
    falla, re-lanza la excepción original.
    """
    ultimo_error: Exception | None = None
    for intento in range(_RETRIES):
        try:
            return fn()
        except (httpx.RemoteProtocolError, httpx.ReadTimeout, httpx.ConnectError, httpx.ReadError) as e:
            ultimo_error = e
            logger.warning(
                "Supabase error de red (intento %d/%d): %s",
                intento + 1, _RETRIES, e,
            )
            if intento < _RETRIES - 1:
                time.sleep(_BACKOFF_S[intento])
    raise ultimo_error


# ── Clientes ──────────────────────────────────────────────────────────────────

# ── CFE invoices ──────────────────────────────────────────────────────────────

def save_cfe_invoice(
    invoice: CFEInvoice,
    cliente_id: int,
    contrato_id: int | None = None,
    *,
    validacion_manual: bool = False,
    validado_por: str | None = None,
    motivo_captura_manual: str | None = None,
) -> tuple[int, str]:
    """Persiste un CFEInvoice completo. Devuelve (id de cfe_facturas, nombre_canonico)."""
    nombre_canonico = generar_nombre_canonico(invoice)

    row = {
        "cliente_id": cliente_id,
        "contrato_id": contrato_id,
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
        "validacion_manual": validacion_manual,
        "validado_por": validado_por,
        "motivo_captura_manual": motivo_captura_manual,
    }
    _anio, _mes = _mes_asociado(invoice.periodo_inicio, invoice.periodo_fin)
    row["anio"] = _anio
    row["mes"] = _mes
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

def save_gas_invoice(invoice: GasInvoice, cliente_id: int, contrato_id: int | None = None) -> tuple[int, str]:
    """Persiste una GasInvoice completa. Devuelve (id de gas_facturas, nombre_canonico)."""
    nombre_canonico = generar_nombre_canonico(invoice)

    row = {
        "cliente_id": cliente_id,
        "contrato_id": contrato_id,
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
    _anio, _mes = _mes_asociado(invoice.periodo_inicio, invoice.periodo_fin)
    row["anio"] = _anio
    row["mes"] = _mes
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


# ── Gestión de clientes ───────────────────────────────────────────────────────

_CLIENTE_CAMPOS_EXTENDIDOS = (
    "sector_industrial, contacto_nombre, contacto_cargo, contacto_email, contacto_telefono, "
    "direccion, estado, codigo_postal, tarifa_cfe, "
    "capacidad_instalada_kw, demanda_contratada_kw, anio_inicio_operacion, "
    "regimen_operacion, consumo_anual_estimado_mwh, logo_url, "
    "medio_termico, medio_termico_vapor_pct, nivel_tension_kv, altitud_msnm, tipo_motor, "
    "ppa_suministrador, ppa_rfc_suministrador, ppa_precio_fijo_usd_mwh, "
    "ppa_fecha_inicio_suministro, ppa_energia_contratada_mwh_anual, ppa_capacidad_maxima_kw, "
    "ppa_margen_reserva_cenace_pct, ppa_zona_carga, ppa_rpu, ppa_division, "
    "ppa_pdf_contrato_url, ppa_notas, "
    "precio_gas_manual_mxn_gj_pcs"
)


def _row_to_cliente_dict(row: dict) -> dict:
    return {
        "id": row["id"],
        "nombre": row["nombre"],
        "rfc": row["rfc"],
        "notas": row.get("notas"),
        "created_at": row.get("created_at"),
        "logo_url": row.get("logo_url"),
        "sector_industrial": row.get("sector_industrial"),
        "contacto_nombre": row.get("contacto_nombre"),
        "contacto_cargo": row.get("contacto_cargo"),
        "contacto_email": row.get("contacto_email"),
        "contacto_telefono": row.get("contacto_telefono"),
        "direccion": row.get("direccion"),
        "estado": row.get("estado"),
        "codigo_postal": row.get("codigo_postal"),
        "tarifa_cfe": row.get("tarifa_cfe"),
        "capacidad_instalada_kw": row.get("capacidad_instalada_kw"),
        "demanda_contratada_kw": row.get("demanda_contratada_kw"),
        "anio_inicio_operacion": row.get("anio_inicio_operacion"),
        "regimen_operacion": row.get("regimen_operacion"),
        "consumo_anual_estimado_mwh": row.get("consumo_anual_estimado_mwh"),
        "medio_termico": row.get("medio_termico"),
        "medio_termico_vapor_pct": row.get("medio_termico_vapor_pct"),
        "nivel_tension_kv": row.get("nivel_tension_kv"),
        "altitud_msnm": row.get("altitud_msnm"),
        "tipo_motor": row.get("tipo_motor"),
        # Campos PPA
        "ppa_suministrador": row.get("ppa_suministrador"),
        "ppa_rfc_suministrador": row.get("ppa_rfc_suministrador"),
        "ppa_precio_fijo_usd_mwh": row.get("ppa_precio_fijo_usd_mwh"),
        "ppa_fecha_inicio_suministro": row.get("ppa_fecha_inicio_suministro"),
        "ppa_energia_contratada_mwh_anual": row.get("ppa_energia_contratada_mwh_anual"),
        "ppa_capacidad_maxima_kw": row.get("ppa_capacidad_maxima_kw"),
        "ppa_margen_reserva_cenace_pct": row.get("ppa_margen_reserva_cenace_pct"),
        "ppa_zona_carga": row.get("ppa_zona_carga"),
        "ppa_rpu": row.get("ppa_rpu"),
        "ppa_division": row.get("ppa_division"),
        "ppa_pdf_contrato_url": row.get("ppa_pdf_contrato_url"),
        "ppa_notas": row.get("ppa_notas"),
        "precio_gas_manual_mxn_gj_pcs": row.get("precio_gas_manual_mxn_gj_pcs"),
        "num_cfe": len(row.get("cfe_facturas") or []),
        "num_gas": len(row.get("gas_facturas") or []),
        "num_calificado": len(row.get("facturas_electricidad_calificado") or []),
        "num_electricidad": len(row.get("cfe_facturas") or []) + len(row.get("facturas_electricidad_calificado") or []),
    }


def get_all_clientes_con_conteos() -> list[dict]:
    """Devuelve todos los clientes con conteo de facturas CFE y gas. Ordenados por nombre."""
    result = _supabase.table("clientes").select(
        f"id, nombre, rfc, notas, created_at, logo_url, sector_industrial, cfe_facturas(id), gas_facturas(id), facturas_electricidad_calificado(id)"
    ).order("nombre").execute()
    return [_row_to_cliente_dict(row) for row in result.data]


def get_cliente_con_conteos(cliente_id: int) -> dict | None:
    """Devuelve un cliente con todos sus campos y conteo de facturas, o None si no existe."""
    result = _supabase.table("clientes").select(
        f"id, nombre, rfc, notas, created_at, {_CLIENTE_CAMPOS_EXTENDIDOS}, "
        "cfe_facturas(id), gas_facturas(id), facturas_electricidad_calificado(id)"
    ).eq("id", cliente_id).execute()
    if not result.data:
        return None
    return _row_to_cliente_dict(result.data[0])


def create_cliente(
    nombre: str,
    rfc: str,
    notas: str | None,
    sector_industrial: str | None = None,
    contacto_nombre: str | None = None,
    contacto_cargo: str | None = None,
    contacto_email: str | None = None,
    contacto_telefono: str | None = None,
    direccion: str | None = None,
    estado: str | None = None,
    codigo_postal: str | None = None,
    tarifa_cfe: str | None = None,
    capacidad_instalada_kw: float | None = None,
    demanda_contratada_kw: float | None = None,
    anio_inicio_operacion: int | None = None,
    regimen_operacion: str | None = None,
    consumo_anual_estimado_mwh: float | None = None,
    medio_termico: str | None = None,
    medio_termico_vapor_pct: int | None = None,
    nivel_tension_kv: str | None = None,
    altitud_msnm: int | None = None,
    tipo_motor: str | None = None,
) -> int:
    """Crea un nuevo cliente. Devuelve el id asignado."""
    data: dict = {
        "nombre": nombre,
        "rfc": rfc,
        "notas": notas or None,
        "sector_industrial": sector_industrial,
        "contacto_nombre": contacto_nombre,
        "contacto_cargo": contacto_cargo,
        "contacto_email": contacto_email,
        "contacto_telefono": contacto_telefono,
        "direccion": direccion,
        "estado": estado,
        "codigo_postal": codigo_postal,
        "tarifa_cfe": tarifa_cfe,
        "capacidad_instalada_kw": capacidad_instalada_kw,
        "demanda_contratada_kw": demanda_contratada_kw,
        "anio_inicio_operacion": anio_inicio_operacion,
        "regimen_operacion": regimen_operacion,
        "consumo_anual_estimado_mwh": consumo_anual_estimado_mwh,
        "medio_termico": medio_termico,
        "medio_termico_vapor_pct": medio_termico_vapor_pct,
        "nivel_tension_kv": nivel_tension_kv,
        "altitud_msnm": altitud_msnm,
        "tipo_motor": tipo_motor,
    }
    result = _supabase.table("clientes").insert(data).execute()
    return result.data[0]["id"]


def update_cliente(
    cliente_id: int,
    nombre: str,
    notas: str | None,
    rfc: str | None = None,
    sector_industrial: str | None = None,
    contacto_nombre: str | None = None,
    contacto_cargo: str | None = None,
    contacto_email: str | None = None,
    contacto_telefono: str | None = None,
    direccion: str | None = None,
    estado: str | None = None,
    codigo_postal: str | None = None,
    tarifa_cfe: str | None = None,
    capacidad_instalada_kw: float | None = None,
    demanda_contratada_kw: float | None = None,
    anio_inicio_operacion: int | None = None,
    regimen_operacion: str | None = None,
    consumo_anual_estimado_mwh: float | None = None,
    medio_termico: str | None = None,
    medio_termico_vapor_pct: int | None = None,
    nivel_tension_kv: str | None = None,
    altitud_msnm: int | None = None,
    tipo_motor: str | None = None,
) -> None:
    """Actualiza los campos del cliente. rfc=None preserva el RFC actual sin tocarlo."""
    data: dict = {
        "nombre": nombre,
        "notas": notas or None,
        "sector_industrial": sector_industrial,
        "contacto_nombre": contacto_nombre,
        "contacto_cargo": contacto_cargo,
        "contacto_email": contacto_email,
        "contacto_telefono": contacto_telefono,
        "direccion": direccion,
        "estado": estado,
        "codigo_postal": codigo_postal,
        "tarifa_cfe": tarifa_cfe,
        "capacidad_instalada_kw": capacidad_instalada_kw,
        "demanda_contratada_kw": demanda_contratada_kw,
        "anio_inicio_operacion": anio_inicio_operacion,
        "regimen_operacion": regimen_operacion,
        "consumo_anual_estimado_mwh": consumo_anual_estimado_mwh,
        "medio_termico": medio_termico,
        "medio_termico_vapor_pct": medio_termico_vapor_pct,
        "nivel_tension_kv": nivel_tension_kv,
        "altitud_msnm": altitud_msnm,
        "tipo_motor": tipo_motor,
    }
    if rfc is not None:
        data["rfc"] = rfc
    _supabase.table("clientes").update(data).eq("id", cliente_id).execute()


def upload_logo(cliente_id: int, file_bytes: bytes, content_type: str) -> str:
    """Sube el logo al bucket client-logos y actualiza logo_url en clientes. Devuelve la URL pública."""
    path = f"cliente_{cliente_id}.png"
    _supabase.storage.from_("client-logos").upload(
        path=path,
        file=file_bytes,
        file_options={"content-type": content_type, "upsert": "true"},
    )
    url = _supabase.storage.from_("client-logos").get_public_url(path)
    _supabase.table("clientes").update({"logo_url": url}).eq("id", cliente_id).execute()
    return url


def delete_logo(cliente_id: int) -> None:
    """Elimina el logo del bucket y limpia logo_url en clientes."""
    path = f"cliente_{cliente_id}.png"
    try:
        _supabase.storage.from_("client-logos").remove([path])
    except Exception as exc:
        logger.warning("No se pudo eliminar logo del Storage (cliente_id=%d): %s", cliente_id, exc)
    _supabase.table("clientes").update({"logo_url": None}).eq("id", cliente_id).execute()


def delete_cliente(cliente_id: int) -> None:
    """Borra el cliente. ON DELETE CASCADE en el schema elimina todas sus facturas y relaciones."""
    _supabase.table("clientes").delete().eq("id", cliente_id).execute()


# ── Datos PPA del cliente ──────────────────────────────────────────────────────

_PPA_CAMPOS = (
    "ppa_suministrador", "ppa_rfc_suministrador", "ppa_precio_fijo_usd_mwh",
    "ppa_fecha_inicio_suministro", "ppa_energia_contratada_mwh_anual",
    "ppa_capacidad_maxima_kw", "ppa_margen_reserva_cenace_pct",
    "ppa_zona_carga", "ppa_rpu", "ppa_division", "ppa_pdf_contrato_url", "ppa_notas",
)


def get_cliente_ppa_datos(cliente_id: int) -> dict:
    """Devuelve los campos PPA del cliente como dict. Todos pueden ser None."""
    result = _supabase.table("clientes").select(
        ", ".join(_PPA_CAMPOS)
    ).eq("id", cliente_id).execute()
    if not result.data:
        return {}
    return {k: result.data[0].get(k) for k in _PPA_CAMPOS}


def update_cliente_ppa_datos(cliente_id: int, datos: dict) -> None:
    """Actualiza los campos PPA del cliente. Solo actualiza las claves presentes en datos."""
    allowed = set(_PPA_CAMPOS)
    safe = {k: v for k, v in datos.items() if k in allowed}
    if not safe:
        return
    _supabase.table("clientes").update(safe).eq("id", cliente_id).execute()


def update_precio_gas_manual(cliente_id: int, precio: Decimal | None) -> None:
    """Actualiza el precio de gas manual (MXN/GJ PCS) del cliente. None lo borra."""
    _supabase.table("clientes").update({
        "precio_gas_manual_mxn_gj_pcs": str(precio) if precio is not None else None,
    }).eq("id", cliente_id).execute()


def get_ppa_bloques_mensuales(cliente_id: int, anio: int | None = None) -> list[dict]:
    """Devuelve los bloques mensuales PPA del cliente. Filtra por año si se indica."""
    query = _supabase.table("ppa_bloques_mensuales").select(
        "id, cliente_id, anio, mes, bloque_contratado_mwh"
    ).eq("cliente_id", cliente_id).order("anio").order("mes")
    if anio is not None:
        query = query.eq("anio", anio)
    return query.execute().data


def upsert_ppa_bloque_mensual(
    cliente_id: int, anio: int, mes: int, bloque_mwh: Decimal
) -> None:
    """Inserta o actualiza el bloque contratado para un mes dado."""
    _supabase.table("ppa_bloques_mensuales").upsert({
        "cliente_id": cliente_id,
        "anio": anio,
        "mes": mes,
        "bloque_contratado_mwh": str(bloque_mwh),
    }, on_conflict="cliente_id,anio,mes").execute()


def delete_ppa_bloque_mensual(cliente_id: int, anio: int, mes: int) -> None:
    """Elimina el bloque contratado para un mes dado."""
    _supabase.table("ppa_bloques_mensuales").delete().eq(
        "cliente_id", cliente_id
    ).eq("anio", anio).eq("mes", mes).execute()


def rfc_existe(rfc: str, exclude_id: int | None = None) -> bool:
    """True si ya existe un cliente con ese RFC (opcionalmente excluyendo un id)."""
    query = _supabase.table("clientes").select("id").eq("rfc", rfc)
    if exclude_id is not None:
        query = query.neq("id", exclude_id)
    result = query.execute()
    return len(result.data) > 0


def cliente_tiene_facturas(cliente_id: int) -> bool:
    """True si el cliente tiene al menos una factura CFE o gas."""
    cfe = _supabase.table("cfe_facturas").select("id").eq("cliente_id", cliente_id).limit(1).execute()
    if cfe.data:
        return True
    gas = _supabase.table("gas_facturas").select("id").eq("cliente_id", cliente_id).limit(1).execute()
    return bool(gas.data)


# ── Contratos ─────────────────────────────────────────────────────────────────

class ContratoIdentificadorDuplicado(Exception):
    """El par (cliente_id, identificador_real) ya existe en contratos."""


def _row_to_contrato(row: dict) -> Contrato:
    return Contrato(
        id=row["id"],
        cliente_id=row["cliente_id"],
        nombre=row["nombre"],
        tipo=row["tipo"],
        identificador_real=row["identificador_real"],
        notas=row.get("notas"),
        created_at=row.get("created_at"),
        planta_id=row.get("planta_id"),
    )


def get_contrato_con_conteos(contrato_id: int) -> dict | None:
    """Devuelve un contrato con conteo de facturas CFE, gas y calificado asociadas, o None si no existe."""
    result = _supabase.table("contratos").select("*").eq("id", contrato_id).execute()
    if not result.data:
        return None
    row = result.data[0]
    cfe = _supabase.table("cfe_facturas").select("id").eq("contrato_id", contrato_id).execute()
    gas = _supabase.table("gas_facturas").select("id").eq("contrato_id", contrato_id).execute()
    try:
        calificado = _supabase.table("facturas_electricidad_calificado").select("id").eq("contrato_id", contrato_id).execute()
        num_calificado = len(calificado.data)
    except Exception:
        num_calificado = 0
    return {
        "id": row["id"],
        "cliente_id": row["cliente_id"],
        "nombre": row["nombre"],
        "tipo": row["tipo"],
        "identificador_real": row["identificador_real"],
        "notas": row.get("notas"),
        "created_at": row.get("created_at"),
        "num_cfe": len(cfe.data),
        "num_gas": len(gas.data),
        "num_calificado": num_calificado,
    }


def get_contratos_por_cliente(cliente_id: int, planta_id: int | None = None) -> list[Contrato]:
    """Devuelve contratos del cliente. Si planta_id se provee, filtra a esa planta."""
    q = _supabase.table("contratos").select("*").eq("cliente_id", cliente_id)
    if planta_id is not None:
        q = q.eq("planta_id", planta_id)
    return [_row_to_contrato(r) for r in q.order("nombre").execute().data]


def get_contrato(contrato_id: int) -> Contrato | None:
    """Devuelve un contrato por id, o None si no existe."""
    result = _supabase.table("contratos").select("*").eq("id", contrato_id).execute()
    if not result.data:
        return None
    return _row_to_contrato(result.data[0])


def create_contrato(
    cliente_id: int,
    nombre: str,
    tipo: str,
    identificador_real: str,
    notas: str | None,
    planta_id: int | None = None,
) -> int:
    """Crea un contrato. Devuelve el id asignado.
    Lanza ContratoIdentificadorDuplicado si (cliente_id, identificador_real) ya existe."""
    payload: dict = {
        "cliente_id": cliente_id,
        "nombre": nombre,
        "tipo": tipo,
        "identificador_real": identificador_real,
        "notas": notas if notas else None,
    }
    if planta_id is not None:
        payload["planta_id"] = planta_id
    try:
        result = _supabase.table("contratos").insert(payload).execute()
    except Exception as exc:
        msg = str(exc).lower()
        if "unique" in msg or "duplicate" in msg or "contratos_cliente_id_identificador_real" in msg:
            raise ContratoIdentificadorDuplicado(identificador_real) from exc
        raise
    return result.data[0]["id"]


def update_contrato(
    contrato_id: int,
    nombre: str,
    tipo: str,
    identificador_real: str,
    notas: str | None,
    planta_id: int | None = None,
) -> None:
    """Actualiza los campos del contrato.
    Lanza ContratoIdentificadorDuplicado si el nuevo identificador_real ya existe para el cliente."""
    payload: dict = {
        "nombre": nombre,
        "tipo": tipo,
        "identificador_real": identificador_real,
        "notas": notas if notas else None,
    }
    if planta_id is not None:
        payload["planta_id"] = planta_id
    try:
        _supabase.table("contratos").update(payload).eq("id", contrato_id).execute()
    except Exception as exc:
        msg = str(exc).lower()
        if "unique" in msg or "duplicate" in msg or "contratos_cliente_id_identificador_real" in msg:
            raise ContratoIdentificadorDuplicado(identificador_real) from exc
        raise


def delete_contrato(contrato_id: int) -> None:
    """Borra el contrato. ON DELETE SET NULL en facturas desvincula las facturas asociadas."""
    _supabase.table("contratos").delete().eq("id", contrato_id).execute()


# ── Facturas por contrato ──────────────────────────────────────────────────────

def get_cfe_facturas_por_contrato(contrato_id: int) -> list[dict]:
    """Devuelve las facturas CFE del contrato (campos básicos para la ficha)."""
    result = _supabase.table("cfe_facturas").select(
        "id, nombre_canonico, periodo_inicio, periodo_fin, subtotal_mxn"
    ).eq("contrato_id", contrato_id).order("periodo_inicio").execute()
    return result.data


def get_gas_facturas_por_contrato(contrato_id: int) -> list[dict]:
    """Devuelve las facturas de gas del contrato (campos básicos para la ficha)."""
    result = _supabase.table("gas_facturas").select(
        "id, nombre_canonico, periodo_inicio, periodo_fin, subtotal_mxn"
    ).eq("contrato_id", contrato_id).order("periodo_inicio").execute()
    return result.data


# ── Selección por mes (contrato_meses_seleccionados) ──────────────────────────

def _get_contrato_ids_de_cliente(cliente_id: int) -> list[int]:
    result = _supabase.table("contratos").select("id").eq("cliente_id", cliente_id).execute()
    return [r["id"] for r in result.data]


def get_meses_seleccionados_por_contrato(contrato_id: int) -> list[tuple[int, int]]:
    """Retorna lista de (anio, mes) seleccionados para el contrato."""
    result = _supabase.table("contrato_meses_seleccionados").select("anio, mes").eq(
        "contrato_id", contrato_id
    ).execute()
    return [(r["anio"], r["mes"]) for r in result.data]


def get_meses_seleccionados_por_cliente(cliente_id: int) -> set[tuple[int, int, int]]:
    """Retorna set de (contrato_id, anio, mes) seleccionados para el cliente."""
    contrato_ids = _get_contrato_ids_de_cliente(cliente_id)
    if not contrato_ids:
        return set()
    result = _supabase.table("contrato_meses_seleccionados").select(
        "contrato_id, anio, mes"
    ).in_("contrato_id", contrato_ids).execute()
    return {(r["contrato_id"], r["anio"], r["mes"]) for r in result.data}


def get_anios_con_facturas_por_contrato(contrato_id: int) -> list[int]:
    """Retorna lista ordenada de años que tienen al menos una factura en el contrato."""
    cfe = _supabase.table("cfe_facturas").select("anio").eq("contrato_id", contrato_id).not_.is_(
        "anio", "null"
    ).execute()
    gas = _supabase.table("gas_facturas").select("anio").eq("contrato_id", contrato_id).not_.is_(
        "anio", "null"
    ).execute()
    anios = {r["anio"] for r in cfe.data} | {r["anio"] for r in gas.data}
    return sorted(anios)


def get_meses_con_factura(contrato_id: int, anio: int, contrato_tipo: str = "") -> set[int]:
    """Retorna conjunto de meses (1-12) con al menos una factura en ese contrato/año.

    Si contrato_tipo es 'electrico_calificado', consulta facturas_electricidad_calificado.
    En cualquier otro caso consulta cfe_facturas + gas_facturas (comportamiento por defecto).
    """
    if contrato_tipo == TIPO_ELECTRICO_CALIFICADO:
        cal = _supabase.table("facturas_electricidad_calificado").select("mes").eq(
            "contrato_id", contrato_id
        ).eq("anio", anio).not_.is_("mes", "null").execute()
        return {r["mes"] for r in cal.data}
    cfe = _supabase.table("cfe_facturas").select("mes").eq("contrato_id", contrato_id).eq(
        "anio", anio
    ).not_.is_("mes", "null").execute()
    gas = _supabase.table("gas_facturas").select("mes").eq("contrato_id", contrato_id).eq(
        "anio", anio
    ).not_.is_("mes", "null").execute()
    return {r["mes"] for r in cfe.data} | {r["mes"] for r in gas.data}


def upsert_mes_seleccionado(contrato_id: int, anio: int, mes: int) -> None:
    """Marca un mes como seleccionado (ON CONFLICT DO NOTHING vía upsert)."""
    _supabase.table("contrato_meses_seleccionados").upsert(
        {"contrato_id": contrato_id, "anio": anio, "mes": mes}
    ).execute()


def delete_mes_seleccionado(contrato_id: int, anio: int, mes: int) -> None:
    """Deselecciona un mes."""
    _supabase.table("contrato_meses_seleccionados").delete().eq(
        "contrato_id", contrato_id
    ).eq("anio", anio).eq("mes", mes).execute()


def upsert_meses_seleccionados_anio(contrato_id: int, anio: int, contrato_tipo: str = "") -> int:
    """Selecciona todos los meses con factura del año. Retorna cantidad insertada."""
    meses = get_meses_con_factura(contrato_id, anio, contrato_tipo=contrato_tipo)
    if not meses:
        return 0
    _supabase.table("contrato_meses_seleccionados").upsert(
        [{"contrato_id": contrato_id, "anio": anio, "mes": m} for m in meses]
    ).execute()
    return len(meses)


def delete_meses_seleccionados_anio(contrato_id: int, anio: int) -> None:
    """Deselecciona todos los meses del año para ese contrato."""
    _supabase.table("contrato_meses_seleccionados").delete().eq(
        "contrato_id", contrato_id
    ).eq("anio", anio).execute()


def get_tipos_electricos_con_meses_seleccionados(cliente_id: int, planta_id: int | None = None) -> list[str]:
    """
    Devuelve lista de tipos de contrato eléctrico que tienen al menos un mes
    seleccionado para el cliente dado. Si planta_id se provee, limita a esa planta.
    """
    from models.contrato import TIPOS_ELECTRICOS

    q = _supabase.table("contratos").select("id, tipo").eq("cliente_id", cliente_id).in_("tipo", list(TIPOS_ELECTRICOS))
    if planta_id is not None:
        q = q.eq("planta_id", planta_id)
    contratos = q.execute()

    tipos_con_meses = set()
    for contrato in contratos.data:
        contrato_id = contrato["id"]
        tipo = contrato["tipo"]
        result = _supabase.table("contrato_meses_seleccionados").select("contrato_id").eq("contrato_id", contrato_id).limit(1).execute()
        if result.data:
            tipos_con_meses.add(tipo)

    return sorted(tipos_con_meses)


def get_tipo_suministro_electrico_seleccionado(cliente_id: int, planta_id: int | None = None) -> str | None:
    """
    Detecta el tipo de suministro eléctrico de los meses seleccionados del cliente.

    Returns:
        'electrico_basico'    — todos los meses seleccionados son de contratos CFE
        'electrico_calificado' — todos los meses seleccionados son de contratos PPA
        None                  — sin meses eléctricos seleccionados (solo gas, o ninguno)

    Nota: el bloqueo de mezcla (Task 22) garantiza que nunca coexistan basico y calificado.
    Si por algún bug existieran ambos, retorna el primero encontrado.
    """
    tipos = get_tipos_electricos_con_meses_seleccionados(cliente_id, planta_id=planta_id)
    if not tipos:
        return None
    return tipos[0]  # bloqueo de mezcla garantiza máximo uno; si hay dos, tomar el primero


def get_sidebar_data_contrato(contrato_id: int, contrato_tipo: str = "") -> list[dict]:
    """Retorna datos completos del sidebar para un contrato: años con facturas y selección.

    Cada elemento: {"anio": int, "meses_con_factura": [int], "meses_seleccionados": [int]}
    Ordenado por año descendente (más reciente primero).

    Si contrato_tipo es 'electrico_calificado', consulta facturas_electricidad_calificado (2 queries).
    En cualquier otro caso usa CFE + gas (3 queries fijas), sin N+1.
    """
    # Agrupar meses con factura por año
    meses_por_anio: dict[int, set[int]] = defaultdict(set)

    if contrato_tipo == TIPO_ELECTRICO_CALIFICADO:
        # Query 1: facturas calificado para este contrato
        cal = _supabase.table("facturas_electricidad_calificado").select("anio, mes").eq(
            "contrato_id", contrato_id
        ).not_.is_("anio", "null").not_.is_("mes", "null").execute()
        for r in cal.data:
            meses_por_anio[r["anio"]].add(r["mes"])
    else:
        # Query 1: todos los (anio, mes) con factura CFE para este contrato
        cfe = _supabase.table("cfe_facturas").select("anio, mes").eq(
            "contrato_id", contrato_id
        ).not_.is_("anio", "null").not_.is_("mes", "null").execute()

        # Query 2: todos los (anio, mes) con factura de gas para este contrato
        gas = _supabase.table("gas_facturas").select("anio, mes").eq(
            "contrato_id", contrato_id
        ).not_.is_("anio", "null").not_.is_("mes", "null").execute()

        for r in cfe.data:
            meses_por_anio[r["anio"]].add(r["mes"])
        for r in gas.data:
            meses_por_anio[r["anio"]].add(r["mes"])

    # Query final: meses seleccionados
    sel_result = _supabase.table("contrato_meses_seleccionados").select("anio, mes").eq(
        "contrato_id", contrato_id
    ).execute()

    # Agrupar meses seleccionados por año
    sel_por_anio: dict[int, set[int]] = defaultdict(set)
    for r in sel_result.data:
        sel_por_anio[r["anio"]].add(r["mes"])

    resultado = []
    for anio in sorted(meses_por_anio, reverse=True):
        resultado.append({
            "anio": anio,
            "meses_con_factura": sorted(meses_por_anio[anio]),
            "meses_seleccionados": sorted(sel_por_anio.get(anio, set())),
        })
    return resultado


def get_sidebar_data_cliente(cliente_id: int) -> dict[int, list[dict]]:
    """Retorna datos de sidebar para TODOS los contratos de un cliente en 4 queries.

    Devuelve dict {contrato_id: [{"anio": int, "meses_con_factura": [int], "meses_seleccionados": [int]}, ...]}.
    Ordenado por año descendente dentro de cada contrato.
    Incluye facturas CFE, gas y electrico_calificado.
    """
    # Query 1: todos los (contrato_id, anio, mes) CFE del cliente
    cfe = _supabase.table("cfe_facturas").select("contrato_id, anio, mes").eq(
        "cliente_id", cliente_id
    ).not_.is_("contrato_id", "null").not_.is_("anio", "null").not_.is_("mes", "null").execute()

    # Query 2: todos los (contrato_id, anio, mes) gas del cliente
    gas = _supabase.table("gas_facturas").select("contrato_id, anio, mes").eq(
        "cliente_id", cliente_id
    ).not_.is_("contrato_id", "null").not_.is_("anio", "null").not_.is_("mes", "null").execute()

    # Query 3: todos los (contrato_id, anio, mes) calificado del cliente
    try:
        cal = _supabase.table("facturas_electricidad_calificado").select("contrato_id, anio, mes").eq(
            "cliente_id", cliente_id
        ).not_.is_("contrato_id", "null").not_.is_("anio", "null").not_.is_("mes", "null").execute()
        cal_data = cal.data
    except Exception:
        cal_data = []

    # Combinar todas las fuentes para determinar contrato_ids y agrupar meses con factura
    todas = cfe.data + gas.data + cal_data
    contrato_ids = {r["contrato_id"] for r in todas}
    if not contrato_ids:
        return {}

    # Query 4: todos los meses seleccionados del cliente (via contratos del cliente)
    sel_result = _supabase.table("contrato_meses_seleccionados").select(
        "contrato_id, anio, mes"
    ).in_("contrato_id", list(contrato_ids)).execute()

    # Agrupar meses con factura por (contrato_id, anio)
    meses_por_contrato_anio: dict[tuple[int, int], set[int]] = defaultdict(set)
    for r in todas:
        meses_por_contrato_anio[(r["contrato_id"], r["anio"])].add(r["mes"])

    # Agrupar meses seleccionados por (contrato_id, anio)
    sel_por_contrato_anio: dict[tuple[int, int], set[int]] = defaultdict(set)
    for r in sel_result.data:
        sel_por_contrato_anio[(r["contrato_id"], r["anio"])].add(r["mes"])

    # Construir resultado
    contrato_anios: dict[int, set[int]] = defaultdict(set)
    for (cid, anio) in meses_por_contrato_anio:
        contrato_anios[cid].add(anio)

    resultado: dict[int, list[dict]] = {}
    for cid in contrato_anios:
        anios_data = []
        for anio in sorted(contrato_anios[cid], reverse=True):
            anios_data.append({
                "anio": anio,
                "meses_con_factura": sorted(meses_por_contrato_anio[(cid, anio)]),
                "meses_seleccionados": sorted(sel_por_contrato_anio.get((cid, anio), set())),
            })
        resultado[cid] = anios_data
    return resultado


def get_facturas_para_dashboard(cliente_id: int, planta_id: int | None = None) -> tuple[list[CFEInvoice], list[GasInvoice]]:
    """Carga facturas CFE y gas seleccionadas. Si planta_id se provee, solo considera
    contratos de esa planta, filtrando los meses seleccionados de otras plantas.
    """
    seleccionados = get_meses_seleccionados_por_cliente(cliente_id)
    if not seleccionados:
        return [], []
    if planta_id is not None:
        r = _supabase.table("contratos").select("id").eq("planta_id", planta_id).execute()
        ids_planta = {row["id"] for row in r.data}
        seleccionados = {(c, a, m) for c, a, m in seleccionados if c in ids_planta}
        if not seleccionados:
            return [], []
    contrato_ids = list({c for c, _, _ in seleccionados})

    cfe_result = _supabase.table("cfe_facturas").select(
        "*, clientes(nombre, rfc), cfe_periodos(*), cfe_mem_componentes(*)"
    ).eq("cliente_id", cliente_id).in_("contrato_id", contrato_ids).order("periodo_inicio").execute()

    gas_result = _supabase.table("gas_facturas").select(
        "*, clientes(nombre, rfc), gas_conceptos(*)"
    ).eq("cliente_id", cliente_id).in_("contrato_id", contrato_ids).order("periodo_inicio").execute()

    cfe_invoices = [
        _row_to_cfe_invoice(row) for row in cfe_result.data
        if row.get("anio") and row.get("mes")
        and (row["contrato_id"], row["anio"], row["mes"]) in seleccionados
    ]
    gas_invoices = [
        _row_to_gas_invoice(row) for row in gas_result.data
        if row.get("anio") and row.get("mes")
        and (row["contrato_id"], row["anio"], row["mes"]) in seleccionados
    ]
    return cfe_invoices, gas_invoices


def get_cfe_invoices_for_dashboard(cliente_id: int) -> list[CFEInvoice]:
    """Carga facturas CFE del cliente cuyos meses están seleccionados. Usa get_facturas_para_dashboard internamente."""
    return get_facturas_para_dashboard(cliente_id)[0]


def get_gas_invoices_for_dashboard(cliente_id: int) -> list[GasInvoice]:
    """Carga facturas de gas del cliente cuyos meses están seleccionados. Usa get_facturas_para_dashboard internamente."""
    return get_facturas_para_dashboard(cliente_id)[1]


def delete_cfe_factura(factura_id: int) -> None:
    """Borra una factura CFE (ON DELETE CASCADE elimina periodos y componentes)."""
    _supabase.table("cfe_facturas").delete().eq("id", factura_id).execute()


def delete_gas_factura(factura_id: int) -> None:
    """Borra una factura de gas (ON DELETE CASCADE elimina conceptos)."""
    _supabase.table("gas_facturas").delete().eq("id", factura_id).execute()


def get_ultimas_cfe_invoices(cliente_id: int, n: int = 12) -> list[CFEInvoice]:
    """Retorna las n facturas CFE más recientes del cliente, sin filtrar por meses seleccionados.

    Ordenadas por periodo_inicio DESC y devueltas ya en orden ASC (cronológico).
    Usado por el dashboard de Cogeneración (regla: siempre últimas 12).
    """
    result = _supabase.table("cfe_facturas").select(
        "*, clientes(nombre, rfc), cfe_periodos(*), cfe_mem_componentes(*)"
    ).eq("cliente_id", cliente_id).order("periodo_inicio", desc=True).limit(n).execute()
    return [_row_to_cfe_invoice(row) for row in result.data]


def get_ultimas_gas_invoices(cliente_id: int, n: int = 12) -> list[GasInvoice]:
    """Retorna las n facturas de gas más recientes del cliente, sin filtrar por meses seleccionados.

    Ordenadas por periodo_inicio DESC y devueltas ya en orden ASC (cronológico).
    Usado por el dashboard de Cogeneración (regla: siempre últimas 12).
    """
    result = _supabase.table("gas_facturas").select(
        "*, clientes(nombre, rfc), gas_conceptos(*)"
    ).eq("cliente_id", cliente_id).order("periodo_inicio", desc=True).limit(n).execute()
    return [_row_to_gas_invoice(row) for row in result.data]


def get_ultimas_ppa_invoices(cliente_id: int, n: int = 12) -> list["FacturaCalificado"]:
    """Retorna las n facturas PPA más recientes del cliente, sin filtrar por meses seleccionados.

    Usado por el dashboard de Cogeneración (regla: siempre últimas 12).
    """
    result = _supabase.table("facturas_electricidad_calificado").select("*").eq(
        "cliente_id", cliente_id
    ).order("periodo_inicio", desc=True).limit(n).execute()
    return [_row_to_factura_calificado(row) for row in result.data]


# ── Facturas electricidad calificado (suministro calificado / PPA) ─────────────

def _row_to_factura_calificado(row: dict) -> FacturaCalificado:
    """Convierte una fila de Supabase en un objeto FacturaCalificado."""
    def _parse_decimal(v) -> Decimal | None:
        if v is None:
            return None
        return Decimal(str(v))

    return FacturaCalificado(
        id=row["id"],
        contrato_id=row["contrato_id"],
        cliente_id=row["cliente_id"],
        suministrador=row.get("suministrador"),
        rpu=row.get("rpu"),
        serie_folio=row.get("serie_folio"),
        periodo_inicio=date.fromisoformat(str(row["periodo_inicio"])[:10]),
        periodo_fin=date.fromisoformat(str(row["periodo_fin"])[:10]),
        dias_facturados=row.get("dias_facturados"),
        anio=row.get("anio"),
        mes=row.get("mes"),
        nombre_canonico=row.get("nombre_canonico"),
        consumo_kwh=Decimal(str(row["consumo_kwh"])),
        precio_unitario_mxn_kwh=Decimal(str(row["precio_unitario_mxn_kwh"])),
        subtotal_mxn=Decimal(str(row["subtotal_mxn"])),
        iva_mxn=_parse_decimal(row.get("iva_mxn")),
        total_mxn=_parse_decimal(row.get("total_mxn")),
        excedente_detectado=bool(row.get("excedente_detectado", False)),
        advertencias=row.get("advertencias") or [],
        pdf_url=row.get("pdf_url"),
        parser_version=row.get("parser_version"),
        created_at=row.get("created_at"),
    )


def create_factura_calificado(contrato_id: int, cliente_id: int, datos: dict) -> int:
    """Inserta una nueva factura calificada. Devuelve el id asignado."""
    _NUMERIC_FIELDS = {"consumo_kwh", "precio_unitario_mxn_kwh", "subtotal_mxn", "iva_mxn", "total_mxn"}
    row = {"contrato_id": contrato_id, "cliente_id": cliente_id}
    for k, v in datos.items():
        if v is None:
            row[k] = None
        elif k in _NUMERIC_FIELDS and isinstance(v, Decimal):
            row[k] = str(v)
        else:
            row[k] = v
    result = _supabase.table("facturas_electricidad_calificado").insert(row).execute()
    return result.data[0]["id"]


def get_factura_calificado(factura_id: int) -> FacturaCalificado | None:
    """Devuelve una factura calificada por id, o None si no existe."""
    result = _supabase.table("facturas_electricidad_calificado").select("*").eq(
        "id", factura_id
    ).execute()
    if not result.data:
        return None
    return _row_to_factura_calificado(result.data[0])


def get_facturas_calificado_por_contrato(contrato_id: int) -> list[dict]:
    """Devuelve campos básicos de las facturas calificadas del contrato (para la ficha)."""
    result = _supabase.table("facturas_electricidad_calificado").select(
        "id, nombre_canonico, periodo_inicio, periodo_fin, subtotal_mxn, consumo_kwh, excedente_detectado"
    ).eq("contrato_id", contrato_id).order("periodo_inicio").execute()
    return result.data


def get_facturas_calificado_por_cliente(cliente_id: int) -> list[FacturaCalificado]:
    """Devuelve todas las facturas calificadas del cliente, ordenadas por periodo_inicio."""
    result = _supabase.table("facturas_electricidad_calificado").select("*").eq(
        "cliente_id", cliente_id
    ).order("periodo_inicio").execute()
    return [_row_to_factura_calificado(row) for row in result.data]


def update_factura_calificado(factura_id: int, datos: dict) -> None:
    """Actualiza una factura calificada por id."""
    _NUMERIC_FIELDS = {"consumo_kwh", "precio_unitario_mxn_kwh", "subtotal_mxn", "iva_mxn", "total_mxn"}
    payload: dict = {}
    for k, v in datos.items():
        if v is None:
            payload[k] = None
        elif k in _NUMERIC_FIELDS and isinstance(v, Decimal):
            payload[k] = str(v)
        else:
            payload[k] = v
    _supabase.table("facturas_electricidad_calificado").update(payload).eq("id", factura_id).execute()


def delete_factura_calificado(factura_id: int) -> None:
    """Borra una factura calificada por id."""
    _supabase.table("facturas_electricidad_calificado").delete().eq("id", factura_id).execute()


def get_facturas_para_dashboard_calificado(
    cliente_id: int,
    meses_seleccionados: set[tuple[int, int, int]],
) -> list[FacturaCalificado]:
    """Devuelve FacturaCalificado para los (contrato_id, anio, mes) seleccionados del cliente."""
    if not meses_seleccionados:
        return []
    result = _supabase.table("facturas_electricidad_calificado").select("*").eq(
        "cliente_id", cliente_id
    ).order("periodo_inicio").execute()
    return [
        _row_to_factura_calificado(row) for row in result.data
        if row.get("anio") and row.get("mes")
        and (row["contrato_id"], row["anio"], row["mes"]) in meses_seleccionados
    ]


def get_facturas_ppa_y_gas_para_dashboard(
    cliente_id: int,
    planta_id: int | None = None,
) -> tuple[list[FacturaCalificado], list[GasInvoice]]:
    """Carga facturas PPA y gas seleccionadas. Si planta_id se provee, filtra a esa planta."""
    seleccionados = get_meses_seleccionados_por_cliente(cliente_id)
    if not seleccionados:
        return [], []
    if planta_id is not None:
        r = _supabase.table("contratos").select("id").eq("planta_id", planta_id).execute()
        ids_planta = {row["id"] for row in r.data}
        seleccionados = {(c, a, m) for c, a, m in seleccionados if c in ids_planta}
        if not seleccionados:
            return [], []
    contrato_ids = list({c for c, _, _ in seleccionados})

    ppa_result = _supabase.table("facturas_electricidad_calificado").select("*").eq(
        "cliente_id", cliente_id
    ).in_("contrato_id", contrato_ids).order("periodo_inicio").execute()

    gas_result = _supabase.table("gas_facturas").select(
        "*, clientes(nombre, rfc), gas_conceptos(*)"
    ).eq("cliente_id", cliente_id).in_("contrato_id", contrato_ids).order("periodo_inicio").execute()

    ppa_invoices = [
        _row_to_factura_calificado(row) for row in ppa_result.data
        if row.get("anio") and row.get("mes")
        and (row["contrato_id"], row["anio"], row["mes"]) in seleccionados
    ]
    gas_invoices = [
        _row_to_gas_invoice(row) for row in gas_result.data
        if row.get("anio") and row.get("mes")
        and (row["contrato_id"], row["anio"], row["mes"]) in seleccionados
    ]
    return ppa_invoices, gas_invoices


# ── Configuración global ──────────────────────────────────────────────────────

def list_configuracion() -> list[dict]:
    """Devuelve todas las filas de configuracion ordenadas por clave."""
    resp = _supabase.table("configuracion").select("*").order("clave").execute()
    return resp.data or []


def get_configuracion(clave: str) -> str | None:
    """Lee el valor de una clave en la tabla configuracion. None si no existe."""
    resp = _supabase.table("configuracion").select("valor").eq("clave", clave).limit(1).execute()
    return resp.data[0]["valor"] if resp.data else None


def get_configuracion_row(clave: str) -> dict | None:
    """Lee la fila completa de configuracion para una clave. None si no existe."""
    resp = _supabase.table("configuracion").select("*").eq("clave", clave).limit(1).execute()
    return resp.data[0] if resp.data else None


def get_session_version(user_id: str) -> int | None:
    """Devuelve la session_version actual del usuario, o None si no existe o hay error."""
    try:
        res = _supabase.table("user_profiles").select("session_version").eq("id", user_id).limit(1).execute()
        rows = res.data or []
        return rows[0].get("session_version") if rows else None
    except Exception:
        return None


def incrementar_session_version(user_id: str) -> None:
    """Incrementa session_version del usuario. Invalida todas las sesiones activas."""
    actual = get_session_version(user_id) or 0
    _supabase.table("user_profiles").update({"session_version": actual + 1}).eq("id", user_id).execute()


def registrar_login_audit(
    user_id: str | None,
    email: str,
    success: bool,
    ip_address: str | None = None,
    user_agent: str | None = None,
    failure_reason: str | None = None,
) -> None:
    """Registra un intento de login en login_audit. Falla-silenciosa."""
    try:
        _supabase.table("login_audit").insert({
            "user_id": user_id,
            "email": email,
            "success": success,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "failure_reason": failure_reason,
        }).execute()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "No se pudo registrar login_audit para %s: %s", email, exc
        )


def set_configuracion(clave: str, valor: str) -> None:
    """Crea o actualiza un parámetro en la tabla configuracion."""
    from datetime import datetime, timezone
    _supabase.table("configuracion").upsert(
        {
            "clave": clave,
            "valor": valor,
            "fecha_modificacion": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="clave",
    ).execute()


# ── Mediciones cincominutal ────────────────────────────────────────────────────

def get_mediciones_por_cliente(cliente_id: int, planta_id: int | None = None) -> list[dict]:
    """Lista de mediciones cargadas para el cliente, ordenadas por anio DESC, mes DESC.

    Si planta_id se especifica, filtra a las mediciones de esa planta.
    """
    q = (
        _supabase.table("mediciones_cincominutal")
        .select("id, cliente_id, planta_id, anio, mes, nombre, uploaded_at, uploaded_by")
        .eq("cliente_id", cliente_id)
    )
    if planta_id is not None:
        q = q.eq("planta_id", planta_id)
    return q.order("anio", desc=True).order("mes", desc=True).execute().data or []


def get_medicion(medicion_id: int) -> dict | None:
    """Retorna una medición por ID o None si no existe."""
    resp = (
        _supabase.table("mediciones_cincominutal")
        .select("*")
        .eq("id", medicion_id)
        .execute()
    )
    return resp.data[0] if resp.data else None


def create_medicion(
    cliente_id: int, anio: int, mes: int, nombre: str, uploaded_by: str
) -> int:
    """Inserta cabecera en mediciones_cincominutal. Retorna el id creado.

    Raises:
        ValueError: si ya existe una medición para ese mes/año del cliente.
    """
    existing = (
        _supabase.table("mediciones_cincominutal")
        .select("id")
        .eq("cliente_id", cliente_id)
        .eq("anio", anio)
        .eq("mes", mes)
        .execute()
    )
    if existing.data:
        raise ValueError("Ya existe una medición para ese mes/año")

    resp = (
        _supabase.table("mediciones_cincominutal")
        .insert({
            "cliente_id":   cliente_id,
            "anio":         anio,
            "mes":          mes,
            "nombre":       nombre,
            "uploaded_by":  uploaded_by,
        })
        .execute()
    )
    return resp.data[0]["id"]


def save_medicion_datos(medicion_id: int, datos: list[dict]) -> None:
    """Inserta puntos en mediciones_cincominutal_datos en batches de 1000."""
    BATCH = 1000
    for i in range(0, len(datos), BATCH):
        batch = datos[i : i + BATCH]
        rows = [
            {
                "medicion_id": medicion_id,
                "ts":          d["ts"].isoformat() if hasattr(d["ts"], "isoformat") else str(d["ts"]),
                "potencia_kw": d["potencia_kw"],
            }
            for d in batch
        ]
        _supabase.table("mediciones_cincominutal_datos").insert(rows).execute()


def get_medicion_datos(medicion_id: int) -> list[dict]:
    """Todos los puntos de una medición ordenados por ts ASC.
    Pagina de 1,000 en 1,000 para superar el max-rows de PostgREST."""
    PAGE = 1000
    result = []
    start = 0
    while True:
        resp = (
            _supabase.table("mediciones_cincominutal_datos")
            .select("ts, potencia_kw")
            .eq("medicion_id", medicion_id)
            .order("ts", desc=False)
            .range(start, start + PAGE - 1)
            .execute()
        )
        batch = resp.data or []
        result.extend(batch)
        if len(batch) < PAGE:
            break
        start += PAGE
    return result


def update_medicion(medicion_id: int, campos: dict) -> dict | None:
    """Actualiza campos de una medición. Retorna el registro actualizado o None."""
    resp = (
        _supabase.table("mediciones_cincominutal")
        .update(campos)
        .eq("id", medicion_id)
        .execute()
    )
    return resp.data[0] if resp.data else None


def delete_medicion(medicion_id: int) -> None:
    """Borra la cabecera; ON DELETE CASCADE elimina los datos automáticamente."""
    _supabase.table("mediciones_cincominutal").delete().eq("id", medicion_id).execute()


# ══════════════════════════════════════════════════════════════════════════════
# FASE 2 — Telemetría de medidores Accuenergy Acuvim II
# ══════════════════════════════════════════════════════════════════════════════

def crear_medidor(
    cliente_id: int,
    nombre: str,
    punto_medicion: str | None = None,
    ubicacion: str | None = None,
    numero_serie: str | None = None,
    relacion_tc: float | None = None,
    marca: str = "Accuenergy",
    modelo: str = "Acuvim II",
) -> dict:
    """Inserta un medidor en la tabla medidores y retorna el registro creado con id."""
    payload = {
        "cliente_id":      cliente_id,
        "nombre":          nombre,
        "punto_medicion":  punto_medicion,
        "ubicacion":       ubicacion,
        "numero_serie":    numero_serie,
        "relacion_tc":     relacion_tc,
        "marca":           marca,
        "modelo":          modelo,
    }
    resp = _supabase.table("medidores").insert(payload).execute()
    return resp.data[0]


def obtener_medidores_por_cliente(cliente_id: int) -> list[dict]:
    """Retorna todos los medidores de un cliente, ordenados por nombre."""
    resp = (
        _supabase.table("medidores")
        .select("*")
        .eq("cliente_id", cliente_id)
        .order("nombre", desc=False)
        .limit(20000)
        .execute()
    )
    return resp.data or []


def obtener_medidor(medidor_id: int) -> dict | None:
    """Retorna un medidor por id, o None si no existe."""
    resp = (
        _supabase.table("medidores")
        .select("*")
        .eq("id", medidor_id)
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None


def insertar_medicion(medidor_id: int, timestamp: str, **variables) -> dict:
    """Inserta una lectura completa en mediciones_tiempo_real.

    timestamp debe ser un string ISO-8601 o un datetime con tzinfo.
    Las variables del set completo Acuvim II se pasan como kwargs.
    Retorna el registro insertado.
    """
    payload = {"medidor_id": medidor_id, "timestamp": timestamp, **variables}
    resp = _supabase.table("mediciones_tiempo_real").insert(payload).execute()
    return resp.data[0]


def insertar_mediciones_batch(lista_mediciones: list[dict]) -> int:
    """Inserta múltiples lecturas en mediciones_tiempo_real.

    Cada elemento debe ser un dict con 'medidor_id', 'timestamp' y las variables.
    Retorna el número de filas insertadas.
    """
    if not lista_mediciones:
        return 0
    _BATCH = 1000
    total = 0
    for i in range(0, len(lista_mediciones), _BATCH):
        chunk = lista_mediciones[i : i + _BATCH]
        resp = _supabase.table("mediciones_tiempo_real").insert(chunk).execute()
        total += len(resp.data or [])
    return total


def obtener_mediciones_recientes(
    medidor_id: int,
    desde: str,
    hasta: str,
) -> list[dict]:
    """Lecturas de mediciones_tiempo_real para un medidor en el rango [desde, hasta].

    desde/hasta son strings ISO-8601. Ordenadas por timestamp ASC.
    """
    resp = (
        _supabase.table("mediciones_tiempo_real")
        .select("*")
        .eq("medidor_id", medidor_id)
        .gte("timestamp", desde)
        .lte("timestamp", hasta)
        .order("timestamp", desc=False)
        .limit(20000)
        .execute()
    )
    return resp.data or []


def obtener_agregados_15min(
    medidor_id: int,
    desde: str,
    hasta: str,
) -> list[dict]:
    """Buckets de 15 minutos en mediciones_agregadas_15min para un medidor en [desde, hasta].

    Ordenados por bucket_15min ASC.
    """
    resp = (
        _supabase.table("mediciones_agregadas_15min")
        .select("*")
        .eq("medidor_id", medidor_id)
        .gte("bucket_15min", desde)
        .lte("bucket_15min", hasta)
        .order("bucket_15min", desc=False)
        .limit(20000)
        .execute()
    )
    return resp.data or []


def obtener_agregados_5min(
    medidor_id: int,
    desde: str,
    hasta: str,
) -> list[dict]:
    """Buckets de 5 minutos en mediciones_agregadas_5min para un medidor en [desde, hasta].

    Ordenados por bucket_5min ASC. Reintenta hasta 3 veces ante errores de red.
    """
    def _query():
        resp = (
            _supabase.table("mediciones_agregadas_5min")
            .select("*")
            .eq("medidor_id", medidor_id)
            .gte("bucket_5min", desde)
            .lte("bucket_5min", hasta)
            .order("bucket_5min", desc=False)
            .limit(20000)
            .execute()
        )
        return resp.data or []

    return _ejecutar_con_reintentos(_query)


def obtener_agregados_horarios(
    medidor_id: int,
    desde: str,
    hasta: str,
) -> list[dict]:
    """Buckets horarios en mediciones_agregadas_horarias para un medidor en [desde, hasta].

    Ordenados por bucket_hora ASC. Reintenta hasta 3 veces ante errores de red.
    """
    def _query():
        resp = (
            _supabase.table("mediciones_agregadas_horarias")
            .select("*")
            .eq("medidor_id", medidor_id)
            .gte("bucket_hora", desde)
            .lte("bucket_hora", hasta)
            .order("bucket_hora", desc=False)
            .limit(20000)
            .execute()
        )
        return resp.data or []

    return _ejecutar_con_reintentos(_query)


def obtener_ultimo_timestamp_cliente(cliente_id: int) -> "datetime | None":
    """Timestamp máximo en mediciones_tiempo_real para todos los medidores del cliente.

    Retorna None si el cliente no tiene mediciones.
    Usado como ancla temporal en modo demo (datos sintéticos sin re-seed continuo).
    DEUDA TÉCNICA: revertir a datetime.now() cuando entren medidores físicos con MQTT.
    """
    from datetime import timezone as _tz
    resp = (
        _supabase.table("medidores")
        .select("id")
        .eq("cliente_id", cliente_id)
        .limit(20000)
        .execute()
    )
    ids = [r["id"] for r in (resp.data or [])]
    if not ids:
        return None

    resp2 = (
        _supabase.table("mediciones_tiempo_real")
        .select("timestamp")
        .in_("medidor_id", ids)
        .order("timestamp", desc=True)
        .limit(1)
        .execute()
    )
    if not resp2.data:
        return None

    ts_str = resp2.data[0]["timestamp"]
    ts_naive = ts_str.replace("Z", "").split("+")[0].strip()
    return datetime.fromisoformat(ts_naive).replace(tzinfo=_tz.utc)


def crear_medidor_jerarquico(
    cliente_id: int,
    nombre: str,
    punto_medicion: str | None = None,
    medidor_padre_id: int | None = None,
    tipo_carga: str | None = None,
    potencia_nominal_kw: float | None = None,
    ubicacion: str | None = None,
    numero_serie: str | None = None,
    relacion_tc: str | None = None,
    marca: str = "Accuenergy",
    modelo: str = "Acuvim II",
) -> dict:
    """Inserta un medidor con campos jerárquicos. Coexiste con crear_medidor."""
    payload = {
        "cliente_id":         cliente_id,
        "nombre":             nombre,
        "punto_medicion":     punto_medicion,
        "medidor_padre_id":   medidor_padre_id,
        "tipo_carga":         tipo_carga,
        "potencia_nominal_kw": potencia_nominal_kw,
        "ubicacion":          ubicacion,
        "numero_serie":       numero_serie,
        "relacion_tc":        relacion_tc,
        "marca":              marca,
        "modelo":             modelo,
    }
    resp = _supabase.table("medidores").insert(payload).execute()
    return resp.data[0]


def obtener_arbol_medidores(cliente_id: int, planta_id: int | None = None) -> list[dict]:
    """Todos los medidores del cliente con limit(20000), orden estable por id.

    Si planta_id se provee, limita a los medidores de esa planta.
    """
    q = (
        _supabase.table("medidores")
        .select("*")
        .eq("cliente_id", cliente_id)
    )
    if planta_id is not None:
        q = q.eq("planta_id", planta_id)
    resp = q.order("id", desc=False).limit(20000).execute()
    return resp.data or []


def obtener_hijos(medidor_id: int) -> list[dict]:
    """Medidores con medidor_padre_id = medidor_id, limit(20000)."""
    resp = (
        _supabase.table("medidores")
        .select("*")
        .eq("medidor_padre_id", medidor_id)
        .order("id", desc=False)
        .limit(20000)
        .execute()
    )
    return resp.data or []


def obtener_descendientes_ids(medidor_id: int) -> list[int]:
    """IDs de todos los descendientes (recursivo en Python, máx 3 niveles)."""
    ids: list[int] = []
    hijos = obtener_hijos(medidor_id)
    for hijo in hijos:
        ids.append(hijo["id"])
        nietos = obtener_hijos(hijo["id"])
        for nieto in nietos:
            ids.append(nieto["id"])
            biznietos = obtener_hijos(nieto["id"])
            for biznieto in biznietos:
                ids.append(biznieto["id"])
    return ids


# ══════════════════════════════════════════════════════════════════════════════
# Modelado CHP — cache de resultados
# ══════════════════════════════════════════════════════════════════════════════

def get_cliente_chp_params(cliente_id: int) -> dict:
    """Retorna chp_num_motores, chp_margen_kw y chp_motores_config del cliente."""
    resp = (
        _supabase.table("clientes")
        .select("chp_num_motores, chp_margen_kw, chp_motores_config")
        .eq("id", cliente_id)
        .single()
        .execute()
    )
    if not resp.data:
        return {"num_motores": 1, "margen_kw": 0.0, "motores_config": None}
    row = resp.data
    return {
        "num_motores":    int(row["chp_num_motores"] or 1),
        "margen_kw":      float(row["chp_margen_kw"] or 0),
        "motores_config": row.get("chp_motores_config"),
    }


def update_cliente_chp_params(
    cliente_id: int,
    motores_config: list | None,
    margen_kw: float,
) -> None:
    """Actualiza chp_motores_config, chp_margen_kw (y chp_num_motores derivado) en clientes."""
    update_data: dict = {"chp_margen_kw": margen_kw}
    if motores_config is not None:
        update_data["chp_motores_config"] = motores_config
        update_data["chp_num_motores"] = len(motores_config)
    _supabase.table("clientes").update(update_data).eq("id", cliente_id).execute()


def get_chp_session_params(cliente_id: int) -> dict | None:
    """Retorna chp_session_params del cliente o None si vacío."""
    resp = (
        _supabase.table("clientes")
        .select("chp_session_params")
        .eq("id", cliente_id)
        .single()
        .execute()
    )
    return resp.data.get("chp_session_params") if resp.data else None


def save_chp_session_params(cliente_id: int, params: dict) -> None:
    """Guarda chp_session_params en el cliente."""
    _supabase.table("clientes") \
        .update({"chp_session_params": params}) \
        .eq("id", cliente_id) \
        .execute()


def get_modelado_chp_by_id(modelado_id: int) -> dict | None:
    """Retorna la cabecera del modelado por su PK. None si no existe."""
    resp = (
        _supabase.table("modelado_chp")
        .select("*")
        .eq("id", modelado_id)
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None


def get_modelado_chp(
    medicion_id: int,
    motores_config: list,
    margen_kw: float,
    rendimiento_electrico: float,
    costo_om_kwh: float,
    autoconsumo_pct: float,
) -> dict | None:
    """Busca un modelado con esos parámetros exactos en cache (por motores_config JSONB).
    Retorna el registro completo o None si no existe."""
    import json as _json
    resp = (
        _supabase.table("modelado_chp")
        .select("*")
        .eq("medicion_id", int(medicion_id))
        .eq("margen_kw", float(round(float(margen_kw), 2)))
        .eq("rendimiento_electrico", float(round(float(rendimiento_electrico), 4)))
        .eq("costo_om_kwh", float(round(float(costo_om_kwh), 6)))
        .eq("autoconsumo_pct", float(round(float(autoconsumo_pct), 4)))
        .eq("motores_config", _json.dumps(motores_config))
        .eq("calc_version", _MODELADO_CHP_VERSION)
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None


def save_modelado_chp(cliente_id: int, medicion_id: int, params: dict, kpis: dict) -> int | None:
    """Upsert de cabecera en modelado_chp. Retorna el id del registro.

    Usa upsert con on_conflict sobre columnas numéricas del índice único.
    Si PostgREST devuelve data vacía (conflicto silencioso), hace fallback
    a SELECT por medicion_id + calc_version para devolver el id existente.
    """
    motores_config      = params["motores_config"]
    capacidad_nominal_kw = sum(float(m.get("capacidad_kw", 0)) for m in motores_config)
    payload = {
        "cliente_id":            cliente_id,
        "medicion_id":           medicion_id,
        "motores_config":        motores_config,
        "num_motores":           len(motores_config),
        "capacidad_nominal_kw":  round(capacidad_nominal_kw, 2),
        "margen_kw":             params["margen_kw"],
        "rendimiento_electrico": params["rendimiento_electrico"],
        "costo_om_kwh":          params["costo_om_kwh"],
        "autoconsumo_pct":       params["autoconsumo_pct"],
        "gen_neta_anual_kwh":    kpis.get("gen_neta_anual_kwh"),
        "gen_bruta_anual_kwh":   kpis.get("gen_bruta_anual_kwh"),
        "cobertura_pct":         kpis.get("cobertura_pct"),
        "consumo_gas_anual_gj":  kpis.get("consumo_gas_anual_gj"),
        "costo_om_anual_mxn":    kpis.get("costo_om_anual_mxn"),
        "horas_anuales_motor":   kpis.get("horas_anuales_motor"),
        "capacidad_promedio_kw": kpis.get("capacidad_promedio_kw"),
        "calc_version":          _MODELADO_CHP_VERSION,
    }
    resp = (
        _supabase.table("modelado_chp")
        .upsert(payload, on_conflict="medicion_id,margen_kw,rendimiento_electrico,costo_om_kwh,autoconsumo_pct")
        .execute()
    )

    if resp.data:
        return resp.data[0]["id"]

    # Fallback: upsert ejecutado pero PostgREST no devolvió data (conflicto silencioso)
    busqueda = (
        _supabase.table("modelado_chp")
        .select("id")
        .eq("medicion_id", int(payload["medicion_id"]))
        .eq("calc_version", payload.get("calc_version", "1"))
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    if busqueda.data:
        return busqueda.data[0]["id"]

    raise RuntimeError("save_modelado_chp: no se pudo obtener el id del registro")


def save_modelado_chp_curva(modelado_id: int, curva: list[dict]) -> None:
    """Inserta la curva modelada en modelado_chp_curva en batches de 1,000.
    Incluye gen_por_motor JSONB con generación individual por motor."""
    BATCH = 1000
    rows = [
        {
            "modelado_id":     modelado_id,
            "ts":              p["ts"],
            "demanda_kw":      p["demanda_kw"],
            "gen_neta_kw":     p["gen_neta_kw"],
            "motores_activos": p["motores_activos"],
            "gen_por_motor":   {str(k): v for k, v in p["gen_por_motor"].items()}
                               if p.get("gen_por_motor") else None,
        }
        for p in curva
    ]
    for i in range(0, len(rows), BATCH):
        _supabase.table("modelado_chp_curva").insert(rows[i: i + BATCH]).execute()


def get_modelado_chp_curva(modelado_id: int) -> list[dict]:
    """Retorna todos los puntos de la curva modelada ordenados por ts ASC.
    Incluye gen_por_motor JSONB. Pagina de 1,000 en 1,000."""
    PAGE = 1000
    result = []
    start = 0
    while True:
        resp = (
            _supabase.table("modelado_chp_curva")
            .select("ts, demanda_kw, gen_neta_kw, motores_activos, gen_por_motor")
            .eq("modelado_id", modelado_id)
            .order("ts", desc=False)
            .range(start, start + PAGE - 1)
            .execute()
        )
        batch = resp.data or []
        result.extend(batch)
        if len(batch) < PAGE:
            break
        start += PAGE
    return result


# ── Usuario ↔ Cliente (N:N) ───────────────────────────────────────────────────

def get_clientes_de_usuario(user_id: str) -> list[dict]:
    """
    Retorna lista de clientes asignados a un usuario_normal vía usuario_clientes.
    Ordena por nombre ASC. Si no hay filas en usuario_clientes, hace fallback a
    empresa_id de user_profiles (compatibilidad legacy).
    Cada dict tiene al menos {id, nombre, ...campos básicos de clientes}.
    """
    try:
        res = _supabase.table("usuario_clientes").select("cliente_id").eq("user_id", user_id).execute()
        rows = res.data or []
        if rows:
            ids = [r["cliente_id"] for r in rows]
            clientes_res = (
                _supabase.table("clientes")
                .select("id, nombre, rfc, sector_industrial, tarifa_cfe")
                .in_("id", ids)
                .order("nombre", desc=False)
                .execute()
            )
            return clientes_res.data or []
        # Fallback legacy: leer empresa_id de user_profiles
        profile_res = (
            _supabase.table("user_profiles")
            .select("empresa_id")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        profile_rows = profile_res.data or []
        empresa_id = profile_rows[0].get("empresa_id") if profile_rows else None
        if not empresa_id:
            return []
        cli_res = (
            _supabase.table("clientes")
            .select("id, nombre, rfc, sector_industrial, tarifa_cfe")
            .eq("id", empresa_id)
            .execute()
        )
        return cli_res.data or []
    except Exception as exc:
        logger.error("Error en get_clientes_de_usuario user_id=%s: %s", user_id, exc)
        return []


def set_clientes_de_usuario(user_id: str, cliente_ids: list[int]) -> None:
    """
    Reemplaza la asignación completa de clientes para un usuario.
    Borra todas las filas existentes en usuario_clientes para ese user_id
    e inserta las nuevas. Si cliente_ids está vacío, solo borra.
    """
    _supabase.table("usuario_clientes").delete().eq("user_id", user_id).execute()
    if not cliente_ids:
        return
    rows = [{"user_id": user_id, "cliente_id": cid} for cid in cliente_ids]
    _supabase.table("usuario_clientes").insert(rows).execute()


def get_usuarios_de_cliente(cliente_id: int) -> list[dict]:
    """
    Retorna lista de usuario_normal asignados a un cliente.
    Cada dict: {user_id, email, nombre, apellido}.
    """
    try:
        res = (
            _supabase.table("usuario_clientes")
            .select("user_id, user_profiles(email, nombre, apellido)")
            .eq("cliente_id", cliente_id)
            .execute()
        )
        rows = res.data or []
        result = []
        for r in rows:
            profile = r.get("user_profiles") or {}
            result.append({
                "user_id": r["user_id"],
                "email": profile.get("email", ""),
                "nombre": profile.get("nombre"),
                "apellido": profile.get("apellido"),
            })
        return result
    except Exception as exc:
        logger.error("Error en get_usuarios_de_cliente cliente_id=%s: %s", cliente_id, exc)
        return []


# ── Fase 2 D3: lookup de facturas para costo en pesos en telemetría ────────────

def obtener_factura_cfe_cliente_mes(cliente_id: int, anio: int, mes: int) -> dict | None:
    """Factura CFE del cliente en (anio, mes) con cfe_periodos embebidos, o None."""
    resp = (
        _supabase.table("cfe_facturas")
        .select("*, cfe_periodos(*)")
        .eq("cliente_id", cliente_id)
        .eq("anio", anio)
        .eq("mes", mes)
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None


def obtener_ultimas_facturas_cfe(cliente_id: int, n: int = 12) -> list[dict]:
    """Últimas n facturas CFE del cliente con cfe_periodos, ordenadas DESC."""
    resp = (
        _supabase.table("cfe_facturas")
        .select("*, cfe_periodos(*)")
        .eq("cliente_id", cliente_id)
        .order("anio", desc=True)
        .order("mes", desc=True)
        .limit(n)
        .execute()
    )
    return resp.data or []


def obtener_factura_ppa_cliente_mes(cliente_id: int, anio: int, mes: int) -> dict | None:
    """Factura PPA del cliente en (anio, mes), o None."""
    resp = (
        _supabase.table("facturas_electricidad_calificado")
        .select("*")
        .eq("cliente_id", cliente_id)
        .eq("anio", anio)
        .eq("mes", mes)
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None


def obtener_ultimas_facturas_ppa(cliente_id: int, n: int = 12) -> list[dict]:
    """Últimas n facturas PPA del cliente, ordenadas DESC."""
    resp = (
        _supabase.table("facturas_electricidad_calificado")
        .select("*")
        .eq("cliente_id", cliente_id)
        .order("anio", desc=True)
        .order("mes", desc=True)
        .limit(n)
        .execute()
    )
    return resp.data or []


def obtener_produccion_diaria(
    cliente_id: int,
    desde_fecha: str,
    hasta_fecha: str,
) -> list[dict]:
    """Retorna registros de produccion_diaria para el cliente en el rango de fechas.

    desde_fecha, hasta_fecha: "YYYY-MM-DD" (ambos inclusivos).
    """
    resp = (
        _supabase.table("produccion_diaria")
        .select("fecha, m2_producidos")
        .eq("cliente_id", cliente_id)
        .gte("fecha", desde_fecha)
        .lte("fecha", hasta_fecha)
        .order("fecha")
        .limit(20000)
        .execute()
    )
    return resp.data or []


def upsert_produccion_mes(
    cliente_id: int,
    anio: int,
    mes: int,
    m2_mes: float,
) -> int:
    """Distribuye m2_mes entre los días del mes ponderando por tipo de día.

    Ponderación: L-V = 1.0, Sáb = 0.6, Dom = 0.0.
    Días con peso 0 (domingo) reciben m2 = 0.
    Retorna número de registros upserted.
    """
    import calendar
    from datetime import date

    n_dias = calendar.monthrange(anio, mes)[1]
    dias = [date(anio, mes, d) for d in range(1, n_dias + 1)]

    PESOS = {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 0.6, 6: 0.0}
    pesos = [PESOS[d.weekday()] for d in dias]
    total_peso = sum(pesos)

    if total_peso == 0:
        return 0

    registros = [
        {
            "cliente_id": cliente_id,
            "fecha": dia.isoformat(),
            "m2_producidos": round(m2_mes * peso / total_peso, 2),
        }
        for dia, peso in zip(dias, pesos)
    ]

    n = 0
    for inicio in range(0, len(registros), 100):
        lote = registros[inicio : inicio + 100]
        _supabase.table("produccion_diaria").upsert(
            lote, on_conflict="cliente_id,fecha"
        ).execute()
        n += len(lote)
    return n


def obtener_produccion_para_periodo(
    cliente_id: int,
    desde: datetime,
    hasta: datetime,
    usar_promedio_historico: bool = False,
) -> float:
    """Retorna m² producidos atribuibles al periodo [desde, hasta].

    Si usar_promedio_historico=True y no hay datos en el rango,
    calcula el promedio diario histórico (90 días previos) × días del rango.
    """
    from datetime import timedelta

    desde_str = desde.strftime("%Y-%m-%d")
    hasta_str = hasta.strftime("%Y-%m-%d")

    registros = obtener_produccion_diaria(cliente_id, desde_str, hasta_str)
    total = sum(float(r.get("m2_producidos") or 0) for r in registros)

    if total > 0 or not usar_promedio_historico:
        return total

    dias_rango = max(1, (hasta.date() - desde.date()).days + 1)
    limite_historico = (desde - timedelta(days=90)).strftime("%Y-%m-%d")
    historico = obtener_produccion_diaria(
        cliente_id,
        limite_historico,
        (desde - timedelta(days=1)).strftime("%Y-%m-%d"),
    )
    if not historico:
        return 0.0

    m2_dias = [float(r.get("m2_producidos") or 0) for r in historico]
    promedio_diario = sum(m2_dias) / len(m2_dias)
    return round(promedio_diario * dias_rango, 2)


def obtener_mediciones_para_rango(
    medidor_id: int,
    desde: str,
    hasta: str,
    rango: str,
) -> list[dict]:
    """Selecciona la fuente correcta según el rango y devuelve dicts homogeneizados.

    rango='24h': mediciones_agregadas_5min (bucket_5min → timestamp).
    rango='7d' o '30d': mediciones_agregadas_horarias (bucket_hora → timestamp).

    Campos del dict retornado:
      timestamp, potencia_activa_kw, factor_potencia, energia_activa_importada_kwh.
    """
    if rango == "24h":
        rows = obtener_agregados_5min(medidor_id, desde, hasta)
        return [
            {
                "timestamp": r["bucket_5min"],
                # Vista usa potencia_activa_promedio_kw (no potencia_activa_kw)
                "potencia_activa_kw": float(r.get("potencia_activa_promedio_kw") or 0),
                # Vista usa factor_potencia_promedio (no factor_potencia)
                "factor_potencia": float(r.get("factor_potencia_promedio") or 0),
                # Vista usa energia_importada_periodo_kwh (no energia_activa_importada_kwh)
                "energia_activa_importada_kwh": float(
                    r.get("energia_importada_periodo_kwh") or 0
                ),
            }
            for r in rows
        ]
    else:  # 7d, 30d
        rows = obtener_agregados_horarios(medidor_id, desde, hasta)
        return [
            {
                "timestamp": r["bucket_hora"],
                "potencia_activa_kw": float(r.get("potencia_activa_promedio_kw") or 0),
                "factor_potencia": float(r.get("factor_potencia_promedio") or 0),
                "energia_activa_importada_kwh": float(
                    r.get("energia_importada_periodo_kwh") or 0
                ),
            }
            for r in rows
        ]


# ── Plantas ────────────────────────────────────────────────────────────────────

def obtener_plantas_por_cliente(cliente_id: int, solo_activas: bool = True) -> list[dict]:
    """Devuelve plantas del cliente ordenadas por nombre.
    Por defecto solo activas; con solo_activas=False devuelve todas.
    """
    q = _supabase.table("plantas").select("*").eq("cliente_id", cliente_id)
    if solo_activas:
        q = q.eq("activo", True)
    return q.order("nombre").execute().data or []


def obtener_planta(planta_id: int) -> dict | None:
    """Devuelve una planta por id, o None si no existe."""
    r = _supabase.table("plantas").select("*").eq("id", planta_id).execute()
    return r.data[0] if r.data else None


def crear_planta(
    cliente_id: int,
    nombre: str,
    *,
    direccion_planta: str | None = None,
    notas: str | None = None,
) -> dict:
    """Inserta una planta y retorna el registro creado."""
    payload = {"cliente_id": cliente_id, "nombre": nombre}
    if direccion_planta:
        payload["direccion_planta"] = direccion_planta
    if notas:
        payload["notas"] = notas
    r = _supabase.table("plantas").insert(payload).execute()
    return r.data[0]


def actualizar_planta(planta_id: int, **campos) -> dict:
    """Actualiza campos permitidos de la planta y retorna el registro actualizado."""
    _CAMPOS_PERMITIDOS = {"nombre", "direccion_planta", "notas", "activo"}
    payload = {k: v for k, v in campos.items() if k in _CAMPOS_PERMITIDOS}
    if not payload:
        raise ValueError("Sin campos válidos para actualizar.")
    r = _supabase.table("plantas").update(payload).eq("id", planta_id).execute()
    return r.data[0]


def planta_tiene_recursos(planta_id: int) -> dict:
    """Verifica si la planta tiene recursos vinculados.

    Retorna dict vacío si no hay recursos, o dict con conteos por categoría:
    {"contratos": N, "medidores": N, "facturas_cfe": N, "facturas_gas": N}
    """
    conteos: dict[str, int] = {}
    for tabla, label in [
        ("contratos", "contratos"),
        ("medidores", "medidores"),
        ("cfe_facturas", "facturas_cfe"),
        ("gas_facturas", "facturas_gas"),
    ]:
        try:
            r = _supabase.table(tabla).select("id", count="exact").eq("planta_id", planta_id).execute()
            n = r.count or 0
            if n:
                conteos[label] = n
        except Exception:
            pass
    return conteos


def get_contratos_por_planta(planta_id: int) -> list[Contrato]:
    """Devuelve contratos de una planta específica, ordenados por nombre."""
    r = _supabase.table("contratos").select("*").eq("planta_id", planta_id).order("nombre").execute()
    return [_row_to_contrato(row) for row in r.data]
