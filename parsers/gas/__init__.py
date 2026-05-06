from __future__ import annotations

from parsers.gas.engie import ENGIEParser


def get_gas_parser() -> ENGIEParser:
    """Devuelve el parser para facturas de gas ENGIE/GDF Suez."""
    return ENGIEParser()
