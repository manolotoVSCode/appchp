# models/contrato.py
from __future__ import annotations

from dataclasses import dataclass

TIPO_ELECTRICO_BASICO     = 'electrico_basico'
TIPO_ELECTRICO_CALIFICADO = 'electrico_calificado'
TIPO_GAS                  = 'gas'

TIPOS_ELECTRICOS = (TIPO_ELECTRICO_BASICO, TIPO_ELECTRICO_CALIFICADO)
TIPOS_VALIDOS    = (TIPO_ELECTRICO_BASICO, TIPO_ELECTRICO_CALIFICADO, TIPO_GAS)


@dataclass
class Contrato:
    id: int
    cliente_id: int
    nombre: str
    tipo: str          # 'electrico_basico' | 'electrico_calificado' | 'gas'
    identificador_real: str
    notas: str | None
    created_at: str | None
    planta_id: int | None = None
