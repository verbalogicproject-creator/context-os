class Store:
    def __init__(self):
        self._items = []
    def all(self):
        return list(self._items)
    def add(self, name):
        self._items.append(name)
        return name
