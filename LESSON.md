# Data Engineering Lesson — building the Olist MongoDB + FastAPI project

This document explains, from the ground up, what was built in this repository, **why** each
piece exists, and what it teaches about how data engineering / backend projects are built
professionally in 2026. It assumes you know basic Python but have not yet built a real
API-on-top-of-a-database project. Read it next to the actual source files — every section
points at a real file and a real function.

---

## 1. What we built, in one paragraph

We took 9 CSV files (a relational e-commerce dataset: customers, orders, order items,
payments, reviews, products, sellers...) and turned them into a small **service**: a
program that owns the data, stores it in MongoDB (a NoSQL / document database), and lets
other programs ask it questions over HTTP (`GET /orders/123`, `GET
/analytics/top-sellers`...) instead of ever touching the CSVs or the database directly.

```
CSV files  --[ingestion script]-->  MongoDB  <--[pymongo]--  FastAPI app  <--HTTP--  client
(datas/)      (src/olist/ingestion)  (4 collections)      (src/olist/)            (browser, curl,
                                                                                    another service)
```

That arrow structure — **files → load once → database → API → consumers** — is the shape of
almost every real-world data platform, just at a much bigger scale (there, "files" become
Kafka topics or S3 buckets, and "load once" becomes a scheduled Airflow DAG).

---

## 2. The big picture: what makes this a "real" project and not a script

A beginner script usually looks like: one `.py` file, hardcoded values, `print()` instead of
errors, no tests, "works on my machine." Here is what separates this project from that, and
why each difference matters.

### 2.1 Separation of concerns

Each file has exactly one job:

| File | Job | NOT its job |
|---|---|---|
| `config.py` | know *where* things are (Mongo URI, DB name) | connect to anything |
| `database.py` | know *how* to open a MongoDB connection | know what's inside it |
| `schemas.py` | describe the *shape* of data going out over HTTP | fetch or store anything |
| `routers/*.py` | answer one HTTP request: read query params, call MongoDB, shape a response | parse CSVs |
| `ingestion/load.py` | read CSVs once, clean them, write them to MongoDB | serve HTTP requests |

**Why this matters:** when something breaks ("the API returns wrong dates"), you know
immediately which file to open. When a beginner mixes everything into one file, every bug
hunt means re-reading the whole program. This is called **separation of concerns**, and it's
the single most valuable habit to build early.

### 2.2 Configuration via environment variables (the "12-factor app" idea)

`src/olist/config.py`:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "olist"

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

**Example:** on your laptop, `.env` has `MONGO_URI=mongodb://localhost:27017`. Inside the
Docker container, `docker-compose.yml` sets `MONGO_URI=mongodb://mongo:27017` (the container
talks to MongoDB by its service *name*, not `localhost`). **The Python code never changes** —
only the environment around it does. That's the whole point.

- **Alternative rejected:** hardcoding `"mongodb://localhost:27017"` directly in
  `database.py`. This would work on your machine and break the moment anyone else — your
  binôme, a Docker container, a grading server — runs it with a different setup. This is
  *the* classic "works on my machine" bug, and 12-factor config (settings from environment,
  never from code) is the industry-standard fix. It's why `.env.example` exists: it documents
  *which* variables exist without leaking real secrets into git.
- `@lru_cache` matters too: without it, every request would re-read and re-validate the `.env`
  file. With it, `Settings()` is built once and reused — a **singleton** pattern via caching
  rather than a global variable.

### 2.3 Reproducible environments: venv + Docker, two different problems

- **`venv/`** solves "which Python packages, at which versions." `pyproject.toml` lists
  `fastapi>=0.119.1`, and `pip install -e ".[dev]"` installs exactly that, isolated from
  whatever else is installed on your system Python.
- **Docker / `docker-compose.yml`** solves "which *services* exist and how they're
  networked" — here, MongoDB itself. You cannot `pip install` a database engine into a venv;
  it's not a Python package, it's a whole separate running process. Docker packages it
  (binary + config + storage) into a container you can start/stop/delete without touching
  your system.

**Why not skip Docker and install MongoDB directly on the machine?** You could — but then
"how do I install MongoDB" becomes a step every teammate and grader must repeat, differently
on Linux/macOS/Windows, and it pollutes their system permanently. `docker compose up -d
mongo` is one command, identical everywhere, and `docker compose down` leaves no trace. This
is why **containerization** is now the default answer to "how do I give someone else my exact
running environment."

