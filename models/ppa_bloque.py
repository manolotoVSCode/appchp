# models/ppa_bloque.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class PPABloqueMensual:
    id: int
    cliente_id: int
    anio: int
    mes: int
    bloque_contratado_mwh: Decimal
    created_at: datetime | None = None
