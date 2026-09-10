from __future__ import annotations

"""
Registro global de parsers de facturas de electricidad calificada.

Uso:
    from parsers.registry import registry

    # Auto-detectar el parser adecuado para un PDF:
    parser_class = registry.auto_detect(pdf_path)
    if parser_class:
        resultado = parser_class().parse(pdf_path)

    # Listar todos los parsers registrados:
    for entrada in registry.todos():
        print(entrada.clave, entrada.nombre)

    # Obtener parser por clave:
    entrada = registry.get("GIN_A")

Añadir un nuevo parser:
    1. Crear el módulo en parsers/electricidad_calificado/<nombre>.py
    2. Añadir una llamada registry.registrar(...) en _registrar_parsers() al final de este archivo.
    3. Definir una 'firma' regex que aparezca exclusivamente en ese formato de PDF.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Type

import pdfplumber

from parsers.base import InvoiceParser


@dataclass(frozen=True)
class ParserEntry:
    clave: str          # Identificador único,  e.g. "GIN_A"
    nombre: str         # Nombre legible
    proveedor: str      # Razón social del emisor
    rfc_emisor: str     # RFC del suministrador
    descripcion: str    # Descripción breve del formato
    parser_class: Type[InvoiceParser]
    firma: str          # Patrón regex que identifica este formato de forma única en el texto


def _extraer_texto(pdf_path: Path) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


class ParserRegistry:
    def __init__(self) -> None:
        self._entries: list[ParserEntry] = []

    def registrar(self, entry: ParserEntry) -> None:
        self._entries.append(entry)

    def todos(self) -> list[ParserEntry]:
        """Devuelve todas las entradas en orden de registro."""
        return list(self._entries)

    def get(self, clave: str) -> ParserEntry | None:
        """Busca una entrada por clave exacta."""
        return next((e for e in self._entries if e.clave == clave), None)

    def auto_detect(self, pdf_path: Path) -> Type[InvoiceParser] | None:
        """
        Extrae el texto del PDF y devuelve la clase del primer parser cuya
        firma hace match. Devuelve None si ninguno reconoce el formato.
        """
        texto = _extraer_texto(Path(pdf_path))
        for entry in self._entries:
            if re.search(entry.firma, texto, re.IGNORECASE | re.MULTILINE):
                return entry.parser_class
        return None


# ── Instancia global ──────────────────────────────────────────────────────────
registry = ParserRegistry()


def _registrar_parsers() -> None:
    """
    Registro canónico de todos los parsers disponibles.
    Las importaciones son locales para evitar dependencias circulares.

    Parsers registrados:
    ┌──────────────┬────────────────────────────────────────────────────────────┐
    │ Clave        │ Descripción                                                │
    ├──────────────┼────────────────────────────────────────────────────────────┤
    │ GIN_A        │ GIN formato original (2024). "Serie - Folio GI01 NNNNN".   │
    │              │ Periodo en texto español. Incluye RPU.                     │
    ├──────────────┼────────────────────────────────────────────────────────────┤
    │ GIN_GIF      │ GIN formato GIF (2025). "SERIE: GIF / FOLIO: NNNN".        │
    │              │ Periodo en fechas ISO. Sin RPU. Importes con $.            │
    └──────────────┴────────────────────────────────────────────────────────────┘
    """
    from parsers.electricidad_calificado.gin import GINParser
    from parsers.electricidad_calificado.gin_gif import GINGIFParser

    registry.registrar(ParserEntry(
        clave="GIN_A",
        nombre="GIN — Formato A (Serie-Folio, periodo en español)",
        proveedor="GENERACION INDUSTRIAL",
        rfc_emisor="GIN040707G89",
        descripcion="Facturas 2024. Etiqueta 'Serie - Folio GI01 NNNNN'. Periodo en texto español. Con RPU.",
        parser_class=GINParser,
        firma=r"Serie\s*-\s*Folio\s+[A-Z]{2,4}\d{2}[-\s]\d{4,}",
    ))

    registry.registrar(ParserEntry(
        clave="GIN_GIF",
        nombre="GIN — Formato GIF (SERIE/FOLIO separados, periodo ISO)",
        proveedor="GENERACION INDUSTRIAL",
        rfc_emisor="GIN040707G89",
        descripcion="Facturas 2025. 'SERIE: GIF / FOLIO: NNNN'. Periodo en fechas ISO. Sin RPU.",
        parser_class=GINGIFParser,
        firma=r"Periodo de facturaci[oó]n:\s*del\s+\d{4}-\d{2}-\d{2}\s+al\s+\d{4}-\d{2}-\d{2}",
    ))


_registrar_parsers()
