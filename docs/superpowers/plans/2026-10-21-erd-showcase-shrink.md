# 8-Table ERD Showcase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Shrink MarketplaceX to a showcase of the `Picture1.png` ERD: exactly 8 tables (7 ERD + `Order`), no-password logins, session cart, simulated payment and self-advancing shipping, text/voice/image search.

**Architecture:** Same Flask modular monolith, stripped in place. Task 1 deletes every module, template, test and static asset outside the new scope and rewrites the models; Tasks 2–9 rebuild each remaining module as small, fresh files (`models.py` / `service.py` / `routes.py`); Task 10 rewrites the seed and `init-db`; Task 11 rebuilds Supabase.

**Tech Stack:** Python 3, Flask 3, Flask-SQLAlchemy, Pillow, psycopg2-binary, Bootstrap 5.3.3 (CDN, as today), pytest on in-memory SQLite.

**Spec:** `docs/superpowers/specs/2026-10-21-erd-showcase-shrink-design.md`

## Global Constraints

- Exactly 8 tables: `FullName`, `Address`, `Customer`, `SearchHistory`, `Category`, `Product`, `ProductImage`, `Order`. No other `db.Model` may exist anywhere.
- Table and column names verbatim from the spec (quoted CamelCase). Python attributes are snake_case, mapped with `db.Column("erdName", ...)` as the current code does. Never add a column to the 7 ERD tables.
- `ProductImage.imageUrl` is `String(500)`; `Product.description` is `String(255)`; ERD varchar columns are `String(255)`; keys are `Integer`.
- Value sets, exact strings: `searchType` ∈ `text`, `voice`, `image`; `paymentMethod` ∈ `cod`, `card`; `paymentStatus` ∈ `unpaid`, `paid`, `refunded`; `status` ∈ `placed`, `processing`, `shipped`, `delivered`, `cancelled`; session roles ∈ `customer`, `seller`, `admin`.
- Constants (in `marketplacex/modules/order/service.py`): `SHIPPING_FEE = 30_000`, `FREE_SHIPPING_FROM = 500_000`, `STEP_SECONDS = 20`, `DEMO_CARD = "4242424242424242"`. In `marketplacex/modules/identity/service.py`: `QUICK_CUSTOMER_EMAIL = "alice@demo"`. In `marketplacex/seed_tiki.py`: `UNBRANDED = "Unbranded"`.
- Time comes only from `marketplacex/clock.py`: call it as `clock.now()` after `from marketplacex import clock` (or relative), never `from ..clock import now`, so tests can monkeypatch `marketplacex.clock.now`. It returns naive UTC.
- Money is integer VND everywhere.
- Never stage or commit `marketplacex/config.py` (it holds the Supabase password and Gemini key locally). Stage files by explicit path; never `git add -A` or `git add .`.
- Test command: `.venv/bin/python -m pytest -q` (bare `pytest` cannot import `marketplacex`).
- Keep the current Bootstrap look; no visual redesign (the impeccable redesign is a later project).
- Every service function that writes commits its own transaction; read paths never commit except `order.service.advance_due`.

## Review Focus

1. Double-submitted checkout (double click, back button): the second POST finds an empty cart and is refused with "Your cart is empty"; no duplicate orders. Owned by Task 5.
2. Stock that dropped after a product was put in the cart: checkout refuses the whole cart naming the product, writes no rows, and leaves stock unchanged. Owned by Task 5.
3. Email typed with capitals or surrounding spaces at sign-up or login: it is stored and matched lowercase-trimmed. Owned by Task 2.
4. An order nobody looked at for an hour: the first read shows `delivered`, with `shippedAt`/`deliveredAt` equal to the due times, not the read time. Owned by Task 6.
5. A customer opening another customer's order URL, or a non-image file uploaded to photo search: a 404, or a flashed error and redirect, never a 500 and never someone else's data. Owned by Tasks 6 and 4.

---

### Task 1: Teardown, 8-table schema, app skeleton

**Files:**
- Delete: `marketplacex/modules/{audit,cases,chat,checkout,inventory,logistics,notification,payment,promotion,reporting,returns,review,settlement}/` (whole directories); `marketplacex/adapters/`; `marketplacex/events.py`; `marketplacex/seed.py`; `marketplacex/static/sample_images/`; `marketplacex/modules/admin/{models,policy,service,routes}.py`; `marketplacex/modules/seller/{models,service,routes}.py`; `marketplacex/modules/cart/{models,service,routes}.py`; `marketplacex/modules/order/{models,service,routes,state_machine}.py`; `marketplacex/modules/catalog/{service,routes}.py`; `marketplacex/modules/identity/{service,routes}.py`; `marketplacex/modules/search/{service,routes,ranking}.py`; `marketplacex/modules/assistant/{service,routes}.py`; every template except `base.html`, `error.html`, `_assistant.html`; every file in `tests/` except `conftest.py` (rewritten) and `test_tiki_snapshot.py` (keep if it still passes unchanged; delete otherwise). Keep `marketplacex/modules/search/{images,query}.py`, `marketplacex/tiki.py`, `marketplacex/data/tiki_catalog.json`, `marketplacex/static/{app.css,js/assistant.js}`, `scripts/fetch_tiki.py`.
- Rewrite: `marketplacex/modules/identity/models.py`, `marketplacex/modules/catalog/models.py`, `marketplacex/modules/search/models.py`, `marketplacex/app.py`, `marketplacex/auth.py`, `marketplacex/errors.py`, `marketplacex/templates/base.html`, `tests/conftest.py`
- Create: `marketplacex/clock.py`, `marketplacex/modules/order/models.py`, `tests/test_schema.py`
- `marketplacex/seed_tiki.py`: replace its body with a stub `def run(snapshot=None) -> dict: raise NotImplementedError` (rewritten in Task 10) so imports keep working.

**Interfaces:**
- Produces (models; attribute → column):
  - `identity.models.FullName`: `id`→`fullNameID`, `first_name`, `middle_name`, `last_name`; property `display -> str` (non-empty parts joined by spaces).
  - `identity.models.Address`: `id`→`addressID`, `ward`, `street`, `detail`; property `line -> str` = non-empty of `detail, street, ward` joined by `", "`.
  - `identity.models.Customer`: `id`→`customerID`, `full_name_id`, `address_id`, `email` (`String(255)`, unique, not null), `phone_number`; relationships `full_name`, `address`; property `name -> str` = `full_name.display`.
  - `catalog.models.Category`: `id`→`categoryID`, `name`, `description`; relationship `products` (dynamic or list, ordered by id).
  - `catalog.models.Product`: `id`→`productID`, `category_id`, `title`→`name`, `brand`→`brandName`, `description`, `price`, `stock_quantity`, `avg_rating`, `created_at`, `updated_at`; relationships `category`, `images` (ordered by `ProductImage.id`, cascade delete-orphan); properties `image_url -> str | None` (first image) and `image_vector -> list[float] | None` (unpacked first image vector).
  - `catalog.models.ProductImage`: `id`→`imageID`, `product_id`, `url`→`imageUrl`, `feature_vector`→`featureVector` (`LargeBinary`, nullable).
  - `search.models.SearchHistory`: `id`→`searchHistoryID`, `customer_id`, `keyword`, `search_type`→`searchType`, `searched_at`.
  - `order.models.Order` (`__tablename__ = "Order"`): `id`→`orderID`, `customer_id`, `product_id`, `address_id`, `quantity`, `unit_price`, `shipping_fee`, `total_price`, `payment_method`, `payment_status`, `status`, `ordered_at`, `shipped_at` (nullable), `delivered_at` (nullable); relationships `customer`, `product`, `address`.
