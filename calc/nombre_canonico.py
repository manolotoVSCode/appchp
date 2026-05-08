# calc/nombre_canonico.py
from __future__ import annotations

import unicodedata
from datetime import date

from models.cfe_invoice import CFEInvoice
from models.gas_invoice import GasInvoice
from calc.periodo import mes_asociado

_MESES = {
    1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL",
    5: "MAYO", 6: "JUNIO", 7: "JULIO", 8: "AGOSTO",
    9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE",
}


def _normalizar_proveedor(texto: str) -> str:
    """Elimina acentos y convierte a mayúsculas. Conserva espacios internos."""
    nfkd = unicodedata.normalize("NFD", texto)
    sin_acentos = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    return sin_acentos.upper().strip()


def _nombre_cfe(año: int, mes: int, numero_servicio: str | None) -> str:
    ns = (numero_servicio or "").strip()
    identificador = f"CFE {ns}" if ns else "CFE SIN_SERVICIO"
    return f"{año} {_MESES[mes]} {identificador}"


def _nombre_gas(año: int, mes: int, nombre_proveedor: str | None) -> str:
    raw = (nombre_proveedor or "").strip()
    proveedor = _normalizar_proveedor(raw) if raw else "GAS"
    return f"{año} {_MESES[mes]} {proveedor}"


def generar_nombre_canonico(factura: CFEInvoice | GasInvoice) -> str:
    """Devuelve el nombre canónico de una factura CFE o gas.

    Formato CFE : "YYYY MES CFE NUMERO_SERVICIO"
    Formato gas : "YYYY MES PROVEEDOR"

    El mes corresponde al mes asociado según la regla de mayoría de días.
    """
    año, mes = mes_asociado(factura.periodo_inicio, factura.periodo_fin)
    if isinstance(factura, CFEInvoice):
        return _nombre_cfe(año, mes, factura.numero_servicio)
    return _nombre_gas(año, mes, factura.nombre_proveedor)


def generar_nombre_canonico_raw(
    periodo_inicio: date,
    periodo_fin: date,
    tipo: str,
    numero_servicio: str | None = None,
    nombre_proveedor: str | None = None,
) -> str:
    """Versión sin objeto de dominio, para uso en migraciones y scripts.

    tipo: "cfe" | "gas"
    """
    año, mes = mes_asociado(periodo_inicio, periodo_fin)
    if tipo == "cfe":
        return _nombre_cfe(año, mes, numero_servicio)
    return _nombre_gas(año, mes, nombre_proveedor)
