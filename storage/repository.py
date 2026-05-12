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
from models.contrato import Contrato
from calc.nombre_canonico import generar_nombre_canonico
from calc.periodo import mes_asociado as _mes_asociado

logger = logging.getLogger(__name__)

_supabase: Client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_KEY"],
)


# ── Clientes ──────────────────────────────────────────────────────────────────

# ── CFE invoices ──────────────────────────────────────────────────────────────

def save_cfe_invoice(invoice: CFEInvoice, cliente_id: int, contrato_id: int | None = None) -> tuple[int, str]:
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
    "medio_termico, nivel_tension_kv, altitud_msnm, tipo_motor"
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
        "nivel_tension_kv": row.get("nivel_tension_kv"),
        "altitud_msnm": row.get("altitud_msnm"),
        "tipo_motor": row.get("tipo_motor"),
        "num_cfe": len(row.get("cfe_facturas") or []),
        "num_gas": len(row.get("gas_facturas") or []),
    }


def get_all_clientes_con_conteos() -> list[dict]:
    """Devuelve todos los clientes con conteo de facturas CFE y gas. Ordenados por nombre."""
    result = _supabase.table("clientes").select(
        f"id, nombre, rfc, notas, created_at, logo_url, cfe_facturas(id), gas_facturas(id)"
    ).order("nombre").execute()
    return [_row_to_cliente_dict(row) for row in result.data]


def get_cliente_con_conteos(cliente_id: int) -> dict | None:
    """Devuelve un cliente con todos sus campos y conteo de facturas, o None si no existe."""
    result = _supabase.table("clientes").select(
        f"id, nombre, rfc, notas, created_at, {_CLIENTE_CAMPOS_EXTENDIDOS}, "
        "cfe_facturas(id), gas_facturas(id)"
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
    )


def get_contrato_con_conteos(contrato_id: int) -> dict | None:
    """Devuelve un contrato con conteo de facturas CFE y gas asociadas, o None si no existe."""
    result = _supabase.table("contratos").select("*").eq("id", contrato_id).execute()
    if not result.data:
        return None
    row = result.data[0]
    cfe = _supabase.table("cfe_facturas").select("id").eq("contrato_id", contrato_id).execute()
    gas = _supabase.table("gas_facturas").select("id").eq("contrato_id", contrato_id).execute()
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
    }


def get_contratos_por_cliente(cliente_id: int) -> list[Contrato]:
    """Devuelve todos los contratos del cliente, ordenados por nombre."""
    result = _supabase.table("contratos").select("*").eq(
        "cliente_id", cliente_id
    ).order("nombre").execute()
    return [_row_to_contrato(r) for r in result.data]


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
) -> int:
    """Crea un contrato. Devuelve el id asignado.
    Lanza ContratoIdentificadorDuplicado si (cliente_id, identificador_real) ya existe."""
    try:
        result = _supabase.table("contratos").insert({
            "cliente_id": cliente_id,
            "nombre": nombre,
            "tipo": tipo,
            "identificador_real": identificador_real,
            "notas": notas if notas else None,
        }).execute()
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
) -> None:
    """Actualiza los campos del contrato.
    Lanza ContratoIdentificadorDuplicado si el nuevo identificador_real ya existe para el cliente."""
    try:
        _supabase.table("contratos").update({
            "nombre": nombre,
            "tipo": tipo,
            "identificador_real": identificador_real,
            "notas": notas if notas else None,
        }).eq("id", contrato_id).execute()
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


def get_meses_con_factura(contrato_id: int, anio: int) -> set[int]:
    """Retorna conjunto de meses (1-12) con al menos una factura en ese contrato/año."""
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


def upsert_meses_seleccionados_anio(contrato_id: int, anio: int) -> int:
    """Selecciona todos los meses con factura del año. Retorna cantidad insertada."""
    meses = get_meses_con_factura(contrato_id, anio)
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


def get_sidebar_data_contrato(contrato_id: int) -> list[dict]:
    """Retorna datos completos del sidebar para un contrato: años con facturas y selección.

    Cada elemento: {"anio": int, "meses_con_factura": [int], "meses_seleccionados": [int]}
    Ordenado por año descendente (más reciente primero).

    Usa exactamente 3 queries fijas (CFE, gas, seleccionados), sin N+1.
    """
    from collections import defaultdict

    # Query 1: todos los (anio, mes) con factura CFE para este contrato
    cfe = _supabase.table("cfe_facturas").select("anio, mes").eq(
        "contrato_id", contrato_id
    ).not_.is_("anio", "null").not_.is_("mes", "null").execute()

    # Query 2: todos los (anio, mes) con factura de gas para este contrato
    gas = _supabase.table("gas_facturas").select("anio, mes").eq(
        "contrato_id", contrato_id
    ).not_.is_("anio", "null").not_.is_("mes", "null").execute()

    # Query 3: meses seleccionados
    sel_result = _supabase.table("contrato_meses_seleccionados").select("anio, mes").eq(
        "contrato_id", contrato_id
    ).execute()

    # Agrupar meses con factura por año
    meses_por_anio: dict[int, set[int]] = defaultdict(set)
    for r in cfe.data:
        meses_por_anio[r["anio"]].add(r["mes"])
    for r in gas.data:
        meses_por_anio[r["anio"]].add(r["mes"])

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


def get_cfe_invoices_for_dashboard(cliente_id: int) -> list[CFEInvoice]:
    """Carga facturas CFE del cliente cuyos meses están seleccionados en contrato_meses_seleccionados."""
    seleccionados = get_meses_seleccionados_por_cliente(cliente_id)
    if not seleccionados:
        return []
    contrato_ids = list({c for c, _, _ in seleccionados})
    result = _supabase.table("cfe_facturas").select(
        "*, clientes(nombre, rfc), cfe_periodos(*), cfe_mem_componentes(*)"
    ).eq("cliente_id", cliente_id).in_("contrato_id", contrato_ids).order("periodo_inicio").execute()
    return [
        _row_to_cfe_invoice(row) for row in result.data
        if row.get("anio") and row.get("mes")
        and (row["contrato_id"], row["anio"], row["mes"]) in seleccionados
    ]


def get_gas_invoices_for_dashboard(cliente_id: int) -> list[GasInvoice]:
    """Carga facturas de gas del cliente cuyos meses están seleccionados en contrato_meses_seleccionados."""
    seleccionados = get_meses_seleccionados_por_cliente(cliente_id)
    if not seleccionados:
        return []
    contrato_ids = list({c for c, _, _ in seleccionados})
    result = _supabase.table("gas_facturas").select(
        "*, clientes(nombre, rfc), gas_conceptos(*)"
    ).eq("cliente_id", cliente_id).in_("contrato_id", contrato_ids).order("periodo_inicio").execute()
    return [
        _row_to_gas_invoice(row) for row in result.data
        if row.get("anio") and row.get("mes")
        and (row["contrato_id"], row["anio"], row["mes"]) in seleccionados
    ]


def delete_cfe_factura(factura_id: int) -> None:
    """Borra una factura CFE (ON DELETE CASCADE elimina periodos y componentes)."""
    _supabase.table("cfe_facturas").delete().eq("id", factura_id).execute()


def delete_gas_factura(factura_id: int) -> None:
    """Borra una factura de gas (ON DELETE CASCADE elimina conceptos)."""
    _supabase.table("gas_facturas").delete().eq("id", factura_id).execute()


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