- Produces (`marketplacex/clock.py`): `now() -> datetime` (naive UTC).
- Produces (`marketplacex/auth.py`): `current_role() -> str | None`, `current_customer() -> Customer | None` (cached on `g`; a `customer_id` whose row is gone counts as logged out), `login_customer(customer) -> None` (clears session, sets `role="customer"`, `customer_id`), `login_staff(role: str) -> None` (`"seller"` or `"admin"`), `logout() -> None` (clears session, including the cart), `require_role(*roles)` decorator (no role → redirect to `identity.login` with `next`; wrong role → `Forbidden`).
- Produces (`marketplacex/errors.py`): keep only `DomainError`, `Forbidden`, `NotFound`, `ValidationError`, `InsufficientStock`, `IllegalTransition`.
- Produces (`marketplacex/app.py`): `MODULES = ["identity", "catalog", "search", "cart", "order", "seller", "admin", "assistant"]`; keep `_import_optional`, the Postgres engine options, `vnd` and `dt` filters, `has_endpoint`; context processor provides `role`, `customer` (from `auth`) and `cart_count` (sum of quantities in `session.get("cart", {})`); keep `_register_errors`, `enable_rls`; `init-db` command stays registered but its body is replaced in Task 10 (for now: `db.create_all()` then `seed_tiki.run()`).
- Produces (`tests/conftest.py` fixtures): `app` (in-memory SQLite, `create_all`, config `TESTING`, `SECRET_KEY="t"`, `GEMINI_API_KEY=""`), `client`, `clock` (monkeypatches `marketplacex.clock.now`; object with `.now` datetime attribute starting at `datetime(2026, 10, 1, 12, 0, 0)` and `.advance(seconds: int)`), `demo` (see below), `login_as(client, role, customer=None)` (writes `role`/`customer_id` into the session).
- `demo` fixture creates and returns a `SimpleNamespace` with:
  - categories `phones` ("Phones") and `books` ("Books");
  - `iphone`: Phones, "Apple iPhone 15", brand "Apple", price 20_000_000, stock 5, rating 4.8, one image whose vector is `pack(feature_vector(solid_image((220, 30, 30))))`;
  - `galaxy`: Phones, "Samsung Galaxy S24", brand "Samsung", price 15_000_000, stock 3, rating 4.5, image vector of `solid_image((30, 30, 220))`;
  - `book`: Books, "Sách Đắc Nhân Tâm", brand "Unbranded", price 100_000, stock 50, rating 4.9, image vector of `solid_image((30, 200, 30))`;
  - `cheap`: Books, "Bookmark", brand "Unbranded", price 20_000, stock 0, rating 4.0, no images;
  - `alice`: Customer `alice@demo`, FullName ("Alice", "", "Nguyen"), phone "0912345678", Address (ward "Trang Tien", street "Trang Tien", detail "12, Hoan Kiem, Hanoi");
  - `binh`: Customer `binh@demo`, FullName ("Binh", "Van", "Tran"), own Address.

- [ ] **Step 1: Delete the files listed above.** Use `git rm -r` with explicit paths.

- [ ] **Step 2: Write the failing schema test** in `tests/test_schema.py`

```python
from sqlalchemy import inspect
from marketplacex.extensions import db

TABLES = {
    "FullName": {"fullNameID", "firstName", "middleName", "lastName"},
    "Address": {"addressID", "ward", "street", "detail"},
    "Customer": {"customerID", "fullNameID", "addressID", "email", "phoneNumber"},
    "SearchHistory": {"searchHistoryID", "customerID", "keyword", "searchType", "searchedAt"},
    "Category": {"categoryID", "name", "description"},
    "Product": {"productID", "categoryID", "name", "brandName", "description", "price", "stockQuantity",
                "avgRating", "createdAt", "updatedAt"},
    "ProductImage": {"imageID", "productID", "imageUrl", "featureVector"},
    "Order": {"orderID", "customerID", "productID", "addressID", "quantity", "unitPrice", "shippingFee",
              "totalPrice", "paymentMethod", "paymentStatus", "status", "orderedAt", "shippedAt", "deliveredAt"},
}

def test_exactly_eight_tables_with_exact_columns(app):
    insp = inspect(db.engine)
    assert set(insp.get_table_names()) == set(TABLES)
    for name, cols in TABLES.items():
        assert {c["name"] for c in insp.get_columns(name)} == cols, name

def test_foreign_keys(app):
    insp = inspect(db.engine)
    fks = {(t, fk["constrained_columns"][0], fk["referred_table"]) for t in TABLES for fk in insp.get_foreign_keys(t)}
    assert fks == {("Customer", "fullNameID", "FullName"), ("Customer", "addressID", "Address"),
                   ("SearchHistory", "customerID", "Customer"), ("Product", "categoryID", "Category"),
                   ("ProductImage", "productID", "Product"), ("Order", "customerID", "Customer"),
                   ("Order", "productID", "Product"), ("Order", "addressID", "Address")}

def test_image_url_and_description_lengths():
    from marketplacex.modules.catalog.models import Product, ProductImage
    assert ProductImage.__table__.c.imageUrl.type.length == 500
    assert Product.__table__.c.description.type.length == 255

def test_demo_fixture_and_app_boots(client, demo):
    assert demo.alice.name == "Alice Nguyen"
    assert demo.alice.address.line == "12, Hoan Kiem, Hanoi, Trang Tien, Trang Tien"
    assert demo.iphone.image_vector is not None and demo.cheap.image_url is None
    assert client.get("/no-such-page").status_code == 404
```

- [ ] **Step 3: Run it** — `.venv/bin/python -m pytest -q tests/test_schema.py`. Expected: FAIL (old models still define extra tables/columns, or import errors).

- [ ] **Step 4: Rewrite the models, `clock.py`, `auth.py`, `errors.py`, `app.py`, `base.html`, `conftest.py` per the Interfaces block.** `base.html`: keep the current layout; nav shows Log in / Sign up for visitors; Cart (with `cart_count`), My orders, Profile for customers; Seller Center for seller; Admin for admin; Log out (a POST form) when logged in; every nav link guarded with `has_endpoint(...)` so pages from later tasks appear as they land. Include `_assistant.html` for visitors and customers when `has_endpoint('assistant.chat')`. Keep `.mx-nav` and the footer, with footer text "Showcase of the MarketplaceX ERD — demo only."

- [ ] **Step 5: Run the whole suite** — `.venv/bin/python -m pytest -q`. Expected: all pass (`test_schema.py`, plus `test_tiki_snapshot.py` if kept). `grep -rn "db.Model" marketplacex` lists exactly the 8 model classes.

- [ ] **Step 6: Commit**

```bash
git add -u marketplacex tests ':!marketplacex/config.py'
git add marketplacex/clock.py marketplacex/modules/order/models.py tests/test_schema.py
git diff --cached --name-only | grep -x marketplacex/config.py && exit 1   # must print nothing
git commit -m "refactor: strip to the 8-table ERD schema"
```

---

### Task 2: Identity — no-password login, sign-up, profile

**Files:**
- Create: `marketplacex/modules/identity/service.py`, `marketplacex/modules/identity/routes.py`, `marketplacex/templates/auth/login.html`, `marketplacex/templates/auth/signup.html`, `marketplacex/templates/customer/profile.html`
- Test: `tests/test_identity.py`

