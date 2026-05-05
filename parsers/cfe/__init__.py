from __future__ import annotations

from parsers.cfe.gdmth import GDMTHParser
from parsers.cfe.base import CFEParser


def get_cfe_parser(tarifa: str) -> CFEParser:
    parsers = {
        "GDMTH": GDMTHParser,
    }
    if tarifa not in parsers:
        raise ValueError(
            f"Tarifa CFE no soportada: '{tarifa}'. Disponibles: {list(parsers.keys())}"
        )
    return parsers[tarifa]()
