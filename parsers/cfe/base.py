from __future__ import annotations

from abc import abstractmethod
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

from models.cfe_invoice import CFEInvoice
from parsers.base import InvoiceParser

# Mapeo de abreviaturas de mes en español a número
MESES_ES = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4,
    "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8,
    "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
}


class CFEParser(InvoiceParser):
    """Base para todos los parsers de facturas CFE.

    Provee helpers compartidos (parseo de fechas, números) y validate().
    Las subclases implementan parse() según la tarifa específica.
    """

    @abstractmethod
    def parse(self, pdf_path: Path) -> CFEInvoice:
        ...

    def validate(self, invoice: CFEInvoice) -> list[str]:
        """Valida coherencia interna. Devuelve lista de errores (vacía = válido)."""
        errores = []

        # Validación de periodos: deben existir los tres para GDMTH
        nombres = {p.periodo for p in invoice.periodos}
        for esperado in ("base", "intermedio", "punta"):
            if esperado not in nombres:
                errores.append(f"Periodo '{esperado}' no encontrado en la factura")

        # Periodo temporal coherente
        if invoice.periodo_fin <= invoice.periodo_inicio:
            errores.append("periodo_fin debe ser posterior a periodo_inicio")

        # Total = subtotal + IVA + DAP + crédito (tolerancia de 1 peso)
        total_calculado = (
            invoice.subtotal_mxn
            + invoice.iva_mxn
            + invoice.derecho_alumbrado_publico_mxn
            + invoice.credito_aplicado_mxn  # ya es negativo
        )
        diferencia = abs(total_calculado - invoice.total_mxn)
        if diferencia > Decimal("1.00"):
            errores.append(
                f"Total no cuadra: calculado={total_calculado}, factura={invoice.total_mxn}, "
                f"diferencia={diferencia}"
            )

        return errores

    @staticmethod
    def _parse_fecha_es(texto: str) -> date:
        """Convierte '07 NOV 23' o '07 NOV 2023' a date."""
        partes = texto.strip().split()
        if len(partes) != 3:
            raise ValueError(f"Formato de fecha no reconocido: '{texto}'")
        dia = int(partes[0])
        mes = MESES_ES.get(partes[1].upper())
        if mes is None:
            raise ValueError(f"Mes no reconocido: '{partes[1]}'")
        anio = int(partes[2])
        if anio < 100:
            anio += 2000
        return date(anio, mes, dia)

    @staticmethod
    def _parse_decimal(texto: str) -> Decimal:
        """Convierte '1,126,771.85' o '94100.81' a Decimal."""
        limpio = texto.strip().replace(",", "").replace(" ", "")
        try:
            return Decimal(limpio)
        except InvalidOperation:
            raise ValueError(f"No se puede convertir a Decimal: '{texto}'")