**Interfaces:**
- Consumes: Task 1 models and `auth` functions.
- Produces (`identity.service`):
  - `QUICK_CUSTOMER_EMAIL = "alice@demo"`
  - `normalize_email(email: str) -> str` (strip + lower)
  - `find_by_email(email: str) -> Customer | None`
  - `signup(first_name, middle_name, last_name, email, phone, ward, street, detail) -> Customer` — all strings; `middle_name` optional; others required → `ValidationError("<Label> is required")` (labels: First name, Last name, Email, Phone, Ward, Street, Detail); email without `@` → `ValidationError("Enter a valid email")`; any field over 255 chars → `ValidationError("<Label> is too long")`; duplicate → `ValidationError("An account with this email already exists")`. Creates FullName, Address, Customer; commits.
  - `update_profile(customer, first_name, middle_name, last_name, phone, ward, street, detail) -> None` — same validation; updates the FullName row and phone in place; if any of ward/street/detail differs from the current address, inserts a new Address and repoints `customer.address_id`; otherwise inserts nothing. Commits.
- Produces (routes, blueprint `identity`): `GET /login` (`identity.login`), `POST /login/quick/<who>` (`who` ∈ customer/seller/admin; customer logs in as `QUICK_CUSTOMER_EMAIL`, flashing "Demo customer not found — run init-db" if missing), `POST /login/email` (unknown email → flash "No customer with that email" and back to login), `GET|POST /signup` (`identity.signup`), `POST /logout` (`identity.logout`), `GET|POST /profile` (`identity.profile`, customers only). Successful logins redirect to a safe `next` (path starting with `/` and not `//`) or `/`; seller → `/seller/products`, admin → `/admin` when no `next`.

- [ ] **Step 1: Write the failing tests** in `tests/test_identity.py`

```python
def test_quick_logins(client, demo):
    r = client.post("/login/quick/customer")
    with client.session_transaction() as s:
        assert s["role"] == "customer" and s["customer_id"] == demo.alice.id
    client.post("/logout")
    client.post("/login/quick/seller")
    with client.session_transaction() as s:
        assert s["role"] == "seller" and "customer_id" not in s
    client.post("/login/quick/admin")
    with client.session_transaction() as s:
        assert s["role"] == "admin"

def test_login_page_shows_three_buttons_and_email_box(client, demo):
    html = client.get("/login").get_data(as_text=True)
    assert "/login/quick/customer" in html and "/login/quick/seller" in html and "/login/quick/admin" in html
    assert 'name="email"' in html and 'type="password"' not in html

def test_email_login_is_case_insensitive_and_trimmed(client, demo):
    client.post("/login/email", data={"email": "  ALICE@Demo "})
    with client.session_transaction() as s:
        assert s["customer_id"] == demo.alice.id

def test_unknown_email_is_refused(client, demo):
    r = client.post("/login/email", data={"email": "nobody@demo"}, follow_redirects=True)
    assert "No customer with that email" in r.get_data(as_text=True)
    with client.session_transaction() as s:
        assert "role" not in s

def test_signup_creates_rows_and_logs_in(client, demo):
    from marketplacex.modules.identity.models import Customer
    client.post("/signup", data={"first_name": "Mai", "middle_name": "", "last_name": "Pham", "email": " Mai@Test.vn ",
                                 "phone": "0901", "ward": "Ben Nghe", "street": "Le Loi", "detail": "5, Quận 1, TP.HCM"})
    c = Customer.query.filter_by(email="mai@test.vn").one()
    assert c.name == "Mai Pham" and c.address.detail == "5, Quận 1, TP.HCM"
    with client.session_transaction() as s:
        assert s["customer_id"] == c.id

def test_signup_rejects_duplicate_and_missing(demo):
    import pytest
    from marketplacex.errors import ValidationError
    from marketplacex.modules.identity import service
    with pytest.raises(ValidationError, match="already exists"):
        service.signup("A", "", "B", "ALICE@demo", "1", "w", "s", "d")
    with pytest.raises(ValidationError, match="Street is required"):
        service.signup("A", "", "B", "new@demo", "1", "w", " ", "d")

def test_profile_address_change_creates_new_row(demo):
    from marketplacex.modules.identity import service
    old = demo.alice.address_id
    service.update_profile(demo.alice, "Alice", "", "Nguyen", "0912345678", "Trang Tien", "Trang Tien", "12, Hoan Kiem, Hanoi")
    assert demo.alice.address_id == old
    service.update_profile(demo.alice, "Alice", "", "Nguyen", "0999", "Ben Nghe", "Le Loi", "45, Quận 1, TP.HCM")
    assert demo.alice.address_id != old and demo.alice.phone_number == "0999"

def test_profile_requires_customer(client, demo, login_as):
    assert client.get("/profile").status_code == 302
    login_as(client, "seller")
    assert client.get("/profile").status_code == 403
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_identity.py` — Expected: FAIL (404s / import errors).
- [ ] **Step 3: Implement the service, routes and three templates.** Login page: three quick buttons as POST forms, an email form, and a "Sign up" link. Sign-up and profile forms use the field names in the tests; profile shows email read-only.
- [ ] **Step 4: Run** the file, then the full suite — Expected: PASS.
- [ ] **Step 5: Commit** (explicit paths) — `feat: no-password login, sign-up and profile`.

---

### Task 3: Catalogue browsing

**Files:**
- Create: `marketplacex/modules/catalog/service.py`, `marketplacex/modules/catalog/routes.py`, `marketplacex/templates/_cards.html`, `marketplacex/templates/customer/{home,category,product}.html`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes: Task 1 models.
- Produces (`catalog.service`):
  - `SORTS = ("rating", "price_asc", "price_desc", "newest")`
  - `categories() -> list[Category]` (by id)
  - `home_sections(per_category: int = 8) -> list[tuple[Category, list[Product]]]` (top by `avg_rating` desc, then id)
  - `category_products(category_id: int, sort: str = "rating", min_price: int | None = None, max_price: int | None = None, page: int = 1, per_page: int = 24) -> tuple[list[Product], int]` (products, total count; unknown sort → `"rating"`; images eager-loaded with `selectinload`)
  - `get_product(product_id: int) -> Product` (`NotFound("Product not found")`)
  - `get_category(category_id: int) -> Category` (`NotFound("Category not found")`)
- Produces (routes, blueprint `catalog`): `GET /` (`catalog.home`), `GET /categories/<int:category_id>` (`catalog.category`, query args `sort`, `min_price`, `max_price`, `page`), `GET /products/<int:product_id>` (`catalog.product`). `_cards.html` defines macro `product_card(p)` (image or placeholder, title, brand, price via `vnd`, rating, link). Product page: all images, price, stock ("Out of stock" at 0), rating, description, an "Add to cart" form posting to `/cart/add` shown only when `has_endpoint('cart.add')` and stock > 0, and a "Find similar" link to `/search?similar=<id>` when the product has a vector.

- [ ] **Step 1: Write the failing tests** in `tests/test_catalog.py`

