"""Tests unitarios para el filtro abreviar_con_cliente."""
import unicodedata
import pytest


def _abreviar_con_cliente(nombre_contrato: str, nombre_cliente: str) -> str:
    """Replica exacta de la función registrada en app.py."""
    ARTICULOS = {"de", "del", "la", "los", "las", "y"}
    iniciales = "".join(
        p[0].upper() for p in nombre_cliente.split()
        if p.lower() not in ARTICULOS and p
    )

    def _norm(s: str) -> str:
        return "".join(
            c for c in unicodedata.normalize("NFKD", s.lower())
            if unicodedata.category(c) != "Mn"
        )

    if _norm(nombre_contrato).startswith(_norm(nombre_cliente)):
        return iniciales + nombre_contrato[len(nombre_cliente):]
    return nombre_contrato


@pytest.mark.parametrize("contrato, cliente, esperado", [
    (
        "IBÉRICA TILES Planta 1",
        "IBÉRICA TILES",
        "IT Planta 1",
    ),
    (
        "IBÉRICA TILES Planta 2",
        "IBÉRICA TILES",
        "IT Planta 2",
    ),
    (
        "Iberica Tiles Planta 3",
        "IBÉRICA TILES",
        "IT Planta 3",
    ),
    (
        "Otro Contrato",
        "IBÉRICA TILES",
        "Otro Contrato",
    ),
    (
        "GRUPO INDUSTRIAL DEL NORTE Sede A",
        "GRUPO INDUSTRIAL DEL NORTE",
        "GIN Sede A",
    ),
])
def test_abreviar_con_cliente(contrato, cliente, esperado):
    assert _abreviar_con_cliente(contrato, cliente) == esperado
