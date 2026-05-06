from __future__ import annotations

import json
import sqlite3
from datetime import date
from decimal import Decimal
from typing import Any

from models.cfe_invoice import CFEInvoice, CFEConsumoHorario, MEMComponente
from models.gas_invoice import GasInvoice


def _upsert_cliente(conn: Any, nombre: str, rfc: str) -> int:
    """Inserta o reutiliza el cliente por RFC. Devuelve su id."""
    row = conn.execute("SELECT id FROM clientes WHERE rfc = ?", (rfc,)).fetchone()
    if row:
        return row["id"] if isinstance(row, dict) else row[0]
    cur = conn.execute(
        "INSERT INTO clientes (nombre, rfc) VALUES (?, ?) RETURNING id",
        (nombre, rfc),
    )
    cur.fetchall()  # drain cursor so commit() can proceed on raw sqlite3
    conn.commit()
    return cur.lastrowid


def save_cfe_invoice(conn: Any, invoice: CFEInvoice) -> int:
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
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        RETURNING id
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
    cur.fetchall()  # drain RETURNING cursor so commit() can proceed on raw sqlite3

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


def load_cfe_invoice(conn: Any, factura_id: int) -> CFEInvoice:
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


def list_cfe_invoices(conn: Any) -> list[dict]:
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


# ── Gas invoices ─────────────────────────────────────────────────────────────

def save_gas_invoice(conn: Any, invoice) -> int:
    """Persiste una GasInvoice completa. Devuelve el id de gas_facturas."""
    cliente_id = _upsert_cliente(conn, invoice.nombre_cliente, invoice.rfc_cliente)
    cur = conn.execute(
        """INSERT INTO gas_facturas (
            cliente_id, uuid_cfdi, folio, fecha_emision, periodo_inicio, periodo_fin,
            fecha_limite_pago, nombre_proveedor, rfc_proveedor, numero_cliente,
            cuenta_contrato, punto_suministro, numero_caseta, tipo_lectura,
            consumo_m3_corregidos, consumo_sin_corregir_m3, poder_calorifico_gj_m3,
            consumo_total_gj, costo_unitario_total_gj,
            subtotal_mxn, iva_mxn, total_mxn, pdf_path, advertencias
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id""",
        (
            cliente_id,
            invoice.uuid_cfdi,
            invoice.folio,
            invoice.fecha_emision.isoformat(),
            invoice.periodo_inicio.isoformat(),
            invoice.periodo_fin.isoformat(),
            invoice.fecha_limite_pago.isoformat(),
            invoice.nombre_proveedor,
            invoice.rfc_proveedor,
            invoice.numero_cliente,
            invoice.cuenta_contrato,
            invoice.punto_suministro,
            invoice.numero_caseta,
            invoice.tipo_lectura,
            str(invoice.consumo_m3_corregidos),
            str(invoice.consumo_sin_corregir_m3),
            str(invoice.poder_calorifico_gj_m3),
            str(invoice.consumo_total_gj),
            str(invoice.costo_unitario_total_gj),
            str(invoice.subtotal_mxn),
            str(invoice.iva_mxn),
            str(invoice.total_mxn),
            invoice.pdf_path,
            json.dumps(invoice.advertencias),
        ),
    )
    factura_id = cur.lastrowid
    cur.fetchall()  # drain RETURNING cursor so commit() can proceed on raw sqlite3
    conn.commit()

    for c in invoice.conceptos:
        conn.execute(
            """INSERT INTO gas_conceptos
               (factura_id, descripcion, clave_producto, cantidad_gj, precio_unitario_gj, importe_mxn)
               VALUES (?,?,?,?,?,?)""",
            (
                factura_id,
                c.descripcion,
                c.clave_producto,
                str(c.cantidad_gj),
                str(c.precio_unitario_gj),
                str(c.importe_mxn),
            ),
        )
    conn.commit()
    return factura_id


def load_gas_invoice(conn: Any, factura_id: int) -> GasInvoice:
    """Carga una GasInvoice completa desde SQLite. Lanza ValueError si no existe."""
    from models.gas_invoice import GasConcepto, GasInvoice as _GI

    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM gas_facturas WHERE id = ?", (factura_id,)
    ).fetchone()

    if row is None:
        conn.row_factory = None
        raise ValueError(f"Factura de gas con id={factura_id} no encontrada")

    conceptos_rows = conn.execute(
        "SELECT * FROM gas_conceptos WHERE factura_id = ? ORDER BY id", (factura_id,)
    ).fetchall()
    conn.row_factory = None

    conceptos = [
        GasConcepto(
            descripcion=c["descripcion"],
            clave_producto=c["clave_producto"],
            cantidad_gj=Decimal(c["cantidad_gj"]),
            precio_unitario_gj=Decimal(c["precio_unitario_gj"]),
            importe_mxn=Decimal(c["importe_mxn"]),
        )
        for c in conceptos_rows
    ]

    return _GI(
        uuid_cfdi=row["uuid_cfdi"] or "",
        folio=row["folio"],
        fecha_emision=date.fromisoformat(row["fecha_emision"]),
        periodo_inicio=date.fromisoformat(row["periodo_inicio"]),
        periodo_fin=date.fromisoformat(row["periodo_fin"]),
        fecha_limite_pago=date.fromisoformat(row["fecha_limite_pago"]),
        nombre_proveedor=row["nombre_proveedor"],
        rfc_proveedor=row["rfc_proveedor"],
        nombre_cliente="",
        rfc_cliente="",
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
        pdf_path=row["pdf_path"],
        advertencias=json.loads(row["advertencias"]),
    )


def list_gas_invoices(conn: Any) -> list[dict]:
    """Devuelve resumen de todas las facturas de gas guardadas."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT gf.id, gf.folio, gf.periodo_inicio, gf.periodo_fin,
                  gf.consumo_total_gj, gf.total_mxn, c.rfc AS rfc_cliente
           FROM gas_facturas gf
           JOIN clientes c ON c.id = gf.cliente_id
           ORDER BY gf.periodo_inicio"""
    ).fetchall()
    conn.row_factory = None
    return [dict(r) for r in rows]
