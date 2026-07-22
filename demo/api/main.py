from api.store import Store
from api.routes import register

store = Store()

def create_app():
    app = {}
    register(app, store)
    return app