```python
from marketplacex.modules.catalog import service

def test_category_sorting_and_price_filter(demo):
    items, total = service.category_products(demo.phones.id, sort="price_asc")
    assert [p.title for p in items] == ["Samsung Galaxy S24", "Apple iPhone 15"] and total == 2
    items, total = service.category_products(demo.phones.id, max_price=16_000_000)
    assert [p.title for p in items] == ["Samsung Galaxy S24"] and total == 1
    items, _ = service.category_products(demo.phones.id, sort="bogus")
    assert items[0].title == "Apple iPhone 15"   # falls back to rating

def test_pages_render(client, demo):
    assert "Apple iPhone 15" in client.get("/").get_data(as_text=True)
    assert "Samsung Galaxy S24" in client.get(f"/categories/{demo.phones.id}").get_data(as_text=True)
    html = client.get(f"/products/{demo.iphone.id}").get_data(as_text=True)
    assert "20,000,000" in html and f"/search?similar={demo.iphone.id}" in html
    assert "Out of stock" in client.get(f"/products/{demo.cheap.id}").get_data(as_text=True)

def test_missing_product_and_category_are_404(client, demo):
    assert client.get("/products/9999").status_code == 404
    assert client.get("/categories/9999").status_code == 404
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** service, routes, templates.
- [ ] **Step 4: Run** file and full suite — Expected: PASS.
- [ ] **Step 5: Commit** — `feat: catalogue home, category and product pages`.

---

### Task 4: Search — text, voice, image, similar, history

**Files:**
- Create: `marketplacex/modules/search/service.py`, `marketplacex/modules/search/ranking.py`, `marketplacex/modules/search/routes.py`, `marketplacex/templates/customer/search.html`
- Rewrite: `marketplacex/static/js/voice.js`
- Modify: `marketplacex/templates/base.html` (navbar search form gets the mic button and a hidden `mode` input)
- Keep unchanged: `search/images.py`, `search/query.py`
- Test: `tests/test_search.py`

**Interfaces:**
- Consumes: `query.build_query(mode, text=...) -> Query` (`terms`, `alts`, `max_price`); `images.feature_vector(bytes) -> list[float]` (raises `ValidationError("That file is not an image")`), `images.unpack`; `Product.image_vector`.
- Produces (`search.ranking`): `cosine(a, b) -> float`; `lexical(q: Query, product) -> float` (fraction of `q.terms` found, honouring `q.alts`, in the tokens of title + brand + category name + description; keep today's `_fraction` logic).
- Produces (`search.service`):
  - `IMAGE_MATCH_THRESHOLD = 0.5`, `MAX_RESULTS = 48`
  - `search_text(text: str) -> list[Product]` — products with `lexical > 0` and price ≤ `q.max_price` when parsed; ordered by lexical desc, `avg_rating` desc, id; at most `MAX_RESULTS`; text with no terms → `[]`.
  - `search_vector(vector: list[float], exclude_id: int | None = None) -> list[Product]` — cosine ≥ threshold, ordered by cosine desc then id; at most `MAX_RESULTS`.
  - `record(customer, keyword: str, search_type: str) -> None` — no-op when `customer` is None or keyword blank; keyword trimmed and cut to 255; `searched_at = clock.now()`; commits.
  - `recent(customer, limit: int = 8) -> list[SearchHistory]` (newest first).
- Produces (routes, blueprint `search`):
  - `GET /search` (`search.search`): args `q`, `mode` (`text`|`voice`, anything else → `text`), `similar` (product id; 404 if missing; not recorded). Records `(customer, q, mode)` for a logged-in customer with a non-blank `q`.
  - `POST /search/image` (`search.search_image`): file field `photo`; empty → flash "Choose a photo to search with" and redirect to `/search`; not an image → flash the `ValidationError` message and redirect; records keyword = uploaded filename (or `"photo"` when it has none) with type `image`.
  - The template shows results with `product_card`, the photo upload form, and for a logged-in customer the recent searches with their type.
- `voice.js`: finds `#mic` inside the navbar search form; hides it when neither `SpeechRecognition` nor `webkitSpeechRecognition` exists; on click starts recognition with `lang = document.documentElement.lang === 'vi' ? 'vi-VN' : 'en-US'`; on result fills the form's `q` input, sets the hidden `mode` input to `voice`, and submits. Base template loads `voice.js` on every page.

- [ ] **Step 1: Write the failing tests** in `tests/test_search.py`

```python
import io
from marketplacex.modules.search import service
from marketplacex.modules.search.images import solid_image
from marketplacex.modules.search.models import SearchHistory

def test_text_search_matches_and_vietnamese(demo):
    assert [p.title for p in service.search_text("iphone")] == ["Apple iPhone 15"]
    assert [p.title for p in service.search_text("dac nhan tam")] == ["Sách Đắc Nhân Tâm"]
    assert service.search_text("   ") == []
    assert [p.title for p in service.search_text("phone under 16 trieu")] == ["Samsung Galaxy S24"]

def test_vector_search_ranks_by_colour(demo):
    from marketplacex.modules.search.images import feature_vector
    red = feature_vector(solid_image((210, 40, 40)))
    assert service.search_vector(red)[0].id == demo.iphone.id
    assert demo.iphone.id not in [p.id for p in service.search_vector(demo.iphone.image_vector, exclude_id=demo.iphone.id)]

def test_text_and_voice_are_recorded_for_customers_only(client, demo, login_as):
    client.get("/search?q=iphone")
    assert SearchHistory.query.count() == 0
    login_as(client, "customer", demo.alice)
    client.get("/search?q=iphone")
    client.get("/search?q=samsung&mode=voice")
    client.get("/search?q=x&mode=weird")
    rows = [(h.keyword, h.search_type) for h in SearchHistory.query.order_by(SearchHistory.id)]
    assert rows == [("iphone", "text"), ("samsung", "voice"), ("x", "text")]

def test_image_upload_records_filename_and_rejects_non_images(client, demo, login_as):
    login_as(client, "customer", demo.alice)
    r = client.post("/search/image", data={"photo": (io.BytesIO(solid_image((220, 30, 30))), "red.png")},
                    content_type="multipart/form-data")
    assert "Apple iPhone 15" in r.get_data(as_text=True)
    assert SearchHistory.query.filter_by(search_type="image").one().keyword == "red.png"
    r = client.post("/search/image", data={"photo": (io.BytesIO(b"not an image"), "x.txt")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200 and "That file is not an image" in r.get_data(as_text=True)

def test_similar(client, demo):
    html = client.get(f"/search?similar={demo.iphone.id}").get_data(as_text=True)
    assert "Similar to Apple iPhone 15" in html
    assert client.get("/search?similar=9999").status_code == 404
    assert SearchHistory.query.count() == 0

def test_navbar_has_mic_and_mode(client, demo):
    html = client.get("/").get_data(as_text=True)
    assert 'id="mic"' in html and 'name="mode"' in html and "js/voice.js" in html
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** ranking, service, routes, template, `voice.js`, navbar change. The `/search?similar=` page heading reads "Similar to <product title>".
- [ ] **Step 4: Run** file and full suite — Expected: PASS.
- [ ] **Step 5: Commit** — `feat: text, voice and image search with search history`.

---

### Task 5: Session cart, checkout and simulated payment

**Files:**
- Create: `marketplacex/modules/cart/service.py`, `marketplacex/modules/cart/routes.py`, `marketplacex/modules/order/service.py` (checkout part), `marketplacex/modules/order/routes.py` (checkout routes), `marketplacex/templates/customer/{cart,checkout}.html`
- Test: `tests/test_cart_checkout.py`

**Interfaces:**
- Consumes: `catalog.service.get_product`, `auth.current_customer`, `auth.require_role`.
- Produces (`cart.service`; state in `flask.session["cart"]` as `{str(product_id): qty}`):
  - `CartLine` dataclass: `product`, `qty`, `line_total`
  - `raw() -> dict[int, int]`; `lines() -> list[CartLine]` (drops ids whose product no longer exists; caps qty at current stock; drops lines capped to 0); `subtotal() -> int`
  - `add(product_id: int, qty: int = 1) -> None` (`ValidationError("<title> is out of stock")` at stock 0; total qty capped at stock); `set_qty(product_id: int, qty: int) -> None` (≤0 removes); `remove(product_id: int) -> None`; `clear() -> None`
- Produces (`order.service`):
  - constants from Global Constraints
  - `shipping_fee(subtotal: int) -> int` (0 when `subtotal >= FREE_SHIPPING_FROM`, else `SHIPPING_FEE`)
  - `checkout(customer, cart: dict[int, int], payment_method: str, card_number: str | None = None) -> list[Order]`:
    - empty cart → `ValidationError("Your cart is empty")`; method not in (`cod`, `card`) → `ValidationError("Choose a payment method")`;
    - card: digits of `card_number` must equal `DEMO_CARD`, else `ValidationError("Card declined — use the demo card 4242 4242 4242 4242")`; nothing written;
    - loads the products `with_for_update()`; any qty > stock → `InsufficientStock("Only <stock> left of <title>")`; nothing written;
    - one row per cart line in cart order, all with the same `ordered_at = clock.now()`, `address_id = customer.address_id`, `unit_price = product.price`, `shipping_fee` = `shipping_fee(subtotal)` on the first row and 0 on the rest, `total_price = quantity * unit_price + shipping_fee`, `status = "placed"`, `payment_status = "paid"` for card and `"unpaid"` for cod;
    - decrements `stock_quantity`, sets `updated_at = clock.now()`; one commit.
- Produces (routes): blueprint `cart`: `GET /cart` (`cart.view`), `POST /cart/add` (`cart.add`; form `product_id`, `qty`; visitors allowed), `POST /cart/update` (`cart.update`), `POST /cart/remove` (`cart.remove`). Blueprint `order`: `GET /checkout` (`order.checkout`, customer only; shows the address, lines, subtotal, shipping fee, total, and a payment choice with a card-number field), `POST /checkout` (form fields `payment_method`, `card_number`; on success clears the cart and redirects to `/orders` if that endpoint exists, else `/`; on `DomainError` flashes and redirects back to `/checkout`). A visitor posting to `/checkout` is redirected to login.

- [ ] **Step 1: Write the failing tests** in `tests/test_cart_checkout.py`

```python
import pytest
from marketplacex.errors import InsufficientStock, ValidationError
from marketplacex.modules.order import service
from marketplacex.modules.order.models import Order

