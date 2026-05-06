import sys
import traceback

try:
    print("Importando Flask...")
    from flask import Flask
    print("OK")

    print("Importando web.app...")
    from web.app import create_app
    print("OK")

    print("Creando app...")
    app = create_app("invoices")
    print("OK")

    print("Arrancando servidor en http://127.0.0.1:9090/ ...")
    app.run(host="127.0.0.1", port=9090, debug=False, use_reloader=False)

except Exception as e:
    print(f"\nERROR: {e}")
    traceback.print_exc()
    sys.exit(1)