### 2.4 Data modeling driven by usage, not by the source's shape

This is the most important *design* decision in the project, and it's explained in depth in
`README.md` §5, so here's the short version with the underlying principle: **a relational
database is normalized to avoid duplicating data; a document database is modeled around how
data will be *read*.** Those are different, sometimes opposite, goals.

Concretely: `order_items`, `order_payments`, `order_reviews` were CSV files (and would be SQL
tables) on their own. In MongoDB they became **arrays embedded inside the `orders`
document**, because every single time you want an order's items, you also want the order —
there's no use case for "give me item #4821 without its order." Embedding means **one
database read** returns everything; referencing (like `customers`, kept separate) would mean
a second query (a "join", which MongoDB does support via `$lookup` but expensively) every
time.

- **Alternative rejected:** mirror the 9 CSVs into 9 collections with foreign keys, exactly
  like the relational source. The brief explicitly forbids this ("the relational structure
  must not be reproduced automatically") because it throws away the one advantage document
  databases offer, and instead reproduces relational *and* NoSQL's own downsides (multiple
  round-trips, join costs) with none of the benefits (referential integrity, `JOIN`) that SQL
  gives you for that pattern.

### 2.5 Validation at every boundary

Two different kinds of validation exist in this project, at two different boundaries:

1. **Data entering the system** (`ingestion/load.py`): CSV values are messy — missing
   fields, `NaN`, numpy types Mongo can't store. They get cleaned once, at import time.
2. **Requests entering the API** (`routers/*.py`): a client can send `limit=99999` or
   `status=bananas`. FastAPI + Pydantic reject these automatically, before your code ever
   runs, with a clear `422 Unprocessable Entity`.

**Why validate in two places instead of trusting the data once it's "in the system"?** Because
they answer different questions: ingestion asks "is this CSV row usable at all", the API asks
"is this *specific request*, from a client I don't control, safe to execute". A client
sending `limit=99999` isn't a data quality problem, it's a **potential denial-of-service** —
imagine that query trying to serialize 99,441 orders into one JSON response. This is why
every list endpoint caps `limit` at 100.

### 2.6 Measuring performance instead of guessing

`scripts/explain_demo.py` runs the *actual* query MongoDB would run for `GET
/orders?status=delivered&date_from=2018-01-01&date_to=2018-01-31`, twice — once with no
index, once after adding one — and reports **facts**:

```
Before index (COLLSCAN):  docs_examined: 99441   execution_time_ms: 91
After index (IXSCAN):      docs_examined: 7069    execution_time_ms: 16
```

**Why this matters as a habit, not just a brief requirement:** "add an index, it'll be
faster" is a guess. `explain()` turns performance work into an experiment with a measurable
before/after, exactly like a unit test proves correctness. Professionals distrust
performance claims without numbers — this is the data engineering equivalent of "show me the
benchmark."

### 2.7 Idempotent pipelines

`import_all()` in `ingestion/load.py` calls `db[name].delete_many({})` before every
`insert_many()`. **Idempotent** means: running the script once, or five times in a row,
leaves the database in the *same* final state.

**Why it matters:** without this, re-running the import after fixing a bug in
`load_products()` would leave *duplicate* products alongside the old (wrong) ones. In a real
pipeline that runs on a schedule (nightly, hourly...), a script that isn't safe to re-run is a
script that *will* eventually corrupt your data, the first time it's re-triggered after a
partial failure.

### 2.8 Automated tests as a safety net, not as paperwork

`tests/` doesn't just check "does the code run" — it encodes *decisions* as assertions, so
that if someone later breaks one, a machine notices before a human does:

```python
def test_list_orders_rejects_invalid_status(client):
    response = client.get("/orders", params={"status": "not-a-status"})
    assert response.status_code == 422
```

This test *is* the specification "unknown statuses are rejected with 422," written in a form
that can never go silently out of date the way a comment or a README paragraph can.

---

## 3. Function-by-function walkthrough

### 3.1 `config.py` — `get_settings()`

```python
@lru_cache
def get_settings() -> Settings:
    return Settings()
```

**Example:** call `get_settings().mongo_db` anywhere in the code and get `"olist"` (or
whatever `MONGO_DB` is set to) without that code needing to know *how* settings are loaded.
This is **dependency inversion**: routers depend on "a function that returns settings," not
on `.env` file parsing details.

### 3.2 `database.py` — `get_database()`

