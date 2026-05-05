from __future__ import annotations

import pytest
from pathlib import Path
from parsers.base import InvoiceParser
from parsers.cfe.base import CFEParser


def test_invoice_parser_es_abstracto():
    with pytest.raises(TypeError):
        InvoiceParser()


def test_cfe_parser_es_abstracto():
    with pytest.raises(TypeError):
        CFEParser()


def test_cfe_parser_subclase_debe_implementar_parse():
    class Incompleto(CFEParser):
        pass  # no implementa parse()

    with pytest.raises(TypeError):
        Incompleto()


def test_cfe_parser_subclase_completa_puede_instanciarse():
    from models.cfe_invoice import CFEInvoice

    class Completo(CFEParser):
        def parse(self, pdf_path: Path) -> CFEInvoice:
            raise NotImplementedError

    parser = Completo()
    assert isinstance(parser, CFEParser)
    assert isinstance(parser, InvoiceParser)
