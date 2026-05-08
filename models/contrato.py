# models/contrato.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Contrato:
    id: int
    cliente_id: int
    nombre: str
    tipo: str          # "electrico" | "gas"
    identificador_real: str
    notas: str | None
    created_at: str | None