```python
@lru_cache
def _client() -> MongoClient:
    return MongoClient(get_settings().mongo_uri)

def get_database() -> Database:
    return _client()[get_settings().mongo_db]
```

**Example:** every router does `db: Database = Depends(get_database)`. FastAPI calls
`get_database()` for you before running the route function, and hands you the result as the
`db` argument.

- **Why `@lru_cache` on `_client()`?** Opening a `MongoClient` isn't free — it manages a pool
  of TCP connections. You want **one** client shared by the whole app, not a new one per
  request. `lru_cache` with no arguments makes `_client()` behave like a lazily-created
  singleton: the first call creates it, every later call returns the same object.
- **Why is this a function (`get_database`) and not a global variable `db = ...`?** Because a
  function can be *swapped* in tests. See §3.8 below — this single design choice is what lets
  the test suite run against a completely different, disposable database without changing
  one line of router code.

### 3.3 `schemas.py` — Pydantic models, e.g. `Order`

```python
class Order(BaseModel):
    order_id: str
    status: str
    purchase_timestamp: datetime
    items: list[OrderItem]
    review: Review | None
    total_value: float
```

**Example:** `Order(**doc)` where `doc` is a raw MongoDB document. If `doc` is missing
`total_value`, or if `purchase_timestamp` isn't actually a valid date, Pydantic raises an
error immediately, loudly, with a clear message — instead of silently returning broken JSON
to whoever called the API.

- **Why not just return `dict(doc)` directly, as many beginner APIs do?** Two reasons.
  First, `doc` still has MongoDB's internal `_id` field, which is an implementation detail
  the API shouldn't leak. Second — and more important — a typed model becomes
  **self-documenting**: FastAPI reads the `Order` class and generates the Swagger page at
  `/docs` automatically, listing every field and its type, with zero extra effort. Untyped
  dicts give you none of that.

### 3.4 `utils.py` — `strip_id()`

```python
def strip_id(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc
```

**Example:** `Customer(**strip_id(db.customers.find_one({"_id": "abc"})))`. Without
`strip_id`, `Customer(**doc)` would fail with "unexpected keyword argument `_id`" since
`Customer` has no `_id` field (on purpose — see 3.3).

- **Why a tiny one-line function instead of inlining `doc.pop("_id", None)` everywhere?**
  Because it's repeated in every single router (7 times). A one-line helper isn't
  "over-engineering" — it's naming a repeated idea once so a reader instantly recognizes it,
  and so a future change (e.g. also stripping an internal `_imported_at` field) happens in
  one place.

### 3.5 Routers — e.g. `routers/orders.py::list_orders`

```python
@router.get("", response_model=OrderSummaryPage)
def list_orders(
    status: OrderStatus | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Database = Depends(get_database),
) -> OrderSummaryPage:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must be before date_to")
    ...
```

**Example:** `GET /orders?status=delivered&limit=500` → FastAPI checks `limit <= 100` *before*
your function body runs, and returns `422` automatically. `GET /orders?date_from=2018-02-01&
date_to=2018-01-01` → your function body runs, notices the dates are inverted, and returns a
readable `400`.

- **Why `Depends(get_database)` instead of importing a global `db` object at the top of the
  file?** This is FastAPI's **dependency injection** system. It looks like extra ceremony for
  a solo script, but it buys you one enormous thing: in tests, you can replace *only* this one
  dependency (`app.dependency_overrides[get_database] = lambda: fake_db`) without touching
  route code at all. A hardcoded global `db` can't be swapped that way.
- **Why `422` for bad params but `400` for the date range, and `404` for missing orders?**
  This maps to real HTTP semantics, which any client developer already understands: `422` =
  "the request shape itself is invalid" (FastAPI/Pydantic's job), `400` = "shape is fine, but
  the combination doesn't make sense" (your business logic's job), `404` = "the shape and
  logic are fine, the resource just doesn't exist." Returning `200` with an error message
  buried in the JSON body — a very common beginner mistake — forces every client to
  special-case your API instead of using standard HTTP error handling.

### 3.6 `ingestion/load.py` — the cleaning helpers

```python
def _num_or_none(value) -> float | None:
    return None if pd.isna(value) else float(value)
```

**Example:** `products.csv` has 2 rows with an empty `product_weight_g` cell. Pandas reads
that empty cell as `NaN` (not-a-number, a special float). `_num_or_none(NaN)` → `None`.
`_num_or_none(225.0)` → `225.0`.