def test_shipping_fee_threshold():
    assert service.shipping_fee(499_999) == 30_000
    assert service.shipping_fee(500_000) == 0

def test_cart_caps_at_stock_and_refuses_out_of_stock(client, demo):
    client.post("/cart/add", data={"product_id": demo.galaxy.id, "qty": 10})
    with client.session_transaction() as s:
        assert s["cart"] == {str(demo.galaxy.id): 3}
    r = client.post("/cart/add", data={"product_id": demo.cheap.id, "qty": 1}, follow_redirects=True)
    assert "Bookmark is out of stock" in r.get_data(as_text=True)

def test_multi_line_card_checkout(demo, clock):
    orders = service.checkout(demo.alice, {demo.book.id: 2, demo.iphone.id: 1}, "card", "4242 4242 4242 4242")
    assert [(o.quantity, o.unit_price, o.shipping_fee, o.total_price) for o in orders] == [
        (2, 100_000, 0, 200_000), (1, 20_000_000, 0, 20_000_000)]
    assert {o.ordered_at for o in orders} == {clock.now}
    assert all(o.status == "placed" and o.payment_status == "paid" and o.address_id == demo.alice.address_id for o in orders)
    assert demo.book.stock_quantity == 48 and demo.iphone.stock_quantity == 4

def test_small_cod_order_pays_shipping_on_first_row(demo):
    (o,) = service.checkout(demo.alice, {demo.book.id: 1}, "cod")
    assert (o.shipping_fee, o.total_price, o.payment_status) == (30_000, 130_000, "unpaid")

def test_declined_card_writes_nothing(demo):
    with pytest.raises(ValidationError, match="Card declined"):
        service.checkout(demo.alice, {demo.book.id: 1}, "card", "4000 0000 0000 0002")
    assert Order.query.count() == 0 and demo.book.stock_quantity == 50

def test_stock_shortfall_aborts_whole_cart(demo):
    demo.galaxy.stock_quantity = 1
    with pytest.raises(InsufficientStock, match="Only 1 left of Samsung Galaxy S24"):
        service.checkout(demo.alice, {demo.book.id: 1, demo.galaxy.id: 2}, "cod")
    assert Order.query.count() == 0 and demo.book.stock_quantity == 50

def test_checkout_route_clears_cart_and_double_submit_is_refused(client, demo, login_as):
    login_as(client, "customer", demo.alice)
    client.post("/cart/add", data={"product_id": demo.book.id, "qty": 1})
    client.post("/checkout", data={"payment_method": "cod"})
    assert Order.query.count() == 1
    r = client.post("/checkout", data={"payment_method": "cod"}, follow_redirects=True)
    assert "Your cart is empty" in r.get_data(as_text=True) and Order.query.count() == 1

def test_visitor_checkout_redirects_to_login(client, demo):
    r = client.post("/checkout", data={"payment_method": "cod"})
    assert r.status_code == 302 and "/login" in r.headers["Location"]
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** cart service/routes, checkout service/routes, templates. Card number is never logged, stored or echoed back.
- [ ] **Step 4: Run** file and full suite — Expected: PASS.
- [ ] **Step 5: Commit** — `feat: session cart, checkout with simulated card and COD payment`.

---

### Task 6: Orders — simulated shipping, my orders, cancel

**Files:**
- Modify: `marketplacex/modules/order/service.py`, `marketplacex/modules/order/routes.py`
- Create: `marketplacex/templates/customer/{orders,order_detail}.html`, `marketplacex/static/js/order_progress.js`
- Test: `tests/test_orders.py`

