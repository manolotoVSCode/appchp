from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class InvoiceParser(ABC):
    """Protocolo común para todos los parsers del sistema."""

    @abstractmethod
    def parse(self, pdf_path: Path) -> object:
        """Parsea un PDF y devuelve el objeto de dominio correspondiente."""
        ...