- **Why `float(value)` instead of just returning `value` as-is?** Pandas numeric columns hold
  `numpy.float64` / `numpy.int64` values, not plain Python `float`/`int`. MongoDB's driver
  (`pymongo`) can silently mis-handle or reject some numpy types. Casting explicitly to
  Python's built-in `float`/`int` avoids a whole category of "works until it doesn't" bugs —
  a beginner would hit this the first time they tried to insert a numpy value and got a
  cryptic `InvalidDocument` error.

```python
def _items_by_order(data_dir: Path) -> dict[str, list[dict]]:
    df = pd.read_csv(...)
    df["_item"] = df.apply(lambda r: {...}, axis=1)
    return df.sort_values("order_item_id").groupby("order_id")["_item"].apply(list).to_dict()
```

**Example:** `order_items.csv` has 2 rows for `order_id = "abc"` (two products bought in one
order). This function turns those 2 rows into `{"abc": [{"product_id": "p1", ...},
{"product_id": "p2", ...}]}` — exactly the shape needed for the embedded `items` array on the
`orders` document.

- **Why build this lookup dict once instead of querying `order_items.csv` again for every
  order inside a loop?** `load_orders()` processes 99,441 orders. A dict lookup
  (`items_by_order.get(order_id, [])`) is O(1); re-scanning a 112,650-row file per order would
  be O(n·m) — tens of millions of operations, minutes instead of seconds. This "group once,
  look up many times" pattern is one of the most common performance techniques in data
  processing.

```python
df = df.sort_values("review_answer_timestamp").drop_duplicates(subset="order_id", keep="last")
```

**Example:** the dataset has 551 orders with *two* review rows (a customer re-reviewed).
Sorting by answer date then keeping the *last* row per `order_id` means: when duplicates
exist, keep the most recent review, discard the earlier one.

- **Why decide this instead of, say, keeping the first review, or embedding both as a
  list?** Embedding a list "just in case" for something that happens in 0.5% of orders would
  force *every* consumer of the API to handle "review could be one object or an array" for no
  real benefit. Picking one clear, documented rule (latest wins) keeps the schema simple. This
  is a **data cleaning decision**, and real data engineering work is full of exactly this kind
  of judgment call — the important part isn't which rule you pick, it's that you notice the
  duplicates exist at all, decide deliberately, and write down why (see the comment in the
  code and in `README.md` §5).

### 3.7 `scripts/explain_demo.py` — reading `explain()` output

```python
before = db.orders.find(QUERY).explain()
...
db.orders.create_index(INDEX)
after = db.orders.find(QUERY).explain()
```

**Example output interpretation:** `"stage": "COLLSCAN"` means MongoDB walked through every
single document in the collection checking if it matched — the database equivalent of
reading every page of a book to find one sentence. `"stage": "FETCH"` (with an index) means
MongoDB used a sorted structure (the index) to jump straight to the ~7,069 candidates, the
way a book's index sends you straight to the right page.

- **Why a compound index on `(status, purchase_timestamp)` and not two separate indexes?**
  MongoDB can only efficiently use *one* index per query in most cases. A compound index on
  both fields, in that order, lets Mongo narrow by `status` first (few possible values) and
  then binary-search within that slice by date — matching exactly how the query filters. Two
  separate single-field indexes would each help *individually* but MongoDB would still have to
  intersect the results, which is slower.

### 3.8 `tests/conftest.py` — the dependency-override pattern

```python
@pytest.fixture()
def client(db):
    app.dependency_overrides[get_database] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
```

**Example:** in `test_get_customer_found`, `db.customers.insert_one(CUSTOMER)` writes to a
throwaway `olist_test` database, then `client.get("/customers/cust-1")` runs against the
*real* FastAPI app — but every route's `Depends(get_database)` is transparently redirected to
that test database instead of your real `olist` database.

