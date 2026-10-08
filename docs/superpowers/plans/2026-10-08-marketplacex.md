# MarketplaceX Demo Website Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A locally runnable Flask website where every use case in the report's Figure 1 is performable by its actor, backed by the §8.1 domain model, BR01–BR08 and the §9.5 order state machine.

**Architecture:** A modular monolith. Each Figure 2 service is a package under `marketplacex/modules/<name>/` with `models.py`, `service.py` and `routes.py`. Routes call only their own module's service. Cross-module effects go through other services' functions or the in-process event bus (`marketplacex/events.py`). External providers are fake adapters in `marketplacex/adapters/`.

**Tech Stack:** Python 3.9+, Flask 3.x, Flask-SQLAlchemy 3.1 (SQLAlchemy 2), SQLite, Jinja + Bootstrap 5 (CDN), pytest.

**Spec:** `docs/superpowers/specs/2026-10-08-marketplacex-design.md`. Read §3 (classes), §3.1 (state machine), §5 (use case → screen) and §6 (flows) before starting any task.

**Time budget:** a few hours. Tasks 1–14 are the core demo path (search → checkout → fulfil → deliver → review → return → refund → settlement). Tasks 15–20 add the remaining consoles. If time runs short, stop after any task ≥ 14; the app is demoable at every commit after Task 14.

## Global Constraints

