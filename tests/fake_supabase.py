"""
A minimal in-memory stand-in for supabase.Client, implementing just
enough of the chainable query-builder API (`.table().select().eq()
.order().limit().insert().delete().execute()`, plus `.rpc()`) for
shortener/repository.py to run against it without hitting a real
Supabase project or the network.

Not a general-purpose PostgREST mock — only the operations this repo
actually issues are supported.
"""


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self._op = None
        self._filters = []
        self._order = []
        self._limit = None
        self._payload = None

    def select(self, *_args, **_kwargs):
        self._op = self._op or "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def order(self, column, desc=False):
        self._order.append((column, desc))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _matches(self, row):
        return all(row.get(col) == val for col, val in self._filters)

    def execute(self):
        rows = self.client.tables[self.table_name]

        if self._op == "insert":
            self.client._seq[self.table_name] += 1
            new_row = dict(self._payload)
            new_row["id"] = self.client._seq[self.table_name]
            rows.append(new_row)
            return FakeResult([dict(new_row)])

        if self._op == "delete":
            matched = [r for r in rows if self._matches(r)]
            for r in matched:
                rows.remove(r)
            return FakeResult([dict(r) for r in matched])

        # select
        result = [r for r in rows if self._matches(r)]
        for column, desc in reversed(self._order):
            result.sort(key=lambda r: r.get(column), reverse=desc)
        if self._limit is not None:
            result = result[: self._limit]
        return FakeResult([dict(r) for r in result])


class FakeRpcCall:
    """Mimics the object supabase.Client.rpc(...) returns: callers chain
    .execute() onto it, just like a table query."""

    def __init__(self, client, fn_name, params):
        self.client = client
        self.fn_name = fn_name
        self.params = params

    def execute(self):
        if self.fn_name == "increment_clicks":
            code = self.params["url_code"]
            for row in self.client.tables["urls"]:
                if row["code"] == code:
                    row["clicks"] += 1
        return FakeResult(data=[])


class FakeSupabaseClient:
    def __init__(self):
        self.tables = {"urls": [], "users": []}
        self._seq = {"urls": 0, "users": 0}

    def table(self, name):
        return FakeQuery(self, name)

    def rpc(self, fn_name, params):
        return FakeRpcCall(self, fn_name, params)