- **Why test against a real (if disposable) MongoDB instead of mocking pymongo?** A mock
  would only prove "my code calls `.find_one()` the way I expect" — it can't catch a wrong
  MongoDB query operator, a bad aggregation pipeline stage, or a type mismatch, because a
  mock doesn't actually run MongoDB's query engine. Testing against real MongoDB (just an
  isolated, wiped-between-tests database) catches real bugs at the cost of needing Mongo
  running — a trade-off this project makes deliberately, and documents in the README ("start
  Mongo first").

### 3.9 `Dockerfile` / `docker-compose.yml`

```dockerfile
RUN pip install --no-cache-dir .
CMD ["fastapi", "run", "src/olist/main.py", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
api:
  depends_on:
    mongo:
      condition: service_healthy
```

**Example:** `docker compose up -d` builds an image containing exactly the code and
dependencies from `pyproject.toml`, then starts it — but only *after* MongoDB's healthcheck
(`mongosh --eval "db.adminCommand('ping')"`) reports success.

- **Why `depends_on: condition: service_healthy` instead of just `depends_on: mongo`?**
  Plain `depends_on` only waits for the container to *start*, not for MongoDB inside it to be
  *ready to accept connections* — those are seconds apart but real, and the API would
  otherwise crash on its first connection attempt. The healthcheck closes that gap.

---

## 4. Decisions and alternatives — quick recap table

| Decision made | Alternative considered | Why the alternative was rejected here |
|---|---|---|
| Embed items/payments/review in `orders` | Separate collection per CSV file (mirror SQL) | Brief forbids reproducing the relational schema; every read of an order needs all of these together |
| `pymongo` (synchronous) | `motor` (async MongoDB driver) | FastAPI supports both, but sync `pymongo` is simpler to reason about and test for a project this size; async only pays off under heavy concurrent load |
| Real test MongoDB (`olist_test` db) | `mongomock` (in-memory fake) | Catches real query/aggregation bugs a mock cannot; acceptable trade-off since Docker makes a real Mongo instance one command away |
| `ruff` for linting | `flake8` + `isort` + `black` separately | One fast Rust-based tool replacing three slower Python ones — the current standard in new Python projects |
| `pyproject.toml` only | `requirements.txt` + `setup.py` | Single source of truth for dependencies, metadata, tool config (`[tool.ruff]`, `[tool.pytest.ini_options]`) — the modern packaging standard |
| Read-only API (no POST/PUT) | Full CRUD | The dataset is a historical snapshot; the brief's usages are all "consult / analyze" — building write endpoints nobody needs is scope creep |
| Precompute `items_count`/`total_value` at import | Compute on every request via aggregation | Avoids re-aggregating on every single list request for values that never change after import |

---

## 5. Professional strategies you're seeing here (and where they come from)

- **Dependency injection** (FastAPI's `Depends`) — same idea used in Spring (Java), Angular
  (JS), NestJS: code declares *what it needs*, a framework decides *how to provide it*. Makes
  testing and swapping implementations trivial.
- **"Parse, don't validate"** (Pydantic models like `Order`, `Customer`) — instead of checking
  `if "order_id" in doc: ...` scattered everywhere, you convert untrusted data into a typed
  object *once*, at the boundary, and trust the type afterward.
- **Infrastructure as code** (`docker-compose.yml`) — the *definition* of "what services this
  project needs and how they connect" lives in a versioned file, not in a wiki page or
  someone's memory.
- **12-factor configuration** (env vars, `.env`/`.env.example`) — the same technique used by
  virtually every cloud-deployed application (Heroku popularized the term; every serverless
  and container platform since has followed it).
- **Idempotent, re-runnable pipelines** — the foundation of tools like Airflow, dbt, and
  Dagster: a pipeline step should be safe to retry after a partial failure without manual
  cleanup.
- **Contract-first / auto-generated API docs** (OpenAPI/Swagger from type hints) — the
  documentation cannot drift out of sync with the code because it's *generated from* the code,
  not hand-written separately.
- **Fast, unified tooling** (`ruff`, `pyproject.toml`) — the broader 2024-2026 trend in the
  Python ecosystem (see also `uv` for package installation) of replacing many small, slow
  tools with fewer, faster, Rust-powered ones.

---

## 6. Suggested next steps for your binôme

1. **Git**: this folder isn't a git repository yet (it just got moved out of the personal
   course repo into the shared `groupe/` folder). Since the brief requires visible
   contributions from both of you, the next step is `git init`, an initial commit, and a
   shared GitHub remote — both of you cloning it and committing your own parts.
2. **Presentation**: use the README's §5 (data modeling) and §7 (explain/index) sections as
   the backbone of the "why MongoDB, why these choices" part of your soutenance — you already
   have real numbers (91ms → 16ms) to show, not just claims.
3. **If you have time**: a cursor-based pagination alternative to `skip`/`limit` is worth
   mentioning as a known limitation — `skip` gets slower on very large offsets because MongoDB
   still has to walk past every skipped document internally.