- Python 3.9 compatible: put `from __future__ import annotations` at the top of every module; no `match` statements; use `Optional[X]` inside SQLAlchemy `Mapped[...]` annotations (those are evaluated at runtime).
- `requirements.txt`: `flask>=3.0,<3.2`, `flask-sqlalchemy>=3.1`, `pytest>=8`. No other dependencies.
- Set up once with `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`. All commands below use `.venv/bin/python -m pytest`.
- All money is integer VND in columns named `*_vnd`. Never use floats for money.
- All "current time" reads go through `marketplacex.modules.admin.policy.now()` (it applies the demo clock offset). Naive UTC datetimes.
- Module and method names match the report §7 interfaces: `reserve/commit/release`, `authorize/refund`, `quote/place_order`, `create_orders/transition`, `open_case/decide`, `evaluate`.
- Order status changes only through `order.service.transition(...)`.
- Every privileged action (seller, admin, support or risk mutation, plus support data reveal) calls `audit.service.record(...)` with a reason when the action takes one.
- Seed accounts all use password `demo123`: `alice@demo` (customer), `sportzone@demo`, `techhub@demo`, `stylehouse@demo` (sellers), `admin@demo`, `support@demo`, `risk@demo`.
- Policy defaults (PlatformPolicy): `return_window_days=7`, `platform_fee_pct=5`, `seller_response_hours=48`, `reservation_ttl_min=15`, `quote_ttl_min=10`, `risk_max_order_vnd=20000000`, `risk_max_vouchers_per_day=3`, `risk_max_refunds_30d=3`, `prohibited_terms="counterfeit,replica,fake"`.
- Read policy only as `from marketplacex.modules.admin import policy` then `policy.get_int(...)` / `policy.now()` (module attribute access), so tests can monkeypatch it.
- Commit after every task with a message ending in `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Test Helpers (all in `tests/conftest.py`, added by the first task that uses them)

| Helper | Added in | Behavior |
|---|---|---|
| `app`, `client`, `make_user(role, email=None)`, `login(client, user)` | 1 | see Task 1 |
| `seeded` (fixture), `offer_id(key)`, `product_id(key)`, `shop_id(name)`, `user_id(email)`, `seller_user(email)`, `alice_user()`, `alice` (fixture), `cat(name)` | 2 | `seeded` runs `seed.seed_catalog()` (and `seed_promotions()` once Task 5 exists) |
| `make_order(status)` | 6 | inserts a minimal one-item Order directly, with the given status |
| `captured_payment(amount)` | 7 | `authorize` + signed success callback |
| `pay_success(group_id)`, `pay_fail(group_id)`, `paid_order(customer, key, qty)` | 8/9 | cart → quote (no vouchers) → place → callback; returns the Order |
| `shipped_order(customer, key)`, `delivered_order(customer, key)` | 10 | `paid_order` + seller accept/pack/hand over (+ advance until delivered) |
| `c_return_shipment(case)`, `disputed_case(customer)` | 12 | the return Shipment of a case; open → seller reject → escalate |
| `valid_listing_data()`, `pending_product()` | 15 | a valid Shoes listing dict; the seeded pending product |

## Review Focus

1. **Another user's resource by URL id:** e.g. customer B opening `/orders/<A's id>`, or seller X posting to `/seller/orders/<Y's order>/accept`, must get 404 with no state change. Tests in Task 9 and Task 10.
2. **Cart item that became unavailable** (offer's product suspended, or stock 0) before quote: the quote page should list it as unavailable and exclude it, not crash or charge it. Test in Task 8.
3. **Bad quantity input** (`0`, `-1`, `abc`, above purchase limit) in the cart form: expect a flash error, cart unchanged, no 500. Test in Task 4.
4. **Search with no keywords** (empty string, or only a price phrase like "under 500k"): expect an in-stock list filtered by price, sorted by sales, no exception. Test in Task 3.
5. **Evidence upload that isn't a PNG/JPEG or is > 2 MB:** expect rejection with a message and no file stored. Test in Task 12.

---

## File Map

```
requirements.txt  README.md  .gitignore
marketplacex/
  __init__.py  app.py  config.py  extensions.py  errors.py  events.py  seed.py
  auth.py                       # current_user(), require_role(), login helpers
  adapters/ __init__.py payment_provider.py logistics_provider.py notification_provider.py
  modules/<name>/ __init__.py models.py service.py routes.py
     names: admin audit identity seller catalog inventory search cart promotion
            order payment logistics checkout notification review returns
            settlement reporting support risk chat
  templates/ base.html  _macros.html  auth/ customer/ seller/ admin/ support/ risk/
  static/ app.css  sample_images/*.svg  uploads/ (gitignored)
tests/ conftest.py  test_<module>.py ...  test_e2e.py
```

`app.create_app(config: dict | None = None) -> Flask` registers every module's blueprint (if its `routes.py` exists) and imports every `service.py` so event subscribers register.

---

### Task 1: Foundation — app factory, errors, events, policy/clock, audit, identity

**Files:**
- Create: `requirements.txt`, `.gitignore` (`.venv/`, `*.db`, `instance/`, `marketplacex/static/uploads/`, `__pycache__/`), `marketplacex/{__init__,app,config,extensions,errors,events,auth}.py`, `marketplacex/modules/{admin,audit,identity}/{__init__,models,service}.py`, `marketplacex/modules/admin/{policy,routes}.py`, `marketplacex/modules/identity/routes.py`, `templates/base.html`, `templates/_macros.html`, `templates/auth/{login,register,forgot,reset,account}.html`, `static/app.css`
- Test: `tests/conftest.py`, `tests/test_foundation.py`

**Interfaces — Produces:**
- `extensions.db` (Flask-SQLAlchemy instance).
- `errors.DomainError(Exception)` with `.code: str` and `.message: str`. Subclasses: `IllegalTransition`, `InsufficientStock`, `PurchaseLimitExceeded`, `VoucherInvalid`, `VoucherExhausted`, `QuoteChanged` (has `.changed: list[dict]`), `QuoteExpired`, `RefundExceedsCaptured`, `NotEligible`, `StaleVersion`, `Forbidden`, `InvalidSignature`, `NotFound`, `ValidationError`.
  - The app error handler: for an HTML request, `flash(e.message, "danger")` + redirect to `request.referrer or "/"`; for a JSON request or a path starting `/api/` or `/payments/callback`, `{"code","message","correlation_id"}` with status 400 (403 for Forbidden, 404 for NotFound).
- `events.publish(name: str, aggregate_id, payload: dict) -> EventLog`.
- `events.subscribe(name: str, consumer: str)`: a decorator for `fn(event: EventLog)`. Delivery is synchronous. A `ProcessedEvent(consumer, event_id)` unique row makes redelivery a no-op.
- `events.redeliver(event: EventLog)`: re-runs all subscribers (used by tests).
- Models: `EventLog(id, name, aggregate_id: str, payload: JSON, occurred_at, correlation_id)` and `ProcessedEvent`.
- `admin.models.PlatformPolicy(key PK, value: str)` and `Clock(id=1, offset_hours: int)`.
- `admin.policy`:
  - `now() -> datetime`
  - `advance_clock(hours: int) -> None`
  - `get_int(key) -> int`
  - `get_str(key) -> str`
  - `set_value(key, value, actor) -> None` (audited)
  - `ensure_defaults() -> None` (inserts the Global Constraints defaults)
- `audit.models.AuditEvent` (fields per spec §3) and `audit.service.record(actor, action: str, target_type: str, target_id, reason: str | None = None, before: dict | None = None, after: dict | None = None) -> AuditEvent`. Digests are `sha256(json.dumps(x, sort_keys=True))[:16]`. `correlation_id` comes from `g.correlation_id` (set per request in `before_request` as a uuid4 hex), or `"cli"`.
- `identity.models.User(id, email unique, password_hash, name, role, status='active', phone, created_at)`, `Address(id, user_id, recipient, phone, line, city, is_default)`, `PasswordResetToken(token, user_id, expires_at, used)`.
- `identity.service`:
  - `register(email, password, name) -> User` (role customer)
  - `authenticate(email, password) -> User` (raises `ValidationError` on bad credentials or a suspended account)
  - `add_address(user, **fields) -> Address`
  - `start_recovery(email) -> str | None` (token)
  - `reset_password(token, new_password) -> None`
- `auth.current_user() -> User | None`, `auth.login_user(user)`, `auth.logout_user()`, and the decorator `auth.require_role(*roles)`: redirects to `/login` if anonymous, raises `Forbidden` if the role is wrong.
- Routes:
  - `GET/POST /login`, `/logout`, `GET/POST /register`
  - `POST /demo-login/<role>`: logs in as the first seeded user with that role
  - `GET/POST /forgot`: shows "email sent" plus the reset link on screen in dev
  - `GET/POST /reset/<token>`
  - `GET /account`, `POST /account/addresses`
- `base.html`: a navbar with role-specific links (customer: Search, Cart, Orders, Saved, Chat, Notifications bell; seller: Seller Center; admin, support, risk: their console), a flash area, and a `{% block content %}`. The login page shows demo buttons for each role.
- `tests/conftest.py` fixtures:
  - `app`: `create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://", "SECRET_KEY": "t", "PAYMENT_WEBHOOK_SECRET": "whsec", "NOTIFICATION_FAILURE_RATE": 0})`, then `db.create_all()` and `ensure_defaults()` inside an app context that stays pushed for the test.
  - `client`
  - `make_user(role="customer", email=None) -> User`
  - `login(client, user)`: sets the session user id via `client.session_transaction()`.

- [ ] **Step 1: Write the failing tests** in `tests/test_foundation.py`

```python
def test_register_and_login(client):
    r = client.post("/register", data={"email": "b@x", "password": "pw12345", "name": "B"}, follow_redirects=True)
    assert r.status_code == 200
    client.get("/logout")
    r = client.post("/login", data={"email": "b@x", "password": "pw12345"}, follow_redirects=True)
    assert b"B" in r.data

def test_require_role_blocks_wrong_role(client, make_user, login):
    login(client, make_user("customer"))
    assert client.get("/admin/").status_code == 403   # admin blueprint stub registered in this task

def test_event_consumer_runs_once_on_redelivery(app):
    from marketplacex import events
    seen = []
    @events.subscribe("TestHappened", "test-consumer")
    def h(ev): seen.append(ev.id)
    ev = events.publish("TestHappened", 1, {})
    events.redeliver(ev)
    assert seen == [ev.id]

def test_clock_advance(app):
    from marketplacex.modules.admin import policy
    t0 = policy.now(); policy.advance_clock(48)
    assert (policy.now() - t0).total_seconds() >= 48 * 3600 - 5

def test_audit_record_has_digest(app, make_user):
    from marketplacex.modules.audit import service as audit
    a = audit.record(make_user("admin"), "x.do", "thing", 1, reason="r", before={"a": 1}, after={"a": 2})
    assert a.before_digest != a.after_digest and a.reason == "r"

def test_password_recovery(app, make_user):
    from marketplacex.modules.identity import service as ids
    u = make_user("customer", email="r@x")
    tok = ids.start_recovery("r@x"); ids.reset_password(tok, "newpass1")
    assert ids.authenticate("r@x", "newpass1").id == u.id
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `.venv/bin/python -m pytest tests/test_foundation.py -v`
Expected: errors on `ModuleNotFoundError: marketplacex`.

- [ ] **Step 3: Implement the files listed above.** `admin/routes.py` contains only the blueprint `admin_bp` (url_prefix `/admin`) with `GET /admin/` → `require_role("admin")` placeholder dashboard (Task 16 fills it). `app.py` also registers a CLI command `flask --app marketplacex.app seed` that drops and recreates all tables and then calls `seed.run()` (seed.py starts as `def run(): ensure_defaults()`). Database file: `instance/marketplacex.db`.

- [ ] **Step 4: Run the tests and verify they pass**

Run: `.venv/bin/python -m pytest tests/test_foundation.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit** (`feat: app foundation, events, audit, identity`)

---

### Task 2: Catalog, shops, inventory + catalog seed + browse pages

**Files:**
- Create: `modules/seller/{models,service}.py`, `modules/catalog/{models,service,routes}.py`, `modules/inventory/{models,service}.py`, templates `customer/{home,category,shop,product}.html`; modify `seed.py`
- Test: `tests/test_catalog_inventory.py`

**Interfaces:**
- Consumes: `db`, `User`, `policy.now/get_int`, `audit.record`, `events.publish`.
- Produces:
  - `seller.models.Shop` (spec §3 fields). `seller.service.create_shop(owner, name, location) -> Shop` and `seller.service.shops_of(user) -> list[Shop]`.
  - `catalog.models`: `Category`, `Product`, `Variant`, `Offer` per spec §3; `Offer` has `UniqueConstraint(shop_id, variant_id)` (BR01). `Product.status` defaults to `"draft"`.
  - `catalog.service`:
    - `create_product(shop, category, title, brand, description, attributes: dict, variants: list[dict], image_url=None, image_vector=None) -> Product`. Each variant dict is `{name, price_vnd, original_price_vnd=None, stock, purchase_limit=10}`. It creates Variant, Offer and StockLedger.
    - `set_status(product, status, actor=None, reason=None) -> Product`: publishes `ProductChanged`.
    - `get_product(id) -> Product`, `get_offer(id) -> Offer` (both raise `NotFound`).
    - `category_tree() -> list[Category]` (roots with `.children`).
    - `active_offers()`: query of Offers whose product is active.
    - `delivery_promise(offer, city: str | None) -> str`: "2–3 days" if same city as the shop, else "3–5 days".
  - `inventory.models.StockLedger(offer_id unique, available, reserved, committed, version)` with `CheckConstraint` on all three being `>= 0`, and `Reservation` per spec.
  - `inventory.service`:
    - `get_ledger(offer_id) -> StockLedger`
    - `set_stock(offer_id, available) -> None`
    - `reserve(items: list[tuple[int, int]], attempt_id: str, ttl_min: int) -> list[Reservation]`: idempotent per attempt_id; all-or-nothing; raises `InsufficientStock` naming the offer.
    - `commit(attempt_id) -> None`, `release(attempt_id) -> None`: both idempotent.
    - `return_committed(offer_id, qty) -> None`: committed→available, used by cancellation and returns.
    - `sweep_expired() -> list[str]`: the attempt_ids whose held reservations passed expiry; releases them.
    - `in_stock(offer_id) -> int`.
  - Routes (`catalog_bp`, no prefix): `GET /` (home: category tree, campaign banners once Task 5 exists, recommendations once Task 3 exists, popular offers), `GET /category/<id>`, `GET /shops/<id>`, `GET /products/<id>`.
  - Product detail shows: variant selector, price, original price (struck through only when > price), shop link, rating and count, sold count, delivery promise, stock status, plus "Add to cart", "Save" and "Chat with seller" buttons (the buttons post to routes added in later tasks; render them only if the endpoint exists via a `has_endpoint` Jinja helper).
  - `seed.seed_catalog()`:
    - Users per Global Constraints.
    - Shops: SportZone (Hanoi), TechHub (Ho Chi Minh City), StyleHouse (Da Nang), all `verified`.
    - Categories: Fashion > Shoes, Fashion > Clothing, Electronics > Accessories, Beauty. Shoes `attribute_schema=["size","color"]`, others `["color"]`.
    - Alice gets one default address in Hanoi.
    - The 12 products below, all `active`, each with one variant "Default", stock 50 and purchase_limit 5. `created_at` is now − 10 days, except P04 and P10 (now − 60 days).

| Key | Title | Brand | Shop | Category | price_vnd | orig | rating | sold | vector |
|---|---|---|---|---|---|---|---|---|---|
| P01 | Nike Air Zoom Black Running Shoes | Nike | SportZone | Shoes | 1990000 | 2490000 | 4.9 | 1200 | (0.80,0.30,0.20) |
| P02 | Adidas Ultraboost White Running Shoes | Adidas | SportZone | Shoes | 2350000 | – | 4.8 | 900 | (0.85,0.25,0.15) |
| P03 | Biti's Hunter Black Sneakers | Biti's | SportZone | Shoes | 899000 | 1050000 | 4.7 | 3000 | (0.93,0.09,0.11) |
| P04 | Converse Classic Canvas Shoes | Converse | SportZone | Shoes | 1450000 | – | 4.6 | 500 | (0.75,0.20,0.40) |
| P05 | Sony Wireless Noise Cancelling Headphones | Sony | TechHub | Accessories | 6490000 | 7490000 | 4.8 | 300 | (0.10,0.90,0.20) |
| P06 | Anker 65W USB-C Charger | Anker | TechHub | Accessories | 590000 | – | 4.7 | 800 | (0.05,0.85,0.10) |
| P07 | Logitech Wireless Mouse | Logitech | TechHub | Accessories | 429000 | 499000 | 4.8 | 2500 | (0.10,0.95,0.05) |
| P08 | Puma Black Sport Socks | Puma | SportZone | Clothing | 99000 | – | 4.5 | 4000 | (0.60,0.10,0.70) |
| P09 | Women Linen Summer Dress | StyleHouse | StyleHouse | Clothing | 349000 | 450000 | 4.6 | 700 | (0.20,0.10,0.95) |
| P10 | RGB Mechanical Keyboard | Keychron | TechHub | Accessories | 1190000 | – | 4.7 | 600 | (0.10,0.88,0.30) |
| P11 | Men Cotton T Shirt Black | StyleHouse | StyleHouse | Clothing | 129000 | – | 4.6 | 5000 | (0.25,0.05,0.90) |
| P12 | Skincare Sunscreen SPF50 | StyleHouse | StyleHouse | Beauty | 489000 | – | 4.9 | 1500 | (0.15,0.30,0.85) |

Descriptions: one sentence each containing the title words plus a Vietnamese gloss for P01 ("giày chạy bộ màu đen") and P03 ("giày sneaker màu đen"). Each product's `attributes` has `color` (black/white/etc.) and, for shoes, `size: "42"`. Image URLs point to `static/sample_images/<key>.svg`. Create 12 simple SVGs: a colored rectangle plus the product name.

- [ ] **Step 1: Write the failing tests**

```python
def test_offer_unique_per_shop_variant(seeded):          # BR01; add `seeded` fixture to conftest: calls seed.seed_catalog()
    from marketplacex.modules.catalog.models import Offer
    o = Offer.query.first()
    db.session.add(Offer(shop_id=o.shop_id, variant_id=o.variant_id, price_vnd=1)); 
    with pytest.raises(IntegrityError): db.session.flush()

def test_reserve_commit_release_never_negative(seeded):
    oid = offer_id("P03"); inventory.set_stock(oid, 2)
    inventory.reserve([(oid, 2)], "a1", 15)
    with pytest.raises(InsufficientStock): inventory.reserve([(oid, 1)], "a2", 15)
    inventory.reserve([(oid, 2)], "a1", 15)                 # idempotent
    led = inventory.get_ledger(oid); assert (led.available, led.reserved) == (0, 2)
    inventory.release("a1"); led = inventory.get_ledger(oid); assert (led.available, led.reserved) == (2, 0)

def test_sweep_releases_expired(seeded):
    oid = offer_id("P03"); inventory.reserve([(oid, 1)], "a3", 15); policy.advance_clock(1)
    assert inventory.sweep_expired() == ["a3"]

def test_product_page_shows_commercial_fields(client, seeded):
    html = client.get(f"/products/{product_id('P01')}").get_data(as_text=True)
    for s in ["Nike Air Zoom", "1,990,000", "2,490,000", "SportZone", "4.9", "1200"]: assert s in html
```

Add the helpers `offer_id(key)` and `product_id(key)` to conftest. They look up by title prefix through a `SEED_KEYS` dict exported from `seed.py` (key → title).

- [ ] **Step 2: Run the tests and verify they fail** — `.venv/bin/python -m pytest tests/test_catalog_inventory.py -v` → FAIL (missing modules).
- [ ] **Step 3: Implement the interfaces above.** Add a Jinja filter `vnd` that formats `1990000` as `1,990,000 ₫`.
- [ ] **Step 4: Run the tests and verify they pass** → 4 passed; the full suite stays green.
- [ ] **Step 5: Commit** (`feat: catalog, shops, inventory and seed catalogue`)

---

### Task 3: Search (text / voice / image) + recommendations

**Files:**
- Create: `modules/search/{__init__,query,ranking,images,service,models,routes}.py`, `templates/customer/search.html`, `static/js/voice.js`
- Test: `tests/test_search.py`

**Interfaces:**
- Consumes: `catalog.service.active_offers`, `inventory.service.in_stock`, `catalog.service.delivery_promise`.
- Produces:
  - `query.Query`: a dataclass with `type: str` ('text'|'voice'|'image'), `raw: str`, `terms: list[str]`, `max_price: int | None`, `min_price: int | None`, `vector: tuple | None`, `filters: dict` (category_id, brand, min_rating, location, in_stock: bool), `sort: str` ('relevance'|'sales'|'rating'|'newest'|'price_asc'|'price_desc'), `degraded: bool`.
  - `query.build_query(mode, text="", image_key=None, filters=None, sort="relevance") -> Query`:
    - Lowercases and strips Vietnamese diacritics (`unicodedata` NFD, drop combining marks, map đ→d).
    - Applies `SYNONYMS = {"giay": "shoes", "chay": "running", "bo": "", "mau": "", "den": "black", "trang": "white", "chuot": "mouse", "khong day": "wireless", "ao": "shirt"}`. Multi-word keys are applied first; an empty value drops the token.
    - Parses the price ceiling from `under|below|duoi <n> (million|trieu|m|k|nghin)?` (`million|trieu|m` ×1,000,000; `k|nghin` ×1,000; bare numbers are VND). Removes price tokens and the stopwords `{"under","below","duoi","for","the","a"}` from the terms.
    - Image mode: `vector = images.SAMPLE_IMAGES.get(image_key)`. If missing, set `degraded=True` and fall back to text mode using `text`.
  - `images.SAMPLE_IMAGES: dict[str, tuple]`: `{"black-sneaker": (0.93,0.09,0.11), "wireless-mouse": (0.10,0.95,0.05), "summer-dress": (0.20,0.10,0.95)}`, with a matching SVG in `static/sample_images/query-<key>.svg`.
  - `ranking.score(q, product, offer, shop, customer_city) -> float` per spec §6.5:
    - `lexical` = the fraction of `q.terms` found in the tokens of title + brand + category name + attribute values.
    - `semantic` = cosine(q.vector, product.image_vector) in image mode; otherwise the fraction of terms found in the description.
    - `offer_quality` = rating/5; `seller_quality` = 1.0 if verified else 0.5; `delivery_fit` = 1.0 if same city else 0.5; `freshness` = 1.0 if created ≤ 30 days ago else 0.5.
    - Image mode weights are `semantic 0.75, offer 0.10, seller 0.08, delivery 0.05, fresh 0.02`; text/voice use the spec's weights.
  - `service.search(q: Query, customer=None) -> SearchResult`:
    - `SearchResult` has `items: list[ResultItem]`, `facets: dict[str, list[tuple[str,int]]]` (category, brand, location), `relax_hints: list[str]`, `trace_id: str`, `degraded: bool`.
    - `ResultItem` has `offer, product, shop, score: float, trace_id: str, stock: int`.
    - Hard filters run first (active, price bounds, filters).
    - Text/voice keep `lexical > 0` when terms are non-empty. Image keeps `cosine >= 0.8`.
    - Sort, then tie-break by offer id. With no terms and no vector, the default order is sales.
    - Writes `SearchTrace(trace_id, customer_id, query_json, result_count, degraded, at)`.
    - If there are zero results with filters active: `relax_hints` = one message per active filter (e.g. "Remove price limit under 500,000 ₫").
  - `service.recommend(customer, limit=6) -> list[tuple[Offer, str]]`:
    - Reasons: "Because you searched '<q>'" (top hit of their latest RecentSearch, Task 4 model; guard with try/except ImportError until Task 4 exists), "Similar to items you saved", else "Popular now" (top sales).
    - Excludes offers the customer purchased in the last 30 days (guard until Task 6).
  - Route `GET /search?q=&mode=text|voice|image&image=&category=&brand=&min_price=&max_price=&min_rating=&location=&in_stock=1&sort=`.
  - The page has 3 tabs:
    - Text input.
    - Mic button: `voice.js` uses `webkitSpeechRecognition`, fills a transcript box and submits with `mode=voice`; if unsupported, it shows the transcript box for typing.
    - Image picker: the 3 sample thumbnails plus a file input. An uploaded file → `image=upload` → degraded.
  - The page also shows facets with counts, sort select, result cards with the trace id in a small muted font, a "degraded" alert and relax hints.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("mode,text,image,top", [
    ("text", "black running shoes under 2 million", None, "P01"),
    ("voice", "wireless mouse under 500k", None, "P07"),
    ("image", "", "black-sneaker", "P03"),
    ("text", "giày chạy bộ màu đen", None, "P01"),
])
def test_prototype_top_results(seeded, mode, text, image, top):
    r = search_service.search(build_query(mode, text=text, image_key=image))
    assert r.items[0].product.id == product_id(top)

def test_price_ceiling_applied_before_ranking(seeded):
    r = search_service.search(build_query("text", "running shoes under 2 million"))
    assert product_id("P02") not in [i.product.id for i in r.items]

def test_empty_results_give_relax_hints(seeded):
    r = search_service.search(build_query("text", "headphones under 100k"))
    assert r.items == [] and any("price" in h.lower() for h in r.relax_hints)

def test_unknown_image_falls_back_to_text_degraded(seeded):
    r = search_service.search(build_query("image", text="mouse", image_key="upload"))
    assert r.degraded and r.items[0].product.id == product_id("P07")

def test_no_keywords_lists_by_sales(seeded):            # Review Focus 4
    r = search_service.search(build_query("text", "under 500k"))
    assert r.items and all(i.offer.price_vnd <= 500000 for i in r.items)
    assert r.items[0].product.id == product_id("P11")    # 5000 sold
    assert search_service.search(build_query("text", "")).items

def test_sort_price_deterministic(seeded):
    r = search_service.search(build_query("text", "shoes", sort="price_asc"))
    prices = [i.offer.price_vnd for i in r.items]; assert prices == sorted(prices)

def test_search_page_renders(client, seeded):
    assert b"Nike Air Zoom" in client.get("/search?q=black+running+shoes").data
```

- [ ] **Step 2: Run the tests and verify they fail** — `.venv/bin/python -m pytest tests/test_search.py -v` → FAIL.
- [ ] **Step 3: Implement the interfaces above.** Wire "Recommended for you" (or "Popular now") onto `/`.
- [ ] **Step 4: Run the tests and verify they pass** → 10 passed. If a prototype parametrized case fails, adjust only tokenization/synonyms; do not change the seed vectors or weights.
- [ ] **Step 5: Commit** (`feat: multimodal search with report ranking formula`)

---

### Task 4: Cart, saved items, recent searches

**Files:**
- Create: `modules/cart/{models,service,routes}.py`, `templates/customer/{cart,saved}.html`
- Test: `tests/test_cart.py`

**Interfaces:**
- Consumes: `catalog.service.get_offer`, `inventory.service.in_stock`, `auth.require_role`.
- Produces:
  - Models `Cart(customer_id unique, version)`, `CartItem(cart_id, offer_id, qty, selected=True; unique(cart_id, offer_id))`, `SavedItem`, `RecentSearch`.
  - `cart.service`:
    - `get_cart(customer) -> Cart`
    - `change_item(customer, offer_id: int, qty: int, expected_version: int | None = None) -> Cart`:
      - qty 0 removes the item.
      - Validates `0 <= qty <= offer.purchase_limit` (else `PurchaseLimitExceeded`/`ValidationError`) and that the product is active.
      - A version mismatch raises `StaleVersion`. Each change does `version += 1`.
    - `add_item(customer, offer_id, qty=1) -> Cart`: adds to the existing qty.
    - `set_selected(customer, offer_id, selected: bool) -> Cart`
    - `grouped(cart) -> list[ShopGroup]`: `ShopGroup(shop, items: list[CartItem], subtotal_vnd)`; subtotal counts only selected items.
    - `selected_items(customer, version: int) -> list[CartItem]`: raises `StaleVersion`.
    - `remove_items(customer, offer_ids: list[int]) -> None`
    - `toggle_saved(customer, kind, target_id) -> bool`
    - `saved(customer) -> list[SavedItem]`
    - `record_search(customer, text) -> None`: keeps the latest 10, deduped.
    - `recent_searches(customer) -> list[RecentSearch]`
    - `delete_recent(customer, id) -> None`
  - Routes (customer role):
    - `GET /cart`
    - `POST /cart/add` (offer_id, qty)
    - `POST /cart/items/<offer_id>` (qty, version)
    - `POST /cart/items/<offer_id>/select`
    - `POST /saved/toggle` (kind, target_id)
    - `GET /saved` (saved products, saved shops, recent searches with delete buttons)
    - `POST /recent/<id>/delete`
  - The search route calls `record_search` for logged-in customers.
  - Form qty parsing: non-integer → `ValidationError("Quantity must be a whole number")`.

- [ ] **Step 1: Write the failing tests**

```python
def test_cart_groups_by_shop_and_versions(seeded, alice):   # conftest `alice` fixture = seeded customer
    c = cart.add_item(alice, offer_id("P03"), 2); v = c.version
    c = cart.add_item(alice, offer_id("P07"), 1)
    assert c.version == v + 1
    groups = cart.grouped(c)
    assert {g.shop.name for g in groups} == {"SportZone", "TechHub"}
    assert next(g for g in groups if g.shop.name == "SportZone").subtotal_vnd == 1798000

def test_stale_version_rejected(seeded, alice):
    c = cart.add_item(alice, offer_id("P03"), 1)
    with pytest.raises(StaleVersion): cart.change_item(alice, offer_id("P03"), 2, expected_version=c.version - 1)

@pytest.mark.parametrize("qty", ["0x", "-1", "abc", "6"])          # Review Focus 3 (limit is 5)
def test_bad_qty_flashes_and_keeps_cart(client, seeded, alice, login, qty):
    login(client, alice); client.post("/cart/add", data={"offer_id": offer_id("P03"), "qty": 1})
    r = client.post(f"/cart/items/{offer_id('P03')}", data={"qty": qty}, follow_redirects=True)
    assert r.status_code == 200 and cart.get_cart(alice).items[0].qty == 1

def test_saved_and_recent(seeded, alice):
    assert cart.toggle_saved(alice, "product", product_id("P01")) is True
    cart.record_search(alice, "mouse"); cart.record_search(alice, "mouse")
    assert len(cart.recent_searches(alice)) == 1
```

- [ ] **Step 2: Run the tests and verify they fail.**
- [ ] **Step 3: Implement the interfaces above.**
- [ ] **Step 4: Run the tests and verify they pass** (the full suite stays green).
- [ ] **Step 5: Commit** (`feat: cart grouped by shop, saved items, recent searches`)

---

### Task 5: Promotion — campaigns, vouchers, redemptions

**Files:**
- Create: `modules/promotion/{models,service,routes}.py`, `templates/customer/campaign.html`; modify `seed.py` (`seed_promotions()`)
- Test: `tests/test_promotion.py`

**Interfaces:**
- Produces:
  - Models per spec §3 (`Campaign`, `Voucher`, `Redemption`), with `UniqueConstraint(customer_id, campaign_id, attempt_id)` on Redemption (BR04).
  - `promotion.service.evaluate(customer, shop_subtotals: dict[int, int], shipping: dict[int, int], codes: list[str]) -> Evaluation`:
    - `Evaluation` has `applied: list[Applied]`, `item_discounts: dict[int, int]` (per shop), `shipping_discounts: dict[int, int]`.
    - `Applied` has `voucher_id, code, campaign_id, shop_id | None, amount_vnd`.
    - Rules: the code exists and its campaign is active at `now()` (else `VoucherInvalid`); `used_count < usage_limit` and `spent + amount <= budget` (else `VoucherExhausted`); min_spend is checked against the shop subtotal (shop voucher) or the overall subtotal (platform voucher).
    - At most one platform voucher and one per shop.
    - percent → `min(subtotal * value // 100, max_discount_vnd)`.
    - A platform discount is split across shops proportionally to subtotal, with the remainder going to the largest shop.
    - free_shipping → `min(shipping, max_discount_vnd)`.
  - `reserve(customer, applied: list[Applied], attempt_id, ttl_min) -> list[Redemption]`: idempotent per attempt; held redemptions count against usage/budget.
  - `commit(attempt_id, group_id) -> None`: used_count += 1, spent_vnd += amount.
  - `release(attempt_id) -> None`
  - `active_campaigns() -> list[Campaign]`
  - Route `GET /campaigns/<id>`: the campaign's vouchers and eligible products. Shop voucher → that shop's offers; platform voucher → all active offers.
  - Seed:
    - Campaign "10.10 Sale" (budget 10,000,000; runs now−1d to now+30d).
    - Platform voucher `SALE10` (percent 10, max 100,000, min 0, usage_limit 1000).
    - SportZone voucher `SPORT80` (fixed 80,000, min_spend 500,000, usage_limit 500).
    - Home page shows the campaign banner.

- [ ] **Step 1: Write the failing tests**

```python
def test_report_example_discount(seeded):          # report §13.1: 2 Biti's + 2 vouchers → discount 180,000
    sz = shop_id("SportZone")
    ev = promo.evaluate(alice_user(), {sz: 1798000}, {sz: 28000}, ["SALE10", "SPORT80"])
    assert sum(ev.item_discounts.values()) == 180000

def test_min_spend_and_unknown_code(seeded):
    sz = shop_id("SportZone")
    with pytest.raises(VoucherInvalid): promo.evaluate(alice_user(), {sz: 100000}, {sz: 28000}, ["SPORT80"])
    with pytest.raises(VoucherInvalid): promo.evaluate(alice_user(), {sz: 100000}, {sz: 28000}, ["NOPE"])

def test_redemption_unique_per_attempt(seeded):    # BR04
    sz = shop_id("SportZone"); ev = promo.evaluate(alice_user(), {sz: 1798000}, {sz: 0}, ["SALE10"])
    a = promo.reserve(alice_user(), ev.applied, "att1", 15); b = promo.reserve(alice_user(), ev.applied, "att1", 15)
    assert [r.id for r in a] == [r.id for r in b]

def test_exhausted(seeded):
    v = Voucher.query.filter_by(code="SPORT80").one(); v.usage_limit = 0
    with pytest.raises(VoucherExhausted): promo.evaluate(alice_user(), {shop_id("SportZone"): 1798000}, {}, ["SPORT80"])
```

- [ ] **Step 2: Run the tests and verify they fail.** **Step 3: Implement the interfaces above.** **Step 4: Run the tests and verify they pass.** **Step 5: Commit** (`feat: vouchers, campaigns and redemption holds`)

---

### Task 6: Order aggregate + state machine

**Files:**
- Create: `modules/order/{models,state_machine,service}.py`
- Test: `tests/test_order_state.py`

**Interfaces:**
- Produces:
  - Models per spec §3: `Order`, `OrderItem`, `OrderStatusHistory`. Order also has `attempt_id: str`, `cancel_from: str | None` and `delivered_at`.
  - `state_machine.TRANSITIONS: dict[str, set[str]]`: exactly the spec §3.1 table plus `DeliveryException → {Shipped, Cancelled}`, `Disputed → {Refunded, Completed}`, and `CancelRequested → {Cancelled, Preparing, ReadyToShip}`.
  - `state_machine.GUARDS: dict[tuple[str, str], Callable[[Order], tuple[bool, str]]]`:
    - `(PendingPayment, Confirmed)`: paymentAuthorized, via `payment.service.is_captured(order.group_id)`. Import lazily; until Task 7 exists, the test patches it.
    - `(ReadyToShip, Shipped)`: beforeHandover (`order.status` not cancelled and no pending CancelRequested).
    - `(Shipped, Delivered)`: deliveryEvidenceValid (`logistics.service.has_delivery_event(order.id)`).
    - `(Delivered|Completed, ReturnRequested)`: withinReturnWindow (`now() <= delivered_at + return_window_days`).
  - `order.service`:
    - `create_orders(group, shop_lines: list[dict], address: Address, actor) -> list[Order]`:
      - `shop_lines[i] = {shop_id, items: [{offer_id, title, variant, unit_price_vnd, qty, discount_vnd}], merchandise_vnd, discount_vnd, shop_discount_vnd, platform_discount_vnd, shipping_vnd, total_vnd}`.
      - An item's `discount_vnd` is the total discount on that line (all units). `discount_vnd = shop_discount_vnd + platform_discount_vnd`.
      - Creates the Order(s) in `Draft`, then transitions each to `PendingPayment`.
    - `transition(order, to: str, actor: User | None, reason: str | None = None) -> Order`:
      - Checks TRANSITIONS and the guard (raises `IllegalTransition` with the guard name).
      - Writes the history row (actor_id, from, to, reason, `now()`) and calls `audit.record(actor, f"order.{to}", "order", order.id, reason)`.
      - Sets `delivered_at` when entering Delivered and `cancel_from` when entering CancelRequested.
      - `version += 1`; publishes `OrderStatusChanged` with `{order_id, from, to, shop_id, customer_id, reason}`.
    - `get_for_customer(customer, order_id) -> Order` and `get_for_shop_owner(user, order_id) -> Order`: both raise `NotFound` when not owned.
    - `orders_of_customer(customer)`, `orders_of_shop(shop, status=None)`, `orders_of_group(group_id)`.

- [ ] **Step 1: Write the failing tests**

```python
LEGAL = [("Draft","PendingPayment"),("PendingPayment","Cancelled"),("Confirmed","Preparing"),
         ("Preparing","ReadyToShip"),("Preparing","CancelRequested"),("Delivered","Completed")]
ILLEGAL = [("PendingPayment","Shipped"),("Cancelled","Confirmed"),("Draft","Delivered"),("Shipped","Preparing")]

@pytest.mark.parametrize("a,b", LEGAL)
def test_legal(app, a, b): assert b in TRANSITIONS[a]

@pytest.mark.parametrize("a,b", ILLEGAL)
def test_illegal_raises(app, make_order, a, b):       # conftest make_order(status=...) inserts a minimal Order
    o = make_order(status=a)
    with pytest.raises(IllegalTransition): order_service.transition(o, b, None)
    assert o.status == a

def test_transition_writes_history_audit_event(app, make_order):
    o = make_order(status="Confirmed"); order_service.transition(o, "Preparing", None, "seller accepted")
    h = OrderStatusHistory.query.filter_by(order_id=o.id).one()
    assert (h.from_status, h.to_status, h.reason) == ("Confirmed", "Preparing", "seller accepted")
    assert EventLog.query.filter_by(name="OrderStatusChanged").count() == 1

def test_guard_blocks_unpaid_confirm(app, make_order, monkeypatch):
    monkeypatch.setattr("marketplacex.modules.order.state_machine._is_captured", lambda gid: False)
    with pytest.raises(IllegalTransition, match="paymentAuthorized"):
        order_service.transition(make_order(status="PendingPayment"), "Confirmed", None)

def test_return_window_guard(app, make_order):
    o = make_order(status="Delivered"); o.delivered_at = policy.now(); policy.advance_clock(8 * 24)
    with pytest.raises(IllegalTransition): order_service.transition(o, "ReturnRequested", None)
```

- [ ] **Step 2–4:** Run → fail; implement; run → pass. `state_machine` wraps the cross-module checks in the module-level functions `_is_captured(group_id)` and `_has_delivery(order_id)` so tests can patch them.
- [ ] **Step 5: Commit** (`feat: order aggregate and guarded state machine`)

---

### Task 7: Payment + fake providers (payment, logistics quote)

**Files:**
- Create: `adapters/{payment_provider,logistics_provider}.py`, `modules/payment/{models,service,routes}.py`, `modules/logistics/{models,service}.py`
- Test: `tests/test_payment.py`

**Interfaces:**
- Produces:
  - `adapters.payment_provider.FakePaymentProvider(secret)`:
    - `authorize(amount_vnd, attempt_id) -> str` (provider_ref `"PAY-" + uuid8`)
    - `void(ref)`
    - `refund(ref, amount_vnd, key) -> str` (refund ref)
    - `sign(payload: dict) -> str`: HMAC-SHA256 of `json.dumps(payload, sort_keys=True)` with the secret
    - `verify(payload, sig) -> bool`
  - `adapters.logistics_provider.FakeLogisticsProvider`:
    - `quote(from_city, to_city) -> int`: always 28000
    - `create(order_id, kind) -> tuple[str, str]`: tracking_no, label_url (`/seller/labels/<tracking_no>`)
    - `NEXT = ["picked_up", "in_transit", "out_for_delivery", "delivered"]`
  - `payment.models.PaymentAttempt` and `Refund` per spec (`provider_ref` unique).
  - `payment.service`:
    - `authorize(group_id, amount_vnd, attempt_id) -> PaymentAttempt`: status pending; idempotent per attempt_id.
    - `handle_callback(payload: dict, signature: str) -> PaymentAttempt`:
      - payload is `{event_id, provider_ref, status: "authorized"|"failed"}`.
      - Bad signature → `InvalidSignature`.
      - An already-processed event_id, or an attempt already final → returns it unchanged.
      - authorized → status `captured`, `captured_vnd = amount_vnd` (the demo authorizes and captures together), publish `PaymentAuthorized {group_id, payment_id}`.
      - failed → status `failed`, publish `PaymentChanged {group_id, status: "failed"}`.
    - `simulate(payment_id, outcome: "success"|"fail") -> dict`: builds and signs a payload. The route uses it; a "duplicate" outcome posts the same signed payload twice.
    - `void(payment_id) -> None`
    - `is_captured(group_id) -> bool`
    - `captured_for_group(group_id) -> PaymentAttempt | None`
    - `refundable_vnd(payment_id) -> int`: captured − successful refunds.
    - `refund(payment_id, amount_vnd, idempotency_key, return_case_id=None) -> Refund`:
      - BR07: amount > refundable → `RefundExceedsCaptured`.
      - The same key → the original Refund.
      - Calls the provider and sets status `succeeded` synchronously; publishes `PaymentChanged {kind: "refund", refund_id, return_case_id}`.
  - Routes:
    - `POST /payments/callback`: JSON body, `X-Signature` header; returns `{"status": attempt.status}`.
    - `GET /payments/<id>/pay`: the customer "provider page" with buttons Success / Fail / Duplicate callback.
    - `POST /payments/<id>/simulate/<outcome>`: redirects to the checkout result page `/checkout/<group_id>/result` (that route exists after Task 8; use `url_for` inside a try and fall back to `/orders`).
  - `logistics.models.Shipment`, `TrackingEvent` per spec. `logistics.service.quote(address, shop_ids: list[int]) -> dict[int, int]`. (Shipment creation and tracking come in Task 10; `has_delivery_event(order_id) -> bool` is defined here and returns False until then.)

- [ ] **Step 1: Write the failing tests**

```python
def test_callback_signature_verified(app):
    p = pay.authorize(1, 100000, "att")
    with pytest.raises(InvalidSignature): pay.handle_callback({"event_id": "e1", "provider_ref": p.provider_ref, "status": "authorized"}, "bad")

def test_duplicate_callback_single_capture(app):
    p = pay.authorize(1, 100000, "att"); body = pay.simulate(p.id, "success")
    pay.handle_callback(body["payload"], body["signature"]); pay.handle_callback(body["payload"], body["signature"])
    assert EventLog.query.filter_by(name="PaymentAuthorized").count() == 1 and p.captured_vnd == 100000

def test_refund_bound(app):          # BR07
    p = captured_payment(100000)     # helper: authorize + success callback
    pay.refund(p.id, 60000, "k1"); pay.refund(p.id, 60000, "k1")          # idempotent
    with pytest.raises(RefundExceedsCaptured): pay.refund(p.id, 50000, "k2")
    assert pay.refundable_vnd(p.id) == 40000

def test_callback_endpoint(client, app):
    p = pay.authorize(1, 5000, "att"); b = pay.simulate(p.id, "fail")
    r = client.post("/payments/callback", json=b["payload"], headers={"X-Signature": b["signature"]})
    assert r.json["status"] == "failed"
```

- [ ] **Step 2–4:** fail → implement → pass.
- [ ] **Step 5: Commit** (`feat: payment service with signed idempotent callbacks`)

---

### Task 8: Checkout saga + UI

**Files:**
- Create: `modules/checkout/{models,service,routes}.py`, `modules/risk/{models,service}.py` (stub), `templates/customer/{checkout,checkout_result}.html`
- Test: `tests/test_checkout.py`

**Interfaces:**
- Consumes: `cart.service.selected_items/grouped/remove_items`, `promotion.service.evaluate/reserve/commit/release`, `logistics.service.quote`, `inventory.service.reserve/commit/release/sweep_expired`, `payment.service.authorize/void`, `order.service.create_orders/transition/orders_of_group`, `policy.get_int`.
- Produces:
  - `checkout.models.CheckoutGroup` per spec, plus `attempt_id` (uuid hex), `quote_payload: JSON`, `address_id`, `voucher_codes: JSON`, and `UniqueConstraint(customer_id, idempotency_key)`.
  - `risk.service.evaluate_checkout(customer, group) -> str`: returns `"approved"` in this task (Task 18 adds rules).
  - `checkout.service`:
    - `quote(customer, address_id: int, voucher_codes: list[str]) -> CheckoutGroup`:
      - Sweeps first. Uses the selected cart items.
      - Items whose product isn't active or with stock < qty go to `quote_payload["unavailable"]` and are excluded.
      - No available items → `ValidationError("Nothing to check out")`.
      - `quote_payload = {"shops": [shop_line...], "unavailable": [...], "cart_version": v}`, with shop_line as in Task 6.
      - Item-level discounts: each shop's discount (shop voucher + allocated platform share) is spread over its items proportionally (remainder to the first item).
      - Shipping discounts reduce `shipping_vnd`.
      - `quote_hash = sha256(json.dumps(quote_payload, sort_keys=True))`, `quote_expires_at = now + quote_ttl_min`.
    - `place_order(customer, group_id, idempotency_key: str, quote_hash: str) -> CheckoutGroup`, per spec §6.1 step 2:
      - An existing group with the same (customer, key) → returned as is.
      - Expired → `QuoteExpired`. Hash mismatch, or a recompute (same address/codes) that differs → `QuoteChanged(changed=[...])`.
      - Calls `inventory.reserve(..., ttl=reservation_ttl_min)`, then `promotion.reserve`, then `create_orders` (orders in PendingPayment), then `risk.evaluate_checkout`.
      - Approved → `continue_after_risk(group)`. Held → status `placing` with `failure_reason="Under risk review"`.
      - Any `DomainError` after reservations → `compensate(group, str(e))`, then re-raise.
    - `continue_after_risk(group) -> PaymentAttempt`: `payment.authorize(group.id, group.total_vnd, group.attempt_id)`.
    - `compensate(group, reason) -> None`: releases inventory and promotion, voids payment if pending, transitions each PendingPayment order to PaymentFailed (if the payment failed) or Cancelled, and sets the group to `failed` with the reason. Idempotent.
    - `sweep() -> None`: for each attempt_id returned by `inventory.sweep_expired()`, finds its group and calls `compensate(group, "Reservation expired")`.
    - Subscriber `PaymentAuthorized` (consumer `checkout`): orders → Confirmed, `inventory.commit`, `promotion.commit`, `cart.remove_items` of the purchased offers, group → `completed`, publish `OrderCreated {order_id, customer_id, shop_id}` per order, and `sold_count += qty`.
    - Subscriber `PaymentChanged` with status failed: `compensate(group, "Payment failed")`.
  - Routes (customer):
    - `GET /checkout`: address select, voucher codes input, "Get quote" button.
    - `POST /checkout/quote` → redirect to `GET /checkout/<group_id>`, which shows per-shop lines, discounts, shipping, total, unavailable items, expiry countdown and a "Place order" form with hidden `quote_hash` and a hidden `idempotency_key` (uuid generated when the page renders).
    - `POST /checkout/<group_id>/place` → redirect to `/payments/<payment_id>/pay` (or the result page when held).
    - `GET /checkout/<group_id>/result`: status and order links.
    - A `QuoteChanged` error renders the quote page again with the changed items highlighted.

- [ ] **Step 1: Write the failing tests**

```python
def quote_two_bitis(alice):
    cart.add_item(alice, offer_id("P03"), 2)
    return checkout.quote(alice, alice.addresses[0].id, ["SALE10", "SPORT80"])

def test_quote_matches_report(seeded, alice):        # BR02, report §13.1
    g = quote_two_bitis(alice)
    assert (g.merchandise_vnd, g.discount_vnd, g.shipping_vnd, g.total_vnd) == (1798000, 180000, 28000, 1646000)

def test_place_is_idempotent(seeded, alice):
    g = quote_two_bitis(alice)
    checkout.place_order(alice, g.id, "k1", g.quote_hash); checkout.place_order(alice, g.id, "k1", g.quote_hash)
    assert inventory.get_ledger(offer_id("P03")).reserved == 2 and Order.query.count() == 1

def test_price_change_detected(seeded, alice):
    g = quote_two_bitis(alice); catalog.get_offer(offer_id("P03")).price_vnd = 950000
    with pytest.raises(QuoteChanged): checkout.place_order(alice, g.id, "k1", g.quote_hash)

def test_success_callback_confirms_and_commits(seeded, alice):
    g = quote_two_bitis(alice); checkout.place_order(alice, g.id, "k1", g.quote_hash)
    pay_success(g.id)                                  # helper: simulate + handle_callback
    o = Order.query.one(); led = inventory.get_ledger(offer_id("P03"))
    assert o.status == "Confirmed" and (led.reserved, led.committed) == (0, 2)
    assert cart.get_cart(alice).items == []

def test_payment_fail_compensates(seeded, alice):
    g = quote_two_bitis(alice); checkout.place_order(alice, g.id, "k1", g.quote_hash); pay_fail(g.id)
    assert Order.query.one().status == "PaymentFailed"
    assert inventory.get_ledger(offer_id("P03")).reserved == 0
    assert Redemption.query.filter_by(status="held").count() == 0

def test_expired_reservation_cancels(seeded, alice):
    g = quote_two_bitis(alice); checkout.place_order(alice, g.id, "k1", g.quote_hash)
    policy.advance_clock(1); checkout.sweep()
    assert Order.query.one().status == "Cancelled"

def test_unavailable_item_excluded(seeded, alice):  # Review Focus 2
    cart.add_item(alice, offer_id("P03"), 1); cart.add_item(alice, offer_id("P07"), 1)
    inventory.set_stock(offer_id("P07"), 0)
    g = checkout.quote(alice, alice.addresses[0].id, [])
    assert [u["offer_id"] for u in g.quote_payload["unavailable"]] == [offer_id("P07")]
    assert g.merchandise_vnd == 899000

def test_two_shops_two_orders_one_group(seeded, alice):   # FR11
    cart.add_item(alice, offer_id("P03"), 1); cart.add_item(alice, offer_id("P07"), 1)
    g = checkout.quote(alice, alice.addresses[0].id, []); checkout.place_order(alice, g.id, "k", g.quote_hash)
    assert {o.shop_id for o in order_service.orders_of_group(g.id)} == {shop_id("SportZone"), shop_id("TechHub")}
```

- [ ] **Step 2–4:** fail → implement → pass (the full suite stays green).
- [ ] **Step 5: Commit** (`feat: checkout saga with quote hash, idempotency and compensation`)

---

### Task 9: Notifications, order tracking, cancellation

**Files:**
- Create: `adapters/notification_provider.py`, `modules/notification/{models,service,routes}.py`, `modules/order/routes.py`, `templates/customer/{orders,order_detail,notifications}.html`
- Test: `tests/test_tracking_cancel.py`

**Interfaces:**
- Produces:
  - `FakeNotificationProvider(failure_rate)`: `send(channel, to, body) -> bool`.
  - `notification.service.notify(user_id, template: str, body: str, channel="in_app") -> Notification`: status `sent`/`failed` from the provider.
  - `notification.service.unread_count(user) -> int`, `inbox(user)`, `mark_read(user, id)`.
  - Subscribers (consumer `notification`):
    - `OrderCreated` → customer "Order #N placed" and the shop owner "New order #N".
    - `OrderStatusChanged` → the customer, for every status (template `order_status`), and the shop owner for `CancelRequested`, `ReturnRequested` and `Disputed`.
  - `base.html` bell with the unread count (context processor).
  - `order.service.request_cancel(customer, order, reason) -> Order`:
    - Draft/PendingPayment/Confirmed → `Cancelled` + `_compensate_order(order)`. PendingPayment: release that order's reservations and void the group payment only when every order in the group is cancelled. Confirmed: `inventory.return_committed` for each item and `payment.refund(captured.id, order.total_vnd, f"cancel-{order.id}")`.
    - Preparing/ReadyToShip → `CancelRequested`.
    - Otherwise `IllegalTransition`.
  - `order.service.resolve_cancel(seller, order, approve: bool, reason) -> Order`: approve → `Cancelled` + compensate; decline → back to `order.cancel_from`.
  - Routes (customer):
    - `GET /orders` (list with status badges)
    - `GET /orders/<id>`: items with snapshots, status timeline (actor name, time, reason), shipment tracking events, and buttons by state (Cancel, Review, Return, Contact support, Chat). Buttons for later tasks render only if their endpoint exists.
    - `POST /orders/<id>/cancel` (reason)
    - `GET /notifications`, `POST /notifications/<id>/read`

- [ ] **Step 1: Write the failing tests**

```python
def test_confirmation_notifies_customer_and_seller(seeded, alice):
    paid_order(alice, "P03", 1)                       # conftest helper: cart → quote → place → success → returns Order
    assert Notification.query.filter_by(user_id=alice.id).count() >= 1
    assert Notification.query.filter_by(user_id=user_id("sportzone@demo")).count() >= 1

def test_cancel_confirmed_refunds_and_restocks(seeded, alice):
    o = paid_order(alice, "P03", 1); before = inventory.get_ledger(offer_id("P03")).available
    order_service.request_cancel(alice, o, "changed mind")
    assert o.status == "Cancelled" and inventory.get_ledger(offer_id("P03")).available == before + 1
    assert Refund.query.one().amount_vnd == o.total_vnd

def test_cancel_preparing_needs_seller(seeded, alice):
    o = paid_order(alice, "P03", 1); order_service.transition(o, "Preparing", None)
    order_service.request_cancel(alice, o, "late"); assert o.status == "CancelRequested"
    order_service.resolve_cancel(seller_user("sportzone@demo"), o, False, "already packed"); assert o.status == "Preparing"

def test_other_customer_gets_404(client, seeded, alice, make_user, login):   # Review Focus 1
    o = paid_order(alice, "P03", 1); login(client, make_user("customer"))
    assert client.get(f"/orders/{o.id}").status_code == 404
    assert client.post(f"/orders/{o.id}/cancel", data={"reason": "x"}).status_code == 404 and o.status == "Confirmed"

def test_timeline_renders(client, seeded, alice, login):
    o = paid_order(alice, "P03", 1); login(client, alice)
    html = client.get(f"/orders/{o.id}").get_data(as_text=True)
    assert "PendingPayment" in html and "Confirmed" in html
```

- [ ] **Step 2–4:** fail → implement → pass.
- [ ] **Step 5: Commit** (`feat: notifications, order tracking and cancellation`)

---

### Task 10: Seller Center — fulfilment, shipments, tracking (UC04)

**Files:**
- Create: `modules/seller/routes.py`, `templates/seller/{dashboard,orders,order_detail,label}.html`; modify `modules/logistics/service.py`, `modules/logistics/routes.py` (new)
- Test: `tests/test_fulfilment.py`

**Interfaces:**
- Produces:
  - `logistics.service`:
    - `create_shipment(order, weight_g: int, kind="forward", return_case=None) -> Shipment`: one active forward shipment per order, else `ValidationError`. `promised_pickup_at = now + 24h`.
    - `advance(shipment, fail=False) -> TrackingEvent`: appends the next status from `NEXT` (or `delivery_failed`) with an increasing `seq`. Publishes `TrackingChanged {shipment_id, order_id, kind, status, return_case_id}`.
      - Forward `delivered` → `order.transition(Delivered, actor=None, reason="carrier proof of delivery")`.
      - Forward fail → `DeliveryException`.
    - `has_delivery_event(order_id) -> bool`
    - `reattempt(actor, shipment) -> Order`: DeliveryException → Shipped, appending an `in_transit` event. The seller can also cancel from DeliveryException via `reject`, which then accepts DeliveryException as well as Confirmed.
    - `pickup_overdue(shipment) -> bool`
    - `shipments_of(order)`
  - `seller.service` fulfilment commands. Each one verifies the shop owner (via `order.get_for_shop_owner`) and audits:
    - `accept(seller, order_id) -> Order` (Confirmed→Preparing)
    - `pack(seller, order_id, weight_g) -> Shipment` (create_shipment + →ReadyToShip)
    - `hand_over(seller, order_id) -> Order` (→Shipped; the first tracking event is `picked_up`)
    - `reject(seller, order_id, reason) -> Order` (Confirmed→Cancelled + the same compensation as customer cancel; reason required)
    - `resolve_cancel(...)`: delegates to Task 9.
  - Routes (`/seller`, seller role):
    - `GET /seller/` dashboard: counts by status, pickup-overdue alerts, shop switcher if the seller owns several shops.
    - `GET /seller/orders?status=`
    - `GET /seller/orders/<id>`
    - `POST /seller/orders/<id>/{accept,pack,handover,reject,cancel-approve,cancel-decline}`
    - `GET /seller/labels/<tracking_no>`: a printable label (order id, address snapshot, weight, tracking number).
  - Route `POST /logistics/shipments/<id>/advance?fail=0|1`: the "fake carrier" button. Any logged-in user can trigger it; it's shown on the seller and customer order detail pages under a "Carrier simulator" heading.

- [ ] **Step 1: Write the failing tests**

```python
def test_fulfil_to_delivered(seeded, alice):
    o = paid_order(alice, "P03", 1); s = seller_user("sportzone@demo")
    seller.accept(s, o.id); sh = seller.pack(s, o.id, 800); seller.hand_over(s, o.id)
    assert o.status == "Shipped"
    while not logistics.has_delivery_event(o.id): logistics.advance(sh)
    assert o.status == "Delivered" and o.delivered_at is not None
    assert [e.seq for e in sh.events] == sorted(e.seq for e in sh.events)

def test_cannot_hand_over_cancelled(seeded, alice):
    o = paid_order(alice, "P03", 1); s = seller_user("sportzone@demo")
    seller.reject(s, o.id, "out of stock")
    with pytest.raises(IllegalTransition): seller.hand_over(s, o.id)

def test_other_seller_gets_404(client, seeded, alice, login):        # Review Focus 1
    o = paid_order(alice, "P03", 1); login(client, seller_user("techhub@demo"))
    assert client.post(f"/seller/orders/{o.id}/accept").status_code == 404 and o.status == "Confirmed"

def test_delivery_failure(seeded, alice):
    o = shipped_order(alice, "P03")                   # helper built from the steps above
    logistics.advance(o.shipments[0], fail=True); assert o.status == "DeliveryException"
```

- [ ] **Step 2–4:** fail → implement → pass.
- [ ] **Step 5: Commit** (`feat: seller fulfilment, shipments and carrier simulator`)

---

### Task 11: Reviews (BR06)

**Files:**
- Create: `modules/review/{models,service,routes}.py`, `templates/customer/review_form.html`; modify `templates/customer/product.html` (review list) and `templates/seller/` (a reviews page)
- Test: `tests/test_review.py`

**Interfaces:**
- Produces:
  - `Review` with `UniqueConstraint(order_item_id)`.
  - `review.service`:
    - `create_review(customer, order_item_id, rating: int, comment: str) -> Review`: the item must belong to the customer and the order status must be in `{Delivered, Completed}`, else `NotEligible`. Rating must be 1–5. Updates `Offer.rating_avg/rating_count`.
    - `reply(seller, review_id, text) -> Review`: shop owner only.
    - `set_hidden(actor, review_id, hidden: bool, reason) -> Review`: admin; audited.
    - `reviews_for_product(product_id)`: visible reviews only.
  - Routes:
    - `GET/POST /orders/<order_id>/items/<item_id>/review` (customer)
    - `GET /seller/reviews`, `POST /seller/reviews/<id>/reply`

- [ ] **Step 1: Write the failing tests**

```python
def test_review_requires_delivery(seeded, alice):
    o = paid_order(alice, "P03", 1)
    with pytest.raises(NotEligible): review.create_review(alice, o.items[0].id, 5, "great")

def test_one_review_per_item_and_rating_updates(seeded, alice):
    o = delivered_order(alice, "P03"); review.create_review(alice, o.items[0].id, 3, "ok")
    with pytest.raises((NotEligible, IntegrityError)): review.create_review(alice, o.items[0].id, 5, "again")
    assert catalog.get_offer(offer_id("P03")).rating_count == 1

def test_seller_reply(seeded, alice):
    o = delivered_order(alice, "P03"); r = review.create_review(alice, o.items[0].id, 4, "nice")
    review.reply(seller_user("sportzone@demo"), r.id, "thanks"); assert r.seller_reply == "thanks"
```

Rating math is incremental: `new_avg = (avg*count + rating)/(count+1)`. The seeded rating values stand for historical reviews, and `rating_count` in the seed is 0 for every product (the table's rating is the starting average), so this test's count assertion is exact.

- [ ] **Step 2–4:** fail → implement → pass.
- [ ] **Step 5: Commit** (`feat: verified-purchase reviews and seller replies`)

---

### Task 12: Returns, refunds, disputes (UC05)

**Files:**
- Create: `modules/returns/{models,service,routes}.py`, `templates/customer/{return_form,return_detail}.html`, `templates/seller/{returns,return_detail}.html`
- Test: `tests/test_returns.py`

**Interfaces:**
- Produces:
  - Models per spec §3: `ReturnCase`, `ReturnCaseItem`, `Evidence`, `DisputeDecision`.
  - ReturnCase statuses: `requested`, `proposed`, `accepted`, `awaiting_return`, `inspecting`, `inspection_failed`, `seller_rejected`, `disputed`, `refund_pending`, `refunded`, `closed`.
  - Each status change publishes `ReturnStatusChanged {case_id, order_id, status}` and records audit + an Evidence row of kind `statement` from the system.
  - `returns.service`:
    - `check_eligibility(customer, order, items: dict[int, int]) -> None`: raises `NotEligible(reason)` with exact reasons: "Order is not delivered", "Return window has closed", "Quantity exceeds purchased", "An open case already exists for this item".
    - `open_case(customer, order_id, items: dict[int, int], reason: str, remedy: str, statement: str, image: FileStorage | None = None) -> ReturnCase`: order → ReturnRequested; `seller_deadline = now + seller_response_hours`.
    - `save_evidence_image(file) -> str`: only `image/png` and `image/jpeg` by magic bytes (`\x89PNG`, `\xff\xd8\xff`), ≤ 2 MB, else `ValidationError`. Saves as `static/uploads/<uuid>.<ext>` and returns the URL.
    - `refund_amount(case) -> int`: Σ(unit_price × qty − item.discount_vnd × qty // item.qty), plus the order's `shipping_vnd` when every item is fully returned.
    - `seller_respond(seller, case_id, action: "accept"|"propose"|"reject", reason: str, amount_vnd: int | None = None) -> ReturnCase`:
      - accept + refund_only → `execute_refund`.
      - accept + return_and_refund → `awaiting_return` and `logistics.create_shipment(order, 0, kind="return", return_case=case)`.
      - propose → `proposed` with an amount ≤ refund_amount.
      - reject → `seller_rejected` (reason required).
    - `accept_proposal(customer, case_id) -> ReturnCase` → `execute_refund(case, amount=proposed)`.
    - Subscriber `TrackingChanged` with kind `return` and status `delivered` → case `inspecting`.
    - `inspect(seller, case_id, passed: bool, note) -> ReturnCase`: passed → `execute_refund`; failed → `inspection_failed`.
    - `escalate(customer, case_id, statement) -> ReturnCase`: allowed from `seller_rejected`, `inspection_failed`, `proposed`, or `requested` past `seller_deadline` → `disputed`.
    - `decide_dispute(agent, case_id, outcome, reason_code: str, amount_vnd: int | None, note: str) -> DisputeDecision`:
      - Only once per case.
      - refund_customer → `execute_refund(full)`. partial → `execute_refund(amount)`.
      - side_with_seller → case `closed`, order → `Rejected`.
    - `execute_refund(case, amount_vnd: int | None = None) -> Refund`: `payment.refund(captured.id, amount, f"return-{case.id}", case.id)` → case `refunded`, `refund_amount_vnd` set, order → `Refunded`. (Task 18 inserts the risk check here; leave a single call site.)
    - `can_escalate(case) -> bool`
  - Routes:
    - Customer: `GET/POST /orders/<id>/return`, `GET /returns/<id>` (timeline of Evidence + statuses, escalate button, accept-proposal button), `POST /returns/<id>/{escalate,accept-proposal,evidence}`.
    - Seller: `GET /seller/returns`, `GET /seller/returns/<id>`, `POST /seller/returns/<id>/{respond,inspect}`.

- [ ] **Step 1: Write the failing tests**

```python
def test_eligibility_reasons(seeded, alice):
    o = paid_order(alice, "P03", 1)
    with pytest.raises(NotEligible, match="not delivered"): returns.open_case(alice, o.id, {o.items[0].id: 1}, "r", "refund_only", "s")
    o2 = delivered_order(alice, "P03")
    with pytest.raises(NotEligible, match="Quantity"): returns.open_case(alice, o2.id, {o2.items[0].id: 9}, "r", "refund_only", "s")
    policy.advance_clock(8 * 24)
    with pytest.raises(NotEligible, match="window"): returns.open_case(alice, o2.id, {o2.items[0].id: 1}, "r", "refund_only", "s")

def test_refund_only_accept(seeded, alice):
    o = delivered_order(alice, "P03"); c = returns.open_case(alice, o.id, {o.items[0].id: 1}, "broken", "refund_only", "sole broke")
    returns.seller_respond(seller_user("sportzone@demo"), c.id, "accept", "sorry")
    assert c.status == "refunded" and o.status == "Refunded" and c.refund_amount_vnd == returns.refund_amount(c)

def test_return_shipment_inspection(seeded, alice):
    o = delivered_order(alice, "P03"); s = seller_user("sportzone@demo")
    c = returns.open_case(alice, o.id, {o.items[0].id: 1}, "size", "return_and_refund", "too small")
    returns.seller_respond(s, c.id, "accept", "ok"); sh = c_return_shipment(c)
    while c.status != "inspecting": logistics.advance(sh)
    returns.inspect(s, c.id, True, "fine"); assert c.status == "refunded"

def test_reject_escalate_decide(seeded, alice, make_user):
    o = delivered_order(alice, "P03"); c = returns.open_case(alice, o.id, {o.items[0].id: 1}, "fake", "refund_only", "not genuine")
    returns.seller_respond(seller_user("sportzone@demo"), c.id, "reject", "item is genuine")
    returns.escalate(alice, c.id, "photos attached"); assert c.status == "disputed"
    returns.decide_dispute(make_user("support"), c.id, "side_with_seller", "EVIDENCE_INSUFFICIENT", None, "")
    assert c.status == "closed" and o.status == "Rejected"
    with pytest.raises(NotEligible): returns.decide_dispute(make_user("support"), c.id, "refund_customer", "X", None, "")

@pytest.mark.parametrize("data,ok", [(b"\x89PNG\r\n\x1a\n" + b"0"*10, True), (b"MZ\x90\x00", False), (b"\xff\xd8\xff" + b"0" * (2*1024*1024+1), False)])
def test_evidence_upload_validation(app, data, ok):          # Review Focus 5
    f = FileStorage(stream=io.BytesIO(data), filename="e.png")
    if ok: assert returns.save_evidence_image(f).startswith("/static/uploads/")
    else:
        with pytest.raises(ValidationError): returns.save_evidence_image(f)
```

- [ ] **Step 2–4:** fail → implement → pass. Set `UPLOAD_DIR` in config; tests use `tmp_path` via the app config.
- [ ] **Step 5: Commit** (`feat: returns, refunds and dispute escalation`)

---

### Task 13: Settlement ledger (BR08)

**Files:**
- Create: `modules/settlement/{models,service,routes}.py`, `templates/seller/settlement.html`
- Test: `tests/test_settlement.py`

**Interfaces:**
- Produces:
  - `LedgerEntry` per spec §3.
  - Subscriber `OrderStatusChanged` (consumer `settlement`) handles three cases:
    - to=`Delivered` → `post_delivery(order)`. The entry_group is `f"order-{id}"` and all entries are `held`. Shop discount and platform discount come from the order's shop line (`shop_discount_vnd`, `platform_discount_vnd`, per Task 6), stored on Order as two columns of the same names. `fee = (merch − shop_disc) * platform_fee_pct // 100`. Entries:
      - Dr `customer_payment` = order.total
      - Dr `voucher_funding` = platform_disc
      - Cr `seller_payable` = merch − shop_disc − fee
      - Cr `platform_fee` = fee
      - Cr `shipping` = shipping
    - to=`Refunded` → `post_refund(order, amount)`: Dr `seller_payable`, Cr `refund`, held.
    - to=`Completed` → mark all of the order's entries `released`.
  - `settlement.service`:
    - `is_balanced(order_id) -> bool`
    - `release_eligible(actor) -> int`: Delivered orders with `now > delivered_at + return_window_days` and no open return case → transition `Completed`; returns the count.
    - `statement(shop) -> dict`: keys `held_vnd`, `released_vnd`, `fees_vnd`, `refunds_vnd`, `entries`.
  - Route `GET /seller/settlement` (statement table + totals).

- [ ] **Step 1: Write the failing tests**

```python
def test_delivery_posts_balanced_held_entries(seeded, alice):
    o = delivered_order(alice, "P03"); assert settlement.is_balanced(o.id)
    assert {e.status for e in LedgerEntry.query.filter_by(order_id=o.id)} == {"held"}

def test_release_after_window(seeded, alice, make_user):
    o = delivered_order(alice, "P03"); assert settlement.release_eligible(make_user("admin")) == 0
    policy.advance_clock(8 * 24); assert settlement.release_eligible(make_user("admin")) == 1
    assert o.status == "Completed"
    assert settlement.statement(o.shop)["released_vnd"] > 0

def test_open_return_blocks_release(seeded, alice, make_user):
    o = delivered_order(alice, "P03"); returns.open_case(alice, o.id, {o.items[0].id: 1}, "r", "refund_only", "s")
    policy.advance_clock(8 * 24); assert settlement.release_eligible(make_user("admin")) == 0
```

- [ ] **Step 2–4:** fail → implement → pass.
- [ ] **Step 5: Commit** (`feat: double-entry settlement ledger with hold and release`)

---

### Task 14: End-to-end journey + demo seed

**Files:**
- Modify: `seed.py` (`seed_demo_orders()`, `run()`)
- Test: `tests/test_e2e.py`

**Interfaces:**
- `seed.run()`: `ensure_defaults(); seed_catalog(); seed_promotions(); seed_demo_orders()`.
- `seed_demo_orders()` uses the services, never raw inserts, so every invariant holds. For Alice:
  - one Completed order (P11): created and delivered first, then the clock is advanced 8 days and `release_eligible` runs. The clock is not reset; all later seed orders are created after the advance, so their timestamps stay in order.
  - one Delivered order (P01) with an open `requested` return case
  - one Shipped order (P07)
  - one Confirmed order (P12) awaiting seller acceptance
  - one Delivered order (P03) with no review, ready for the review demo
- Pending moderation products, risk alerts and chats are added by later tasks' seed functions, appended to `run()`.

- [ ] **Step 1: Write the failing test** `test_full_customer_journey(client)` using only HTTP routes and the demo logins:
  1. Alice searches "black sneakers" and adds P03 ×2 to the cart.
  2. Quote with `SALE10,SPORT80` and assert the page shows `1,646,000`.
  3. Place the order, then pay with the Success button.
  4. Log in as SportZone: accept → pack (800 g) → hand over → carrier advance until delivered.
  5. Alice reviews the item, then opens a refund_only return.
  6. SportZone accepts.
  7. Assert the order page shows "Refunded", Alice's notifications ≥ 5, and `settlement.is_balanced(order.id)`.

  Also add `test_seed_runs_clean(app)`: `seed.run()` then assert `Order.query.count() >= 5` and every Delivered/Completed order is balanced.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_e2e.py -v` → expect failures in seed or routes. Fix route/template gaps found (no service changes needed unless a bug is found; if so, add a unit test in the owning module first).
- [ ] **Step 3: Manual smoke.** Run `.venv/bin/flask --app marketplacex.app seed && .venv/bin/flask --app marketplacex.app run` and click through the same journey as Alice and SportZone. Expected: no 500s.
- [ ] **Step 4: Run the full suite** → all pass.
- [ ] **Step 5: Commit** (`test: end-to-end journey and demo seed`). **The core demo is complete here.**

---

### Task 15: Seller Center — shop, listings (UC03), inventory and price

**Files:**
- Modify: `modules/seller/{service,routes}.py`, `modules/catalog/service.py`; create `templates/seller/{shop,products,product_form,inventory}.html`
- Test: `tests/test_seller_catalog.py`

**Interfaces:**
- Produces:
  - `seller.service.update_shop(seller, shop_id, name, location) -> Shop`
  - `seller.service.submit_verification(seller, shop_id, info: str) -> Shop` (→ `pending`)
  - `seller.service.create_shop` (Task 2) is exposed via the UI.
  - `catalog.service.validate_listing(category, title, attributes, variants) -> list[str]` returns error messages (empty = valid) for:
    - a missing required attribute from `category.attribute_schema`
    - a prohibited term (policy `prohibited_terms`) in title or description, case-insensitive
    - duplicate variant names
    - `price_vnd <= 0`
    - `original_price_vnd` present and `< price_vnd`
    - `stock < 0`
    - any shop that is not `verified`
  - `catalog.service.save_listing(seller, shop_id, data: dict, product_id: int | None = None, submit: bool = False) -> Product`: draft save, or validate + `pending` when `submit`. Errors → `ValidationError("; ".join(errors))`. Editing an active product's title/attributes sends it back to `pending`; price/stock edits don't.
  - `seller.service.update_offer(seller, offer_id, price_vnd, original_price_vnd, stock, purchase_limit, version) -> Offer`: optimistic version → `StaleVersion`; audited.
  - Routes:
    - `GET/POST /seller/shop`, `POST /seller/shop/verify`
    - `GET /seller/products`: status badges plus the moderation reason.
    - `GET/POST /seller/products/new`, `GET/POST /seller/products/<id>/edit`: dynamic variant rows via a small JS "add row"; attributes as key/value rows prefilled from the category schema.
    - `GET /seller/inventory`, `POST /seller/inventory/<offer_id>`
- Seed: add one SportZone product "Replica Running Shoes" in `pending`, so admin moderation has data.

- [ ] **Step 1: Write the failing tests**

```python
def test_listing_validation_messages(seeded):
    errs = catalog.validate_listing(cat("Shoes"), "Counterfeit Nike", {"color": "black"},
                                    [{"name": "A", "price_vnd": 0, "stock": 1}, {"name": "A", "price_vnd": 5, "stock": 1}])
    assert any("size" in e for e in errs) and any("prohibited" in e.lower() for e in errs)
    assert any("duplicate" in e.lower() for e in errs) and any("price" in e.lower() for e in errs)

def test_submit_goes_pending(seeded):
    p = catalog.save_listing(seller_user("sportzone@demo"), shop_id("SportZone"), valid_listing_data(), submit=True)
    assert p.status == "pending"

def test_unverified_shop_cannot_submit(seeded):
    s = seller_user("sportzone@demo"); sh = seller_svc.create_shop(s, "New", "Hue")
    with pytest.raises(ValidationError): catalog.save_listing(s, sh.id, valid_listing_data(), submit=True)

def test_update_offer_stale(seeded):
    o = catalog.get_offer(offer_id("P03"))
    with pytest.raises(StaleVersion): seller_svc.update_offer(seller_user("sportzone@demo"), o.id, 1, None, 1, 5, o.version - 1)
```

- [ ] **Step 2–4:** fail → implement → pass.
- [ ] **Step 5: Commit** (`feat: seller shop profile, listing publication and inventory`)

---

### Task 16: Admin Portal — taxonomy, campaigns, policy, governance, reports

**Files:**
- Create: `modules/admin/{routes,service}.py` (replace the stub), `modules/reporting/service.py`, `templates/admin/{dashboard,categories,campaigns,policy,moderation,users,reports}.html`
- Test: `tests/test_admin.py`

**Interfaces:**
- Produces. Every admin mutation requires `reason` (form field; empty → `ValidationError("Reason is required")`) and calls `audit.record`.
  - `admin.service`:
    - `save_category(actor, data, id=None) -> Category`, `delete_category(actor, id, reason)` (refuses if it has products)
    - `save_campaign(actor, data, id=None)`, `save_voucher(actor, data, id=None)`
    - `moderate_listing(actor, product_id, approve: bool, reason)` → `catalog.set_status(active|rejected)` with `moderation_reason`
    - `verify_shop(actor, shop_id, approve, reason)`
    - `suspend_user(actor, user_id, suspend: bool, reason)`
    - `set_review_hidden(...)`: delegates to Task 11
    - `run_settlement(actor) -> int`: delegates to `settlement.release_eligible`
  - Bulk action (§4.4): `bulk_moderate_preview(product_ids) -> list[Product]` and `bulk_moderate(actor, product_ids, approve, reason) -> dict(job_id, done, failed)`. The UI shows the affected list on a confirmation page before executing.
  - `reporting.service`. Each function returns plain dicts/ints:
    - `orders_by_status() -> dict[str, int]`
    - `avg_paid_to_packed_hours() -> float | None`: from history Confirmed→ReadyToShip
    - `cancellations_by_actor() -> dict[str, int]`: role of the history actor, or "system"
    - `refund_aging() -> list[dict(case_id, age_hours, status)]`: open cases
    - `payment_mismatches() -> list[str]`: captured attempts whose group has no Confirmed+ order, and Confirmed+ orders without a captured payment
    - `zero_result_rate() -> float`: from SearchTrace
    - `notification_failure_rate() -> float`
    - `inventory_oversell() -> int`: the number of orders cancelled by a seller with a reason containing "stock" (an oversell attributed to the seller)
  - Routes (`/admin`, admin role):
    - `GET /admin/`: dashboard with the reporting numbers (use the `dataviz` skill only if adding charts; plain stat tiles are enough)
    - `GET/POST /admin/categories`
    - `GET/POST /admin/campaigns`
    - `GET/POST /admin/policy`: includes "Fast-forward clock N hours", "Reset clock" and "Run settlement release".
    - `GET /admin/moderation`: pending listings, pending shops, reported reviews (all visible reviews with rating ≤ 2).
    - `POST /admin/moderation/...`
    - `GET/POST /admin/users`
    - `GET /admin/audit`: the latest 200 AuditEvents.

- [ ] **Step 1: Write the failing tests**

```python
def test_moderation_requires_reason(seeded, make_user):
    p = pending_product()
    with pytest.raises(ValidationError): admin.moderate_listing(make_user("admin"), p.id, True, "")
    admin.moderate_listing(make_user("admin"), p.id, False, "prohibited term")
    assert p.status == "rejected" and AuditEvent.query.filter_by(action="listing.reject").count() == 1

def test_suspended_user_cannot_login(seeded, make_user):
    admin.suspend_user(make_user("admin"), alice_user().id, True, "fraud")
    with pytest.raises(ValidationError): identity.authenticate("alice@demo", "demo123")

def test_reports_shape(seeded, alice):
    paid_order(alice, "P03", 1); r = reporting.orders_by_status()
    assert r.get("Confirmed", 0) >= 1 and reporting.payment_mismatches() == []

def test_admin_pages_render(client, seeded, login, make_user):
    login(client, make_user("admin"))
    for u in ["/admin/", "/admin/categories", "/admin/campaigns", "/admin/policy", "/admin/moderation", "/admin/users", "/admin/audit"]:
        assert client.get(u).status_code == 200, u
```

- [ ] **Step 2–4:** fail → implement → pass.
- [ ] **Step 5: Commit** (`feat: admin portal with governance, policy and operational reports`)

---

### Task 17: Support console — cases, masking, dispute decisions

**Files:**
- Create: `modules/support/{models,service,routes}.py`, `templates/support/{dashboard,case,dispute,customer}.html`; modify the customer order detail ("Contact support" form)
- Test: `tests/test_support.py`

**Interfaces:**
- Produces:
  - `SupportCase`, `CaseNote` per spec.
  - `support.service`:
    - `open_case(customer, order_id | None, subject, body) -> SupportCase`
    - `search(agent, q: str) -> dict(customers, orders, cases)`: matches email, name, order id or case id
    - `mask_email("alice@demo") -> "a***@demo"`, `mask_phone("0912345678") -> "******5678"`
    - `reveal(agent, user_id, field: "email"|"phone", reason) -> str`: reason required; audited as `pii.reveal`
    - `add_note(agent, case_id, body)`, `set_status(agent, case_id, status, reason)`, `assign(agent, case_id)`
    - `disputes() -> list[ReturnCase]` (status `disputed`)
    - `timeline(case_id) -> list`: the merged, chronological order history, return evidence, notes and decisions. Every call is audited as `case.view` (a privileged read, per report §9.4).
  - Routes (`/support`, support role):
    - `GET /support/` (search box, open cases, disputes queue)
    - `GET /support/customers/<id>` (masked)
    - `POST /support/customers/<id>/reveal`
    - `GET /support/cases/<id>`, `POST /support/cases/<id>/{note,status,assign}`
    - `GET /support/disputes/<return_case_id>`: immutable timeline and evidence images
    - `POST /support/disputes/<id>/decide` → `returns.decide_dispute`
  - Customer: `POST /orders/<id>/support` opens a case.
  - Order-level dispute (spec §3.1, "item not received"):
    - `support.report_not_received(customer, order_id, statement) -> SupportCase`: only on a Delivered order; order → `Disputed`.
    - `support.resolve_order_dispute(agent, order_id, refund: bool, reason_code) -> Order`: refund → `payment.refund(full order total)` + order → `Refunded`; otherwise → `Completed`.
    - Routes: `POST /orders/<id>/not-received` (customer) and `POST /support/orders/<id>/resolve` (agent).

- [ ] **Step 1: Write the failing tests**

```python
def test_masking_and_reveal_audited(seeded, make_user):
    agent = make_user("support"); html_user = support.search(agent, "alice")["customers"][0]
    assert support.mask_email(html_user.email) == "a***@demo"
    with pytest.raises(ValidationError): support.reveal(agent, html_user.id, "email", "")
    assert support.reveal(agent, html_user.id, "email", "verify identity on call") == "alice@demo"
    assert AuditEvent.query.filter_by(action="pii.reveal").count() == 1

def test_customer_page_masks(client, seeded, login, make_user):
    login(client, make_user("support")); html = client.get(f"/support/customers/{alice_user().id}").get_data(as_text=True)
    assert "alice@demo" not in html and "a***@demo" in html

def test_dispute_decision_via_console(client, seeded, alice, login, make_user):
    c = disputed_case(alice)                              # helper from Task 12 steps
    login(client, make_user("support"))
    client.post(f"/support/disputes/{c.id}/decide", data={"outcome": "refund_customer", "reason_code": "SELLER_FAULT", "note": "photos clear"})
    assert c.status == "refunded"

def test_not_received_dispute(seeded, alice, make_user):
    o = delivered_order(alice, "P07"); support.report_not_received(alice, o.id, "never arrived")
    assert o.status == "Disputed"
    support.resolve_order_dispute(make_user("support"), o.id, True, "CARRIER_LOSS"); assert o.status == "Refunded"
```

- [ ] **Step 2–4:** fail → implement → pass.
- [ ] **Step 5: Commit** (`feat: support console with masking and dispute decisions`)

---

### Task 18: Risk — rules, alerts, hold/release

**Files:**
- Modify: `modules/risk/{models,service}.py`; create `modules/risk/routes.py`, `templates/risk/{dashboard,alert}.html`; modify `modules/returns/service.py:execute_refund` (one call site); modify `seed.py` (one open alert)
- Test: `tests/test_risk.py`

**Interfaces:**
- Produces:
  - `RiskAlert` per spec, plus `context: JSON`.
  - `risk.service`:
    - `evaluate_checkout(customer, group) -> "approved"|"held"`. Rules, all thresholds from policy:
      - `HIGH_VALUE`: total > `risk_max_order_vnd`
      - `VOUCHER_VELOCITY`: committed redemptions in the last 24h ≥ `risk_max_vouchers_per_day`
      - `NEW_ACCOUNT_HIGH_VALUE`: account < 24h old and total > 5,000,000
      - The first matching rule creates a `RiskAlert(target_type="checkout", target_id=group.id, status="held")`, publishes `RiskDecisionMade`, and returns "held".
    - `evaluate_refund(customer, case, amount) -> "approved"|"held"`: successful refunds in the last 30 days ≥ `risk_max_refunds_30d` → alert (`target_type="refund"`); the case status becomes `refund_pending`.
    - `release(analyst, alert_id, reason)`: checkout → `checkout.continue_after_risk(group)` (the customer then pays from their order page via a "Pay now" link to `/payments/<id>/pay`); refund → `returns.execute_refund(case, case.pending_amount_vnd)`.
    - `reject(analyst, alert_id, reason)`: checkout → `checkout.compensate(group, "Rejected by risk review")`; refund → case `closed` with a note.
    - `dismiss(...)` is an alias of release for non-holding alerts.
    - All of these require a reason and are audited.
  - `returns.service.execute_refund`: call `risk.evaluate_refund` first. Held → store `pending_amount_vnd` (new column) and status `refund_pending`, and return None.
  - Routes (`/risk`, risk role): `GET /risk/` (alert queue with filters open/held/all), `GET /risk/alerts/<id>` (context, customer history counts), `POST /risk/alerts/<id>/{release,reject}`.
  - Customer order page: for a held group, show "Under review"; after release, a "Pay now" link.
  - Seed: one held checkout alert for Alice (cart P05 ×4 = 25,960,000 > 20M), created via services.

- [ ] **Step 1: Write the failing tests**

```python
def test_high_value_checkout_held_then_released(seeded, alice, make_user):
    cart.add_item(alice, offer_id("P05"), 4); g = checkout.quote(alice, alice.addresses[0].id, [])
    checkout.place_order(alice, g.id, "k", g.quote_hash)
    a = RiskAlert.query.one(); assert a.rule == "HIGH_VALUE" and g.status == "placing"
    assert PaymentAttempt.query.count() == 0
    risk.release(make_user("risk"), a.id, "customer verified by phone")
    assert PaymentAttempt.query.count() == 1

def test_reject_compensates(seeded, alice, make_user):
    cart.add_item(alice, offer_id("P05"), 4); g = checkout.quote(alice, alice.addresses[0].id, [])
    checkout.place_order(alice, g.id, "k", g.quote_hash)
    risk.reject(make_user("risk"), RiskAlert.query.one().id, "stolen card pattern")
    assert inventory.get_ledger(offer_id("P05")).reserved == 0 and g.status == "failed"

def test_refund_velocity_holds(seeded, alice, monkeypatch):
    monkeypatch.setattr(policy, "get_int", lambda k: 0 if k == "risk_max_refunds_30d" else DEFAULTS[k])
    o = delivered_order(alice, "P03"); c = returns.open_case(alice, o.id, {o.items[0].id: 1}, "r", "refund_only", "s")
    returns.seller_respond(seller_user("sportzone@demo"), c.id, "accept", "ok")
    assert c.status == "refund_pending" and RiskAlert.query.filter_by(target_type="refund").count() == 1
```

`DEFAULTS` is exported from `admin/policy.py`.

- [ ] **Step 2–4:** fail → implement → pass (the full suite stays green, since the seed adds an alert; Task 14's `test_seed_runs_clean` must still pass).
- [ ] **Step 5: Commit** (`feat: risk rules with hold, release and reject`)

---

### Task 19: Chat (customer ↔ seller)

**Files:**
- Create: `modules/chat/{models,service,routes}.py`, `templates/customer/chat.html`, `templates/seller/chat.html`; seed one conversation
- Test: `tests/test_chat.py`

**Interfaces:**
- Produces:
  - `Conversation` with `UniqueConstraint(customer_id, shop_id)`, and `ChatMessage`.
  - `chat.service`:
    - `get_or_create(customer, shop_id) -> Conversation`
    - `send(user, conversation_id, body: str) -> ChatMessage`: participant only, else `NotFound`; body 1–1000 chars, stripped. Notifies the other party (template `chat_message`).
    - `conversations_for(user) -> list[Conversation]`: customer → theirs; seller → their shops'.
    - `messages(user, conversation_id) -> list[ChatMessage]`
  - Routes:
    - `POST /chat/start` (shop_id) → redirect
    - `GET /chat`, `GET /chat/<id>`, `POST /chat/<id>/send`: one template set; the page polls with `<meta http-equiv="refresh" content="10">` (no websockets)
    - Seller nav links to `/chat`.

- [ ] **Step 1: Write the failing tests**

```python
def test_customer_seller_chat(seeded, alice):
    c = chat.get_or_create(alice, shop_id("SportZone")); chat.send(alice, c.id, "Is size 42 available?")
    chat.send(seller_user("sportzone@demo"), c.id, "Yes")
    assert [m.body for m in chat.messages(alice, c.id)] == ["Is size 42 available?", "Yes"]

def test_outsider_cannot_read(seeded, alice):
    c = chat.get_or_create(alice, shop_id("SportZone"))
    with pytest.raises(NotFound): chat.messages(seller_user("techhub@demo"), c.id)
```

- [ ] **Step 2–4:** fail → implement → pass. **Step 5: Commit** (`feat: customer-seller chat`)

---

### Task 20: README with run instructions and traceability

**Files:**
- Create: `README.md`
- Test: `tests/test_traceability.py`

- [ ] **Step 1: Write the failing test.** Parse README.md and assert it has a row for each of: all 33 use case names from spec §5 (customer, seller, admin, support, risk and provider tables), `FR01`…`FR30` and `BR01`…`BR08`. Also assert that every `tests/test_*.py::name` reference in the README exists (grep the test files for `def name`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Write README.md** with:
  1. Setup and run: venv, `flask --app marketplacex.app seed`, `flask --app marketplacex.app run`, `pytest`.
  2. Demo accounts.
  3. A 5-minute demo script following Task 14's journey plus admin, support and risk.
  4. Architecture: Figure 2 component → module path table.
  5. Traceability tables: use case → route(s) → test; FR → module → test; BR → enforcement → test.
  6. The "Designed, not built" list copied from spec §9.
- [ ] **Step 4: Run the full suite** `.venv/bin/python -m pytest -q` → all pass.
- [ ] **Step 5: Commit** (`docs: README with demo script and report traceability`)
