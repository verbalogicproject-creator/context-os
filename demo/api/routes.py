from api.store import Store

def register(app, store: Store):
    app["/items"] = lambda: store.all()
    app["/items/add"] = lambda name: store.add(name)
