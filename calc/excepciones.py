# calc/excepciones.py
from __future__ import annotations


class PeriodoIncompletoError(ValueError):
    """Se lanza cuando periodo_inicio o periodo_fin son None o el período es inválido."""