**Interfaces:**
- Consumes: Task 5 `Order` rows, `clock.now()`.
- Produces (`order.service`):
  - `STEPS = ("placed", "processing", "shipped", "delivered")`
  - `advance_due() -> int` — for every order with status in `placed`/`processing`/`shipped`, repeatedly apply the rules until none fires, then commit once and return how many orders changed:
    - `placed` → `processing` when `now >= ordered_at + STEP_SECONDS`
    - `processing` → `shipped` when `now >= ordered_at + 2*STEP_SECONDS`; `shipped_at = ordered_at + 2*STEP_SECONDS`
    - `shipped` → `delivered` when `now >= shipped_at + STEP_SECONDS`; `delivered_at = shipped_at + STEP_SECONDS`; `cod` + `unpaid` → `paid`
  - `skip_step(order) -> None` — moves one step now: `placed`→`processing`; `processing`→`shipped` with `shipped_at = now`; `shipped`→`delivered` with `delivered_at = now` (cod becomes paid); final statuses → `IllegalTransition("Order is already <status>")`. Commits.
  - `cancel(order) -> None` — calls `advance_due()` first; allowed only in `placed`/`processing`, else `IllegalTransition("Only orders that have not shipped can be cancelled")`; restores stock; `paid` → `refunded`; status `cancelled`. Commits.
  - `orders_for_customer(customer) -> list[list[Order]]` — calls `advance_due()`; groups by `ordered_at`, newest group first, rows by id inside a group.
  - `get_order(order_id: int) -> Order` (`NotFound("Order not found")`)
  - `progress(order) -> dict` — `{"status", "payment_status", "steps": [{"name", "done": bool, "at": ISO string or None}]}` for the four `STEPS` (processing's `at` is `ordered_at + STEP_SECONDS` once done); `cancelled` orders have every step `done=False` except `placed`.
- Produces (routes, blueprint `order`, customer only, own orders only — another customer's id → 404): `GET /orders` (`order.my_orders`), `GET /orders/<int:order_id>` (`order.detail`), `GET /orders/<int:order_id>/progress` (`order.progress_json`, JSON from `progress()` after `advance_due()`), `POST /orders/<int:order_id>/cancel` (`order.cancel`). Detail page renders the four-step bar with `data-progress-url`; `order_progress.js` polls that URL every 5000 ms, updates the bar, payment status and cancel button, and stops on `delivered`/`cancelled`.

- [ ] **Step 1: Write the failing tests** in `tests/test_orders.py`

```python
from datetime import timedelta
import pytest
from marketplacex.errors import IllegalTransition
from marketplacex.modules.order import service

def _order(demo, method="cod", qty=1):
    return service.checkout(demo.alice, {demo.book.id: qty}, method, "4242424242424242" if method == "card" else None)[0]

def test_steps_advance_on_time(demo, clock):
    o = _order(demo)
    clock.advance(19); service.advance_due(); assert o.status == "placed"
    clock.advance(1);  service.advance_due(); assert o.status == "processing"
    clock.advance(20); service.advance_due(); assert o.status == "shipped" and o.shipped_at == o.ordered_at + timedelta(seconds=40)
    clock.advance(20); service.advance_due(); assert o.status == "delivered" and o.payment_status == "paid"

def test_unwatched_order_stamps_due_times_not_read_time(demo, clock):
    o = _order(demo)
    clock.advance(3600)
    assert service.advance_due() == 1
    assert o.status == "delivered"
    assert o.shipped_at == o.ordered_at + timedelta(seconds=40)
    assert o.delivered_at == o.ordered_at + timedelta(seconds=60)

def test_cancel_window_restores_stock_and_refunds(demo, clock):
    o = _order(demo, "card", qty=2)
    clock.advance(25)
    service.cancel(o)
    assert (o.status, o.payment_status, demo.book.stock_quantity) == ("cancelled", "refunded", 50)
    o2 = _order(demo)
    clock.advance(40)
    with pytest.raises(IllegalTransition):
        service.cancel(o2)

def test_skip_step(demo, clock):
    o = _order(demo)
    clock.advance(5)
    service.skip_step(o); service.skip_step(o)
    assert o.status == "shipped" and o.shipped_at == clock.now
    service.skip_step(o)
    assert o.status == "delivered" and o.payment_status == "paid"
    with pytest.raises(IllegalTransition):
        service.skip_step(o)

def test_my_orders_groups_by_checkout(demo, clock):
    service.checkout(demo.alice, {demo.book.id: 1, demo.galaxy.id: 1}, "cod")
    clock.advance(100)
    service.checkout(demo.alice, {demo.book.id: 1}, "cod")
    groups = service.orders_for_customer(demo.alice)
    assert [len(g) for g in groups] == [1, 2]

def test_other_customers_order_is_404(client, demo, login_as):
    o = _order(demo)
    login_as(client, "customer", demo.binh)
    assert client.get(f"/orders/{o.id}").status_code == 404
    assert client.post(f"/orders/{o.id}/cancel").status_code == 404

def test_progress_json(client, demo, clock, login_as):
    o = _order(demo)
    login_as(client, "customer", demo.alice)
    clock.advance(45)
    data = client.get(f"/orders/{o.id}/progress").get_json()
    assert data["status"] == "shipped"
    assert [s["done"] for s in data["steps"]] == [True, True, True, False]
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** service functions, routes, templates, `order_progress.js`.
- [ ] **Step 4: Run** file and full suite — Expected: PASS.
- [ ] **Step 5: Commit** — `feat: self-advancing shipping, my orders and cancel`.

---

### Task 7: Seller pages — products, images, orders

**Files:**
- Modify: `marketplacex/modules/catalog/service.py` (write functions)
- Create: `marketplacex/modules/seller/routes.py`, `marketplacex/templates/seller/{_nav,products,product_form,orders}.html`
- Test: `tests/test_seller.py`

**Interfaces:**
- Consumes: `order.service.advance_due`, `skip_step`, `get_order`; `search.images.feature_vector`, `pack`.
- Produces (`catalog.service`):
  - `save_product(product: Product | None, category_id: int, title: str, brand: str, description: str, price: int, stock: int) -> Product` — creates when `product` is None; title required, ≤255 → `ValidationError`; blank brand → `"Unbranded"`; brand ≤255; description ≤255 (`ValidationError("Description is too long (255 characters max)")`); price and stock integers ≥ 0 (`ValidationError("Price must be 0 or more")` / `"Stock must be 0 or more"`); unknown category → `NotFound`; sets `updated_at` (and `created_at` on create) from `clock.now()`; commits.
  - `fetch_image(url: str) -> bytes` — `urllib` GET, 10 s timeout, reads at most 5 MB, browser-like `User-Agent`.
  - `add_image(product: Product, url: str, fetch=fetch_image) -> ProductImage` — url must start with `http://` or `https://` and be ≤500 chars (`ValidationError("Enter an image URL starting with http(s)://")`); vector = `pack(feature_vector(fetch(url)))`, or `None` if fetching or decoding raises anything; commits.
  - `remove_image(image_id: int) -> None` (`NotFound` if missing); commits.
  - `seller_products(q: str = "", category_id: int | None = None, page: int = 1, per_page: int = 50) -> tuple[list[Product], int]` (case-insensitive title contains `q`).
- Produces (routes, blueprint `seller`, `require_role("seller")`): `GET /seller/products` (`seller.products`), `GET|POST /seller/products/new` (`seller.new_product`), `GET|POST /seller/products/<int:product_id>` (`seller.edit_product`), `POST /seller/products/<int:product_id>/images` (`seller.add_image`, form `url`), `POST /seller/images/<int:image_id>/delete` (`seller.delete_image`), `GET /seller/orders` (`seller.orders`; calls `advance_due()`; newest first; shows customer name, product, qty, total, payment, status), `POST /seller/orders/<int:order_id>/skip` (`seller.skip`).

- [ ] **Step 1: Write the failing tests** in `tests/test_seller.py`

```python
import pytest
from marketplacex.errors import ValidationError
from marketplacex.modules.catalog import service
from marketplacex.modules.search.images import solid_image

def test_save_product_rules(demo):
    p = service.save_product(None, demo.books.id, "New book", "  ", "short", 50_000, 10)
    assert p.brand == "Unbranded" and p.created_at is not None
    with pytest.raises(ValidationError, match="Description is too long"):
        service.save_product(p, demo.books.id, "New book", "", "x" * 256, 1, 1)
    with pytest.raises(ValidationError, match="Price must be 0 or more"):
        service.save_product(p, demo.books.id, "New book", "", "", -1, 1)

def test_add_image_computes_vector_or_none(demo):
    img = service.add_image(demo.cheap, "https://example.com/a.png", fetch=lambda u: solid_image((1, 2, 3)))
    assert img.feature_vector is not None
    def boom(u): raise OSError("down")
    assert service.add_image(demo.cheap, "https://example.com/b.png", fetch=boom).feature_vector is None
    with pytest.raises(ValidationError):
        service.add_image(demo.cheap, "ftp://x", fetch=boom)

def test_seller_pages_require_seller(client, demo, login_as):
    assert client.get("/seller/products").status_code == 302
    login_as(client, "customer", demo.alice)
    assert client.get("/seller/products").status_code == 403
    login_as(client, "seller")
    assert "Apple iPhone 15" in client.get("/seller/products").get_data(as_text=True)

def test_seller_edits_product_and_skips_order(client, demo, login_as):
    from marketplacex.modules.order import service as orders
    login_as(client, "seller")
    client.post(f"/seller/products/{demo.book.id}", data={"category_id": demo.books.id, "title": "Đắc Nhân Tâm (bìa cứng)",
                "brand": "", "description": "d", "price": 120_000, "stock": 7})
    assert (demo.book.title, demo.book.price, demo.book.stock_quantity) == ("Đắc Nhân Tâm (bìa cứng)", 120_000, 7)
    o = orders.checkout(demo.alice, {demo.book.id: 1}, "cod")[0]
    client.post(f"/seller/orders/{o.id}/skip")
    assert o.status == "processing"
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** file and full suite — Expected: PASS.
- [ ] **Step 5: Commit** — `feat: seller product, image and order pages`.

---

### Task 8: Admin pages — overview, categories, customers, orders

**Files:**
- Modify: `marketplacex/modules/catalog/service.py` (category writes)
- Create: `marketplacex/modules/admin/service.py`, `marketplacex/modules/admin/routes.py`, `marketplacex/templates/admin/{_nav,dashboard,categories,customers,customer,orders}.html`
- Test: `tests/test_admin.py`

**Interfaces:**
- Produces (`catalog.service`): `save_category(category: Category | None, name: str, description: str) -> Category` (name required, both ≤255); `delete_category(category_id: int) -> None` (`ValidationError("Category still has products")` when it has any). Both commit.
- Produces (`admin.service`): `table_counts() -> list[tuple[str, int]]` — the 8 tables in the order `FullName, Address, Customer, SearchHistory, Category, Product, ProductImage, Order`.
- Produces (routes, blueprint `admin`, `require_role("admin")`): `GET /admin` (`admin.dashboard`, the counts), `GET|POST /admin/categories` (`admin.categories`; list with product counts, add form), `POST /admin/categories/<int:category_id>` (`admin.edit_category`), `POST /admin/categories/<int:category_id>/delete` (`admin.delete_category`; error flashed), `GET /admin/customers` (`admin.customers`; name, email, phone, order count), `GET /admin/customers/<int:customer_id>` (`admin.customer`; full name parts, address, orders after `advance_due()`, search history newest first), `GET /admin/orders` (`admin.orders`), `POST /admin/orders/<int:order_id>/cancel` (`admin.cancel_order`; uses `order.service.cancel`, error flashed).

- [ ] **Step 1: Write the failing tests** in `tests/test_admin.py`

```python
def test_table_counts(demo):
    from marketplacex.modules.admin import service
    counts = dict(service.table_counts())
    assert list(counts) == ["FullName", "Address", "Customer", "SearchHistory", "Category", "Product", "ProductImage", "Order"]
    assert counts["Customer"] == 2 and counts["Product"] == 4 and counts["Order"] == 0

def test_admin_access(client, demo, login_as):
    assert client.get("/admin").status_code == 302
    login_as(client, "seller")
    assert client.get("/admin").status_code == 403
    login_as(client, "admin")
    assert "ProductImage" in client.get("/admin").get_data(as_text=True)

def test_category_delete_refused_when_not_empty(client, demo, login_as):
    from marketplacex.modules.catalog.models import Category
    login_as(client, "admin")
    r = client.post(f"/admin/categories/{demo.books.id}/delete", follow_redirects=True)
    assert "Category still has products" in r.get_data(as_text=True)
    client.post("/admin/categories", data={"name": "Toys", "description": "Fun"})
    toys = Category.query.filter_by(name="Toys").one()
    client.post(f"/admin/categories/{toys.id}/delete")
    assert Category.query.filter_by(name="Toys").count() == 0

def test_customer_detail_shows_history_and_orders(client, demo, login_as):
    from marketplacex.modules.order import service as orders
    from marketplacex.modules.search import service as search
    search.record(demo.alice, "tai nghe", "voice")
    orders.checkout(demo.alice, {demo.book.id: 1}, "cod")
    login_as(client, "admin")
    html = client.get(f"/admin/customers/{demo.alice.id}").get_data(as_text=True)
    assert "tai nghe" in html and "voice" in html and "Sách Đắc Nhân Tâm" in html

def test_admin_cancel(client, demo, login_as):
    from marketplacex.modules.order import service as orders
    o = orders.checkout(demo.alice, {demo.book.id: 1}, "cod")[0]
    login_as(client, "admin")
    client.post(f"/admin/orders/{o.id}/cancel")
    assert o.status == "cancelled"
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** file and full suite — Expected: PASS.
- [ ] **Step 5: Commit** — `feat: admin overview, categories, customers and orders`.

---

### Task 9: Assistant, trimmed

**Files:**
- Create: `marketplacex/modules/assistant/service.py`, `marketplacex/modules/assistant/routes.py` (rebuilt from the deleted versions: `git show 9a2677a:marketplacex/modules/assistant/service.py` and `...routes.py`)
- Test: `tests/test_assistant.py`

**Interfaces:**
- Consumes: `search.service.search_text`, `order.service.orders_for_customer`, `catalog` models.
- Produces: same `check_rate`, `_call_gemini`, `ask(question, history, customer) -> str` as before, with:
  - `_products_context(question)`: up to 8 `search_text` hits as `- <title> | <price:,> ₫ | rating <x.x> | in stock / out of stock | /products/<id>`; no hits → the 5 highest-rated products under "No direct matches. Popular products:".
  - `_policy_context()`: fixed text stating shipping is 30,000 ₫ per checkout and free from 500,000 ₫; payment is cash on delivery or the demo card; orders move placed → processing → shipped → delivered about every 20 seconds and can be cancelled before they ship; pages `/search`, `/cart`, `/checkout`, `/orders`, `/profile`. No vouchers, returns, chat or sellers' shops.
  - `_orders_context(customer)`: `customer is None` → "The user is not logged in as a customer; you cannot see any orders."; else up to 8 of their orders as `- Order #<id>: <title> x<qty>, <status>, total <total:,> ₫ | /orders/<id>`.
  - Route `POST /api/assistant` (`assistant.chat`) passes `auth.current_customer()`; rate key `customer:<id>` or `ip:<addr>`.

- [ ] **Step 1: Write the failing tests** in `tests/test_assistant.py`

```python
from marketplacex.modules.assistant import service

def test_prompt_contains_products_policy_and_own_orders(demo):
    from marketplacex.modules.order import service as orders
    orders.checkout(demo.alice, {demo.book.id: 1}, "cod")
    p = service.build_system_prompt("iphone", demo.alice)
    assert "Apple iPhone 15" in p and "/products/" in p and "30,000" in p and "Sách Đắc Nhân Tâm x1" in p
    assert "voucher" not in p.lower() and "return" not in p.lower()
    assert "not logged in" in service.build_system_prompt("iphone", None)

def test_no_key_is_503(client, demo):
    r = client.post("/api/assistant", json={"message": "hi"})
    assert r.status_code == 503
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** file and full suite — Expected: PASS.
- [ ] **Step 5: Commit** — `feat: shopping assistant grounded in products and the customer's orders`.

---

### Task 10: Seed, `init-db`, Supabase smoke test, README

**Files:**
- Rewrite: `marketplacex/seed_tiki.py`, `tests/test_supabase.py`, `README.md`
- Modify: `marketplacex/app.py` (`init-db`, `drop_everything`)
- Test: `tests/test_seed.py`

**Interfaces:**
- Consumes: `tiki.load_snapshot()`, `tiki.clean_description`, `tiki.CATEGORIES`, snapshot product keys `name`, `brand`, `description`, `price`, `rating`, `images`, `vectors` (base64 or null), `tiki_id`; `order.service.shipping_fee`.
- Produces (`seed_tiki`):
  - `UNBRANDED = "Unbranded"`
  - `CUSTOMERS`: the 10 customers of the current seed (alice, binh, chi, dung, giang, hoa, khanh, linh, minh, nam `@demo`, same phones). Names split from the current "First Middle Last" strings: first token → `firstName`, last token → `lastName`, rest → `middleName` (alice has none). Address from the current `(street, ward, district, city)`: `street` = street minus its leading house number, `ward` = ward, `detail` = `"<house number>, <district>, <city>"` (e.g. `"12, Hoan Kiem, Hanoi"`).
  - `SEARCHES`: 30 rows, 3 per customer, types cycling `text`, `voice`, `image`; text/voice keywords drawn in order from `["iphone", "áo thun", "tai nghe bluetooth", "son môi", "sách kỹ năng", "giày chạy bộ", "nồi chiên không dầu", "cà phê", "bàn phím cơ", "kem chống nắng"]`; image keyword `"photo.jpg"`; `searched_at` = now − (index + 1) hours.
  - `run(snapshot: dict | None = None) -> dict` — returns counts keyed by the 8 table names. Per category (one commit each): `Category(name, description=f"{name} from Tiki.vn")`; each product: title `name.strip()[:255]`, brand stripped or `UNBRANDED` (cut to 255), description `clean_description(...)`, `price=int(price)`, `stock_quantity = random.Random(tiki_id).randint(20, 200)`, `avg_rating=float(rating or 0)`, `created_at = updated_at = now - (i % 60) days`; up to 3 images with decoded vectors. Then customers, searches, and 20 orders: customer `ci`, `k` ∈ {0, 1}, product = products-by-id `[(ci*7 + k*31 + 3) % N]`, quantity `1 + (ci + k) % 2`, method `card` when `(ci + k)` is even else `cod`, `ordered_at = now − (ci*3 + k + 1) days`, `shipping_fee = shipping_fee(qty*price)`, delivered with `shipped_at = ordered_at + 40 s`, `delivered_at = shipped_at + 20 s`, `payment_status = "paid"` — except `(ci, k)` ∈ {(3, 1), (7, 1)}: `cancelled`, no shipped/delivered stamps, `refunded` if card else `unpaid`. Seed orders do not change stock.
- Produces (`app.py`): `drop_everything() -> None` — on Postgres, drop every table in schema `public` (reflected with `inspect(db.engine).get_table_names(schema="public")`) with `DROP TABLE IF EXISTS <quoted> CASCADE` in one transaction; elsewhere `db.drop_all()`. `init-db [--reset]`: `--reset` → `drop_everything()`; without it, refuse with exit code 1 and "Database already initialised; use --reset to wipe and reseed." when the `Customer` table exists and has a row; then `db.create_all()`, `seed_tiki.run()`, commit, close session, `enable_rls()`, echo counts and the RLS line.
- `tests/test_supabase.py`: keep the module skip logic; assert the public schema's table set equals the 8 names, each with exactly the columns of `tests/test_schema.py::TABLES` (import it), RLS on every public table, and every category ≥ 50 products.
- README: rewrite "What it is", "Run it" (same venv/`DATABASE_URL`/`init-db --reset`/run/test steps; seeding now takes a few minutes), "Demo logins" (the three buttons; any seeded customer by email, e.g. `binh@demo`; sign-up), "Database" (the 8 tables with one line each), "Simulations" (card `4242 4242 4242 4242`, COD, shipping steps every 20 s, seller skip). Remove sections about deleted features. No password or project secrets.

- [ ] **Step 1: Write the failing tests** in `tests/test_seed.py`

```python
import base64
from marketplacex import seed_tiki
from marketplacex.modules.search.images import solid_image, feature_vector, pack

def _snapshot(n=55):
    vec = base64.b64encode(pack(feature_vector(solid_image((10, 20, 30))))).decode()
    def prod(c, i):
        return {"tiki_id": f"{c}{i}", "name": f" Product {c}-{i} ", "brand": "" if i % 2 else "Brand",
                "description": "<p>Nice &amp; good</p>", "price": "123000", "rating": "4.5",
                "images": [f"https://salt.tikicdn.com/{c}/{i}/{k}.jpg" for k in range(4)], "vectors": [vec, None, vec, vec]}
    return {"categories": [{"name": f"Cat{c}", "shop": "x", "products": [prod(c, i) for i in range(n)]} for c in range(8)]}

def test_seed_counts_and_mapping(app):
    from marketplacex.modules.catalog.models import Product, ProductImage
    from marketplacex.modules.identity.models import Customer
    from marketplacex.modules.order.models import Order
    counts = seed_tiki.run(_snapshot())
    assert counts == {"FullName": 10, "Address": 10, "Customer": 10, "SearchHistory": 30, "Category": 8,
                      "Product": 440, "ProductImage": 1320, "Order": 20}
    p = Product.query.order_by(Product.id).first()
    assert p.title == "Product 0-0" and p.description == "Nice & good" and p.price == 123000 and 20 <= p.stock_quantity <= 200
    assert Product.query.filter_by(brand="Unbranded").count() == 216   # odd i of 0..54, 27 per category
    assert ProductImage.query.filter(ProductImage.feature_vector.is_(None)).count() == 440
    alice = Customer.query.filter_by(email="alice@demo").one()
    assert alice.name == "Alice Nguyen" and alice.address.detail == "12, Hoan Kiem, Hanoi" and alice.address.street == "Trang Tien"
    assert Order.query.filter_by(status="cancelled").count() == 2
    assert Order.query.filter_by(status="delivered").count() == 18

def test_init_db_refuses_without_reset(app):
    seed_tiki.run(_snapshot(1))
    result = app.test_cli_runner().invoke(args=["init-db"])
    assert result.exit_code == 1 and "use --reset" in result.output
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** `seed_tiki.py`, `drop_everything`, `init-db`, `test_supabase.py`, README.
- [ ] **Step 4: Run** the full suite — Expected: PASS, with `tests/test_supabase.py` deselected. Also run `.venv/bin/flask --app marketplacex.app init-db --reset` against a scratch SQLite file (`DATABASE_URL=sqlite:////<scratchpad>/seed.db`) and confirm 8 categories × 65 products are reported.
- [ ] **Step 5: Commit** (never `config.py`) — `feat: seed the 8 tables from the Tiki snapshot; init-db drops every old table`.

---

### Task 11: Rebuild Supabase and verify live (controller)

This is destructive (drops the 46 current tables) and was approved in the spec. The controller runs it, not a subagent.

- [ ] **Step 1:** `.venv/bin/flask --app marketplacex.app init-db --reset` (uses the local `config.py` URL). Expected: counts for 8 tables, `Product: 520`, and "row level security enabled on 8 tables".
- [ ] **Step 2:** `.venv/bin/python -m pytest -q -m supabase` — Expected: all pass.
- [ ] **Step 3:** Run the app and click through: home and every category; text search "iphone" and "áo thun"; mic button present in Safari/Chrome; photo upload search; quick-login Alice → add two products → card checkout → watch the progress bar reach Delivered; COD order cancelled within 40 s; email login as `binh@demo`; sign up a new customer; Seller: edit a product, add an image URL, skip an order step; Admin: counts, add/delete an empty category, customer detail shows search history.
- [ ] **Step 4:** `git grep -n 'vmzbgxyibhhvoucpugwd:[^@]*@'` and `git status --short` — Expected: no password in tracked files; `marketplacex/config.py` modified but unstaged.
