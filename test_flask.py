from flask import Flask
app = Flask(__name__)

@app.route('/')
def ok():
    return 'OK'

print('Arrancando en http://127.0.0.1:8080/')
app.run(host='127.0.0.1', port=8080, use_reloader=False)
