# run_server.py
"""Punto de entrada para el servidor de desarrollo.

Uso:
    python3 run_server.py                          # parsea PDFs en memoria
    python3 run_server.py --db chpapp.db           # crea/reutiliza DB en disco
    python3 run_server.py --db chpapp.db --port 8080
"""
from __future__ import annotations

import argparse
from web.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Dashboard de Cogeneración")
    parser.add_argument("--port", type=int, default=9090)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--invoices", default="invoices", help="Directorio con PDFs")
    parser.add_argument("--db", default=None, help="Ruta SQLite (crea si no existe)")
    args = parser.parse_args()

    app = create_app(invoices_dir=args.invoices, db_path=args.db)
    msg = f"desde DB '{args.db}'" if args.db else "parseando PDFs"
    print(f"Servidor → http://{args.host}:{args.port}/  (cargando {msg}...)")
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
