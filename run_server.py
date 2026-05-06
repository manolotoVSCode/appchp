# run_server.py
"""Punto de entrada para el servidor de desarrollo.

Uso:
    python3 run_server.py
    python3 run_server.py --port 8080
    python3 run_server.py --invoices /ruta/a/invoices
"""
from __future__ import annotations

import argparse
from web.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Dashboard de Cogeneración")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--invoices", default="invoices", help="Directorio con PDFs")
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    print(f"Cargando facturas desde '{args.invoices}'...")
    app = create_app(args.invoices)
    print(f"Servidor listo → http://{args.host}:{args.port}/")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
