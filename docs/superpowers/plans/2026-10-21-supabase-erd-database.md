# Supabase ERD Database Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run MarketplaceX on a fresh Supabase Postgres database whose core is the ERD (Address, FullName, Customer, SearchHistory, Category, Product, ProductImage), seeded with ≥50 real Tiki.vn products per category, with only customer/seller/admin roles.

**Architecture:** Keep the Flask modular monolith. ERD tables get their exact table/column names via SQLAlchemy `__tablename__` and `db.Column("<erdName>", ...)`, while Python attribute names stay as they are today where possible (e.g. `Product.title` maps to column `name`) to limit churn. Old marketplace tables stay and point their foreign keys at the new tables. Tests keep running on in-memory SQLite; production runs on Postgres through the Supabase session pooler.

**Tech Stack:** Python 3, Flask 3, Flask-SQLAlchemy, psycopg2-binary, Pillow, pytest, Supabase Postgres.

**Spec:** `docs/superpowers/specs/2026-10-21-supabase-erd-database-design.md`

## Global Constraints

- ERD table names, exactly: `Address`, `FullName`, `Customer`, `SearchHistory`, `Category`, `Product`, `ProductImage`.
- ERD column names, exactly as in the spec table (camelCase, e.g. `customerID`, `fullNameID`, `stockQuantity`, `avgRating`, `featureVector`). Added columns only appended, never renaming ERD ones.
- `ProductImage.imageUrl` is `varchar(500)`; `Product.description` is `varchar(255)`; `Product.price` and `stockQuantity` integer; `avgRating` float; `featureVector` `LargeBinary` (bytea).
- `ROLES = ("customer", "seller", "admin")`. No `support` or `risk` strings left in routes, templates, policies, seeds or tests.
- The Supabase password never enters git. Committed `config.py` reads `DATABASE_URL`; the hard-coded local URL stays an uncommitted working-copy change (like the Gemini key). Before every commit run `git diff --cached | grep -cE 'vmzbgxyibhhvoucpugwd:[^@]+@'` and expect `0`.
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Full suite command: `.venv/bin/pytest -q`. It must pass at the end of every task.
- Models must work on both SQLite (tests) and Postgres (production): only `JSON`, `LargeBinary`, `String`, `Integer`, `Float`, `Boolean`, `DateTime`, `Text`.

## Review Focus

1. **Circular FK `Customer.addressID` ↔ `Address.customerID`:** `drop_all`/`create_all` on Postgres must not fail. Pin it with `use_alter=True` on `Customer.addressID` and a test that `db.drop_all(); db.create_all()` runs twice in a row (Task 3).
2. **Product with no offers or no stock:** `sync_product` must set `price=0`, `stockQuantity=0` rather than crash on `min([])` (Task 4 test).
3. **Tiki description over 255 chars or HTML:** strip tags and truncate to 255 without breaking a seed insert (Task 7 test).
4. **Image search with an upload that is not an image** (e.g. a .txt renamed .jpg): user sees a flash error, not a 500 (Task 6 test).
5. **Re-running `init-db` without `--reset` on a populated database:** must refuse with a clear message instead of duplicating 520 products (Task 8 test).

---

### Task 1: Remove the risk module

**Files:**
- Delete: `marketplacex/modules/risk/`, `marketplacex/templates/risk/`, `tests/test_risk.py`
- Modify: `marketplacex/app.py` (MODULES list), `marketplacex/modules/checkout/service.py:1,22,150-175`, `marketplacex/modules/returns/service.py:171-190,314-317`, `marketplacex/modules/admin/policy.py:15-17`, `marketplacex/seed.py` (`USERS` risk row, `seed_risk`, `run()` list), `marketplacex/templates/base.html` (risk nav link)
- Test: `tests/test_checkout.py`, `tests/test_returns.py`

**Interfaces:**
- Produces: `checkout.place_order` goes straight from reserve to authorize (no `"held"` path); `continue_after_risk` deleted; `returns.execute_refund(case, amount_vnd=None, actor=None)` (the `skip_risk` param removed); `returns.close_after_risk` deleted.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_checkout.py
def test_high_value_checkout_is_never_held(alice):
    # 25,000,000 VND exceeds the old risk_max_order_vnd of 20,000,000
    from helpers import offer_id
    from marketplacex.modules.cart import service as cart
    from marketplacex.modules.checkout import service as checkout
    import uuid
    cart.add_item(alice, offer_id("P05"), 4)  # 4 x 6,490,000
    g = checkout.quote(alice, alice.addresses[0].id, [])
    checkout.place_order(alice, g.id, uuid.uuid4().hex, g.quote_hash)
    assert g.failure_reason != "Under risk review"
    assert g.status in ("placing", "completed")

# tests/test_foundation.py
def test_only_three_roles():
    from marketplacex.modules.identity.models import ROLES
    assert ROLES == ("customer", "seller", "admin")

def test_no_risk_policies(app):
    from marketplacex.modules.admin import policy
    assert not [k for k in policy.DEFAULTS if k.startswith("risk_")]
```

(Use whatever name `admin/policy.py` gives its defaults dict; if it is not `DEFAULTS`, use that name.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest -q tests/test_checkout.py::test_high_value_checkout_is_never_held tests/test_foundation.py -k "roles or risk"`
Expected: FAIL (roles tuple still has 5 entries; risk policies present).

- [ ] **Step 3: Delete the risk module and its call sites**

Remove the files listed, the `"risk"` entry in `MODULES`, the `risk_*` policy defaults, `seed_risk` and the `risk@demo` user. In `ROLES` drop `"risk"` only (support goes in Task 2, so the roles test still fails until then — mark it `xfail(strict=True)` with reason "support removed in Task 2" and remove the marker in Task 2).

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: all pass (1 xfail).

- [ ] **Step 5: Commit**

```bash
git add -A marketplacex tests
git commit -m "refactor: remove risk review module; checkout and refunds no longer held"
```

---

### Task 2: Move support into admin "Cases"

**Files:**
- Move: `marketplacex/modules/support/` → `marketplacex/modules/cases/`; `marketplacex/templates/support/` → `marketplacex/templates/admin/cases/`; `tests/test_support.py` → `tests/test_cases.py`
- Modify: `marketplacex/app.py` (MODULES: `"support"` → `"cases"`), `marketplacex/modules/identity/models.py` (ROLES), `marketplacex/modules/logistics/routes.py:13`, `marketplacex/modules/returns/service.py:146`, `marketplacex/templates/base.html`, `marketplacex/templates/admin/` nav (add "Cases" tab), `marketplacex/templates/customer/order_detail.html:67-71`, `marketplacex/seed.py` (`support@demo` row)

**Interfaces:**
- Produces: blueprint `cases` with URLs under `/admin/cases/…`, all `@require_role("admin")` except the two customer actions. Endpoint names: `cases.dashboard`, `cases.case`, `cases.case_action`, `cases.dispute`, `cases.decide`, `cases.resolve_order`, `cases.open_from_order` (POST `/orders/<id>/help`), `cases.not_received` (POST `/orders/<id>/not-received`).
- Models renamed: `SupportCase` → `CustomerCase` (table `customer_case`), `CaseNote` stays (table `case_note`).
- Service: masking and reveal removed (`mask_email`, `mask_phone`, `reveal` deleted); `search(agent, q)` stays.

- [ ] **Step 1: Port the tests**

Rewrite `tests/test_cases.py` from `test_support.py`: every `make_user("support")` becomes `make_user("admin")`, URLs `/support/...` become `/admin/cases/...`, `url_for('support.x')` becomes `url_for('cases.x')`. Delete `test_masking_and_reveal_audited` and `test_customer_page_masks`. Add:

```python
def test_customer_cannot_open_cases_console(client, alice, login):
    login(client, alice)
    assert client.get("/admin/cases/").status_code == 403

def test_order_page_links_to_admin_cases(client, alice, login, make_order):
    o = make_order(status="Delivered")
    login(client, alice)
    html = client.get(f"/orders/{o.id}").get_data(as_text=True)
    assert f"/orders/{o.id}/not-received" in html and "/support" not in html
```

Remove the `xfail` marker on `test_only_three_roles`.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest -q tests/test_cases.py tests/test_foundation.py`
Expected: FAIL (no `cases` blueprint, ROLES still has support).

- [ ] **Step 3: Move and rewire**

`git mv` the module, templates and test. Change role checks to `admin`, URL prefix to `/admin/cases`, template paths to `admin/cases/…`, remove masking/reveal routes and template blocks, add a "Cases" link in the admin nav and remove the support link from `base.html`. `logistics/routes.py` roles become `("customer", "seller", "admin")`; `returns/service.py:146` allows `user.role == "admin"`. Customer flash text: "We've opened a case. An admin will review it."

- [ ] **Step 4: Run the full suite and grep**

Run: `.venv/bin/pytest -q && grep -rniE "\bsupport\b|\brisk\b" marketplacex tests --include=*.py --include=*.html | grep -v "data/"`
Expected: tests pass; grep prints nothing (fix any leftover user-visible text).

- [ ] **Step 5: Commit**

```bash
git add -A marketplacex tests
git commit -m "refactor: admin takes over support cases; roles are customer, seller, admin"
```

---

### Task 3: Account, Customer, FullName and Address per ERD

**Files:**
- Modify: `marketplacex/modules/identity/models.py`, `marketplacex/modules/identity/service.py`, `marketplacex/modules/identity/routes.py:87-92`, `marketplacex/templates/auth/account.html`, `marketplacex/templates/customer/checkout.html`, every model with `db.ForeignKey("user.id")` (seller, promotion, order, chat, notification, checkout, review, cart, returns, cases), `marketplacex/modules/checkout/models.py` (`"address.id"` → `"Address.addressID"`), `marketplacex/auth.py`, `marketplacex/seed.py`, `marketplacex/seed_bulk.py`, `tests/conftest.py`, `tests/helpers.py`, any test importing `User`
- Test: `tests/test_identity_erd.py` (create)

**Interfaces:**
- Produces (`marketplacex/modules/identity/models.py`):
  - `class Account` — table `account`, columns `id, email, password_hash, name, role, status, phone, created_at` (old `User`). Relationship `customer` (uselist=False). Property `addresses -> list[Address]` = `self.customer.addresses if self.customer else []`. No `User` alias: rename all imports.
  - `class FullName` — table `FullName`: `id`→col `fullNameID`, `first_name`→`firstName`, `middle_name`→`middleName`, `last_name`→`lastName` (all `String(255)`). Property `display -> str` joins non-empty parts with spaces.
  - `class Customer` — table `Customer`: `id`→`customerID`, `full_name_id`→`fullNameID` FK, `address_id`→`addressID` FK `Address.addressID` with `use_alter=True`, nullable, `email`→`email` String(255), `phone_number`→`phoneNumber` String(255), `account_id`→`accountID` FK `account.id` unique not null. Relationships `full_name`, `account`, `addresses` (via `Address.customer_id`, ordered by id), `default_address`.
  - `class Address` — table `Address`: `id`→`addressID`, `ward`, `street`, `detail` (String(255)), then `customer_id`→`customerID` FK, `recipient`, `phone`, `district`, `city`, `is_default`→`isDefault`. Property `line -> str` = `", ".join(p for p in (detail, street, ward, district) if p)`. `as_dict()` returns keys `recipient, phone, line, city, ward, street, district` (keeps `line` so order snapshots and templates still work).
- Produces (`identity/service.py`):
  - `split_name(name: str) -> tuple[str, str, str]` — first token, middle tokens joined, last token; one word → `(word, "", "")`.
  - `create_account(email: str, name: str, role: str, password: str, phone: str | None = None, created_at=None) -> Account` — validates as `register` does today; for `role == "customer"` also creates `FullName` + `Customer` (email/phone mirrored).
  - `register(email, password, name) -> Account` calls `create_account(..., role="customer")`.
  - `add_address(account: Account, recipient: str, phone: str, street: str, ward: str, district: str, city: str, detail: str = "", is_default: bool = False) -> Address` — requires recipient, phone, street, ward, city; sets `Customer.address_id` when the new address becomes default; raises `ValidationError("Only customers have addresses")` for non-customers.
  - `default_address(account) -> Address | None` unchanged behaviour.
- `tests/conftest.py::make_user` uses `identity.create_account(email, f"{role.title()} {n}", role, "pw12345")`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_identity_erd.py
from marketplacex.extensions import db

def test_register_creates_customer_and_fullname(app):
    from marketplacex.modules.identity import service
    a = service.register("lan@x.vn", "secret1", "Lan Thi Tran")
    c = a.customer
    assert (c.full_name.first_name, c.full_name.middle_name, c.full_name.last_name) == ("Lan", "Thi", "Tran")
    assert c.email == "lan@x.vn" and c.account_id == a.id

def test_seller_has_no_customer_row(app, make_user):
    assert make_user("seller").customer is None

def test_default_address_sets_customer_addressID(app, make_user):
    from marketplacex.modules.identity import service
    u = make_user()
    a1 = service.add_address(u, "Lan", "0901", "12 Trang Tien", "Trang Tien", "Hoan Kiem", "Hanoi")
    a2 = service.add_address(u, "Lan", "0901", "5 Le Loi", "Ben Nghe", "District 1", "Ho Chi Minh City", is_default=True)
    assert u.customer.address_id == a2.id and not a1.is_default
    assert a2.as_dict()["line"] == "5 Le Loi, Ben Nghe, District 1"

def test_seller_cannot_add_address(app, make_user):
    import pytest
    from marketplacex.errors import ValidationError
    from marketplacex.modules.identity import service
    with pytest.raises(ValidationError):
        service.add_address(make_user("seller"), "S", "0", "st", "w", "d", "c")

def test_erd_table_and_column_names(app):
    t = db.metadata.tables
    assert {c.name for c in t["Customer"].columns} >= {"customerID", "fullNameID", "addressID", "email", "phoneNumber"}
    assert {c.name for c in t["FullName"].columns} == {"fullNameID", "firstName", "middleName", "lastName"}
    assert {c.name for c in t["Address"].columns} >= {"addressID", "ward", "street", "detail"}

def test_drop_create_twice(app):
    for _ in range(2):
        db.drop_all()
        db.create_all()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest -q tests/test_identity_erd.py`
Expected: FAIL (ImportError / no `customer` attribute).

- [ ] **Step 3: Implement the models and service functions above**

Then update callers: FK strings `"user.id"` → `"account.id"`; `User` → `Account` imports everywhere; the address form in `auth/account.html` gets fields `street, ward, district, city, detail` (route passes them through); `seed.py` and `seed_bulk.py` create accounts via `create_account` and addresses with the new signature (Alice: `"12 Trang Tien", "Trang Tien", "Hoan Kiem", "Hanoi"`).

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A marketplacex tests
git commit -m "feat: ERD Customer, FullName and Address tables with a shared Account login"
```

---

### Task 4: ERD Category, Product, ProductImage and derived fields

**Files:**
- Modify: `marketplacex/modules/catalog/models.py`, `marketplacex/modules/catalog/service.py`, `marketplacex/modules/inventory/service.py`, `marketplacex/modules/review/service.py`, `marketplacex/modules/review/models.py` (FK `"product.id"` → `"Product.productID"`), `marketplacex/modules/seller/routes.py`, templates using `image_url` (`_cards.html`, `customer/product.html`, `customer/cart.html`), `marketplacex/modules/returns/service.py`, `marketplacex/seed.py`, `marketplacex/seed_bulk.py`
- Test: `tests/test_catalog_erd.py` (create)

**Interfaces:**
- Produces (`catalog/models.py`):
  - `Category` — table `Category`: `id`→`categoryID`, `name`→`name` String(255), `description`→`description` String(255) default `""`, `parent_id`→`parentID`, `attribute_schema`→`attributeSchema`.
  - `Product` — table `Product`: `id`→`productID`, `category_id`→`categoryID`, `title`→`name` String(255), `brand`→`brandName` String(255), `description`→`description` String(255), `price`→`price` Integer default 0, `stock_quantity`→`stockQuantity` Integer default 0, `avg_rating`→`avgRating` Float default 0, `created_at`→`createdAt`, `updated_at`→`updatedAt`, then `shop_id`→`shopID`, `status`, `attributes`, `moderation_reason`→`moderationReason`. Remove `image_url`/`image_vector` columns. Relationship `images` → `ProductImage` ordered by `sort_order`. Property `image_url -> str | None` = first image's URL (templates keep working). Property `image_vector -> list[float] | None` = first image's decoded vector.
  - `ProductImage` — table `ProductImage`: `id`→`imageID`, `product_id`→`productID` FK, `url`→`imageUrl` String(500), `feature_vector`→`featureVector` LargeBinary nullable, `sort_order`→`sortOrder` Integer default 0.
  - `Variant`, `Offer` unchanged except FK to `Product.productID`.
- Produces (`catalog/service.py`):
  - `sync_product(product: Product) -> None` — `price` = min `offer.price_vnd` over the product's offers (0 if none); `stock_quantity` = sum of `inventory.in_stock(offer.id)`; `avg_rating` = mean of visible review ratings rounded to 1 decimal, falling back to the rating-count-weighted offer `rating_avg` when there are no reviews, else 0; `updated_at = policy.now()`. Does not commit.
  - `create_product(..., image_urls: list[str] | None = None, vectors: list[bytes | None] | None = None, ...)` replaces the `image_url=` kwarg; creates `ProductImage` rows in order and calls `sync_product`.
- Callers of `sync_product` (same transaction): `inventory.set_stock`, `reserve`, `commit`, `release`, `return_committed`, `sweep_expired`; `catalog.save_listing` after offers are written; `review.create_review` and `review.set_hidden`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_catalog_erd.py
from marketplacex.extensions import db

def test_product_columns_match_erd(app):
    cols = {c.name for c in db.metadata.tables["Product"].columns}
    assert cols >= {"productID", "categoryID", "name", "brandName", "description", "price",
                    "stockQuantity", "avgRating", "createdAt", "updatedAt"}
    img = {c.name: c for c in db.metadata.tables["ProductImage"].columns}
    assert set(img) >= {"imageID", "productID", "imageUrl", "featureVector"}
    assert img["imageUrl"].type.length == 500

def test_price_and_stock_follow_offers(seeded):
    from helpers import _product, offer_id
    from marketplacex.modules.inventory import service as inventory
    p = _product("P03")
    assert p.price == min(v.offer.price_vnd for v in p.variants)
    inventory.set_stock(offer_id("P03"), 7)
    db.session.commit()
    assert p.stock_quantity == 7

def test_sync_product_with_no_offers(app, make_user):
    from marketplacex.modules.catalog import service as catalog
    from marketplacex.modules.catalog.models import Category, Product
    from marketplacex.modules.seller import service as seller
    shop = seller.create_shop(make_user("seller"), "S", "Hanoi", "")
    cat = Category(name="X"); db.session.add(cat); db.session.flush()
    p = Product(shop_id=shop.id, category_id=cat.id, title="Empty", status="draft")
    db.session.add(p); db.session.flush()
    catalog.sync_product(p)
    assert (p.price, p.stock_quantity, p.avg_rating) == (0, 0, 0)

def test_review_updates_avg_rating(alice):
    from helpers import delivered_order, _product
    from marketplacex.modules.review import service as review
    o = delivered_order(alice, "P07")
    review.create_review(alice, o.items[0].id, 2, "meh")
    assert _product("P07").avg_rating == 2.0

def test_image_url_property_uses_first_image(seeded):
    from helpers import _product
    p = _product("P01")
    assert p.image_url == p.images[0].url
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest -q tests/test_catalog_erd.py`
Expected: FAIL.

- [ ] **Step 3: Implement the models, `sync_product`, `create_product` change and call sites listed above**

Seeds pass `image_urls=[...]` instead of `image_url=`. Prototype vectors are handled in Task 6; until then pass `vectors=None`.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: all pass (image-search tests may need `xfail(strict=True, reason="vectors in Task 6")` if they rely on `image_vector`; remove in Task 6).

- [ ] **Step 5: Commit**

```bash
git add -A marketplacex tests
git commit -m "feat: ERD Category, Product and ProductImage with derived price, stock and rating"
```

---

### Task 5: SearchHistory replaces RecentSearch

**Files:**
- Modify: `marketplacex/modules/cart/models.py` (delete `RecentSearch`), `marketplacex/modules/cart/service.py:130-155`, `marketplacex/modules/search/models.py` (add `SearchHistory`), `marketplacex/modules/search/routes.py`, templates listing recent searches
- Test: `tests/test_search.py`

**Interfaces:**
- Produces: `SearchHistory` in `search/models.py` — table `SearchHistory`: `id`→`searchHistoryID`, `customer_id`→`customerID` FK `Customer.customerID`, `keyword` String(255), `search_type`→`searchType` String(255) (`"text"` or `"image"`), `searched_at`→`searchedAt` DateTime.
- `cart.record_search(account, text: str, search_type: str = "text") -> None` — no-op for accounts without `customer`; same de-dup/limit behaviour as today. `recent_searches(account) -> list[SearchHistory]` (text only, newest first), `delete_recent(account, history_id)`.
- Image searches record keyword `"[image]"` with `search_type="image"` (wired in Task 6).

- [ ] **Step 1: Write the failing test**

```python
def test_search_history_rows(client, alice, login):
    from marketplacex.modules.search.models import SearchHistory
    login(client, alice)
    client.get("/search?q=sneakers")
    row = SearchHistory.query.one()
    assert (row.keyword, row.search_type, row.customer_id) == ("sneakers", "text", alice.customer.id)
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest -q tests/test_search.py::test_search_history_rows` → FAIL (ImportError).
- [ ] **Step 3: Implement as specified; update existing recent-search tests to the new names.**
- [ ] **Step 4: Run the full suite** — `.venv/bin/pytest -q` → all pass.
- [ ] **Step 5: Commit** — `git commit -m "feat: ERD SearchHistory table for customer searches"`

---

### Task 6: Real feature vectors and image search by upload

**Files:**
- Modify: `marketplacex/modules/search/images.py` (rewrite), `marketplacex/modules/search/query.py:77-90`, `marketplacex/modules/search/routes.py`, `marketplacex/modules/search/service.py:100-106`, `marketplacex/templates/customer/search.html` (upload form replaces sample-image buttons; add "Find similar" link on product page), `marketplacex/seed.py` (prototype vectors), `requirements.txt` (`Pillow>=10`)
- Test: `tests/test_search.py`

**Interfaces:**
- Produces (`search/images.py`):
  - `feature_vector(image_bytes: bytes) -> list[float]` — open with Pillow, convert RGB, resize 64×64, 4×4×4 RGB histogram (64 bins), L2-normalised. Raises `ValidationError("That file is not an image")` on `PIL.UnidentifiedImageError`.
  - `pack(vec: list[float]) -> bytes` / `unpack(b: bytes | None) -> list[float] | None` — `struct` float32 little-endian.
  - `solid_image(rgb: tuple[int, int, int]) -> bytes` — 64×64 PNG of one colour (used by the test seed and tests).
- `build_query(mode, text="", image_vector: list[float] | None = None, ...)` replaces `image_key`.
- Routes: `POST /search/image` (multipart field `photo`) → computes vector, records history `("[image]", "image")`, renders results; `GET /search?similar=<product_id>` uses that product's `image_vector`.
- `search.service.search`: image mode keeps products with `cosine >= 0.5`, sorted by similarity desc, max 48.
- Prototype seed: each `PRODUCTS` entry's `color` maps to an RGB (`black (20,20,20)`, `white (240,240,240)`, `beige (225,200,160)`) and its vector is `pack(feature_vector(solid_image(rgb)))`.

- [ ] **Step 1: Write the failing tests**

```python
def test_feature_vector_shape_and_similarity():
    from marketplacex.modules.search.images import feature_vector, solid_image
    from marketplacex.modules.search.ranking import cosine
    black, black2, white = (feature_vector(solid_image(c)) for c in [(20, 20, 20), (25, 25, 25), (240, 240, 240)])
    assert len(black) == 64
    assert cosine(black, black2) > 0.99 and cosine(black, white) < 0.1

def test_upload_black_photo_finds_black_products(client, seeded):
    import io
    from marketplacex.modules.search.images import solid_image
    r = client.post("/search/image", data={"photo": (io.BytesIO(solid_image((20, 20, 20))), "q.png")},
                    content_type="multipart/form-data")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Biti&#39;s Hunter Black Sneakers" in html and "Women Linen Summer Dress" not in html

def test_upload_non_image_flashes_error(client, seeded):
    import io
    r = client.post("/search/image", data={"photo": (io.BytesIO(b"not an image"), "x.jpg")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200 and "That file is not an image" in r.get_data(as_text=True)
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest -q tests/test_search.py -k "vector or upload"` → FAIL.
- [ ] **Step 3: Implement as specified; delete `SAMPLE_IMAGES` and update old image-search tests to upload `solid_image` bytes; remove Task 4 xfail markers.**
- [ ] **Step 4: Run the full suite** — `.venv/bin/pytest -q` → all pass.
- [ ] **Step 5: Commit** — `git commit -m "feat: colour-histogram feature vectors and image search by photo upload"`

---

### Task 7: Tiki.vn catalogue snapshot

**Files:**
- Create: `scripts/fetch_tiki.py`, `marketplacex/data/tiki_catalog.json` (generated), `marketplacex/tiki.py` (pure helpers, importable by tests and seed)
- Test: `tests/test_tiki_snapshot.py`

**Interfaces:**
- `marketplacex/tiki.py`:
  - `CATEGORIES: list[tuple[str, int, str]]` — `(name, tiki_category_id, shop_name)`: `("Phones", 1789, "TechZone")`, `("Laptops", 8095, "TechZone")`, `("Home appliances", 1882, "HomeNest")`, `("Fashion", 931, "StyleHub")`, `("Beauty", 1520, "GlowUp Beauty")`, `("Books", 8322, "ReadMore Books")`, `("Sports", 1975, "FitLife")`, `("Food & drinks", 4384, "HomeNest")`. If a listing for an id returns < 65 items, the fetcher logs it and the engineer picks a sibling Tiki category id that does, updating this table.
  - `clean_description(html: str | None) -> str` — strip tags and entities, collapse whitespace, truncate to 255 chars (cut at 252 + `"..."` when longer).
  - `snapshot_path() -> str` — `marketplacex/data/tiki_catalog.json`.
  - `load_snapshot() -> dict` — `{"source", "fetched_at", "categories": [{"name", "shop", "products": [...]}]}`; product keys: `tiki_id, name, brand, description, price, list_price, rating, review_count, sold, images (≤3 URLs), options (≤3 variant names), vectors (list of base64 float32 or null, parallel to images)`.
- `scripts/fetch_tiki.py` — listing `https://tiki.vn/api/personalish/v1/blocks/listings?limit=40&category=<id>&page=<n>` until 65 unique products with price > 0 and ≥1 image; detail `https://tiki.vn/api/v2/products/<id>` for description, images (`base_url`, ≤3), `configurable_options`; `time.sleep(0.3)` between calls; user-agent `Mozilla/5.0`; for the first image downloads it and stores `pack(feature_vector(...))` base64-encoded (other images `null`). Run with `.venv/bin/python -I scripts/fetch_tiki.py` (it adds the repo to `sys.path` itself). Writes the JSON with `indent=1, ensure_ascii=False`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tiki_snapshot.py
from marketplacex import tiki

def test_clean_description():
    assert tiki.clean_description("<p>Hello&nbsp;<b>world</b></p>") == "Hello world"
    long = tiki.clean_description("<p>" + "a" * 400 + "</p>")
    assert len(long) == 255 and long.endswith("...")
    assert tiki.clean_description(None) == ""

def test_snapshot_has_50_plus_per_category():
    snap = tiki.load_snapshot()
    assert len(snap["categories"]) == 8
    for c in snap["categories"]:
        assert len(c["products"]) >= 50, c["name"]
        for p in c["products"]:
            assert p["price"] > 0 and p["images"] and all(len(u) <= 500 for u in p["images"])
            assert len(p["description"]) <= 255
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest -q tests/test_tiki_snapshot.py` → FAIL (no module).
- [ ] **Step 3: Implement `marketplacex/tiki.py` and `scripts/fetch_tiki.py`, then run the fetcher**

Run: `.venv/bin/python -I scripts/fetch_tiki.py`
Expected: prints one line per category ending `65 products`, and the JSON file exists (~1–3 MB).

- [ ] **Step 4: Run the tests** — `.venv/bin/pytest -q tests/test_tiki_snapshot.py` → PASS.
- [ ] **Step 5: Commit** — `git add marketplacex/tiki.py scripts/fetch_tiki.py marketplacex/data/tiki_catalog.json tests/test_tiki_snapshot.py && git commit -m "feat: Tiki.vn catalogue snapshot, 8 categories x 65 products"`

---

### Task 8: Production seed and `init-db` command

**Files:**
- Create: `marketplacex/seed_tiki.py`
- Delete: `marketplacex/seed_bulk.py`, `marketplacex/data/catalog.json`, `tests/test_bulk_catalog.py`
- Modify: `marketplacex/app.py` (`_register_cli`: replace `seed` with `init-db`), `marketplacex/seed.py` (drop the `seed_bulk` import; `run()` removed — tests use `seed_all_for_tests`)
- Test: `tests/test_seed_tiki.py`

**Interfaces:**
- `seed_tiki.run(snapshot: dict | None = None) -> dict` — seeds a fresh database from `tiki.load_snapshot()` (or the passed dict) and returns counts `{"categories", "products", "customers", "orders", "reviews"}`. It creates:
  - accounts via `identity.create_account`: `admin@demo` (admin); one seller per distinct shop in `tiki.CATEGORIES`, email `<shop-slug>@demo` (e.g. `techzone@demo`); customers `alice@demo` plus 9 more with Vietnamese names in First Middle Last order (e.g. "Binh Van Tran") and addresses spread over Hanoi and Ho Chi Minh City with real ward/district names. Password `demo123` for all.
  - shops (verified), categories (description `f"{name} from Tiki.vn"`), products via `catalog.create_product` with `status="active"`, stock `random.Random(tiki_id).randint(20, 200)`, variants = `options` or `["Default"]`, offer rating fields from the snapshot.
  - vouchers by reusing `seed.seed_promotions()`; 2 delivered orders per customer on deterministic products with one review each (rating 4 or 5); one chat conversation for alice.
- CLI `flask --app marketplacex.app init-db [--reset]`:
  - without `--reset`, if any `account` row exists, print `Database already initialised; use --reset to wipe and reseed.` and exit with code 1;
  - with `--reset`, `db.drop_all()` first;
  - then `db.create_all()`, `policy.ensure_defaults()`, `seed_tiki.run()`, and on Postgres `enable_rls()`; prints the counts.
- `marketplacex/app.py::enable_rls() -> int` — for each table in `db.metadata.sorted_tables` executes `ALTER TABLE <quoted name> ENABLE ROW LEVEL SECURITY` (quote via `db.engine.dialect.identifier_preparer.quote`); returns the number of tables; no-op returning 0 unless `db.engine.dialect.name == "postgresql"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_seed_tiki.py
import copy
from marketplacex import tiki

def _small_snapshot():
    snap = copy.deepcopy(tiki.load_snapshot())
    for c in snap["categories"]:
        c["products"] = c["products"][:3]
    return snap

def test_seed_tiki_small(app):
    from marketplacex import seed_tiki
    from marketplacex.modules.catalog.models import Product
    counts = seed_tiki.run(_small_snapshot())
    assert counts["categories"] == 8 and counts["products"] == 24 and counts["customers"] == 10
    p = Product.query.first()
    assert p.images and p.price > 0 and p.stock_quantity >= 20

def test_init_db_refuses_when_populated(app):
    from marketplacex.modules.identity import service
    service.create_account("x@x.vn", "X", "admin", "secret1")
    r = app.test_cli_runner().invoke(args=["init-db"])
    assert r.exit_code == 1 and "already initialised" in r.output

def test_enable_rls_noop_on_sqlite(app):
    from marketplacex.app import enable_rls
    assert enable_rls() == 0
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest -q tests/test_seed_tiki.py` → FAIL.
- [ ] **Step 3: Implement as specified; delete the old bulk seed files.**
- [ ] **Step 4: Run the full suite, then seed a local SQLite file end to end**

Run: `.venv/bin/pytest -q && DATABASE_URL=sqlite:////tmp/mx_full.db .venv/bin/flask --app marketplacex.app init-db --reset`
Expected: tests pass; output shows `products: 520` (or the snapshot total) and 8 categories.

- [ ] **Step 5: Commit** — `git commit -m "feat: init-db command seeding the Tiki catalogue; remove old bulk seed"`

---

### Task 9: Supabase connection, smoke test, live verification

**Files:**
- Modify: `marketplacex/config.py` (committed: engine options; local-only: hard-coded URL), `requirements.txt` (`psycopg2-binary>=2.9`), `pytest.ini` (register marker, skip by default), `README.md` (setup, `init-db`, demo accounts, roles)
- Create: `tests/test_supabase.py`

**Interfaces:**
- `Config.SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_size": 5}` only when the URL starts with `postgresql`; SQLite keeps defaults (`pool_size` is invalid for SQLite's pool).
- `pytest.ini`: `markers = supabase: hits the live Supabase database` and `addopts = -m "not supabase"`.
- Local working copy only (never staged): `DATABASE_URL` default `postgresql+psycopg2://postgres.vmzbgxyibhhvoucpugwd:<password>@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres?sslmode=require` with the password the user supplied.

- [ ] **Step 1: Write the smoke test**

```python
# tests/test_supabase.py
import os
import pytest
from sqlalchemy import create_engine, inspect, text

pytestmark = pytest.mark.supabase
ERD = {
    "Address": {"addressID", "ward", "street", "detail"},
    "FullName": {"fullNameID", "firstName", "middleName", "lastName"},
    "Customer": {"customerID", "fullNameID", "addressID", "email", "phoneNumber"},
    "SearchHistory": {"searchHistoryID", "customerID", "keyword", "searchType", "searchedAt"},
    "Category": {"categoryID", "name", "description"},
    "Product": {"productID", "categoryID", "name", "brandName", "description", "price", "stockQuantity",
                "avgRating", "createdAt", "updatedAt"},
    "ProductImage": {"imageID", "productID", "imageUrl", "featureVector"},
}

@pytest.fixture(scope="module")
def engine():
    from marketplacex.config import Config
    return create_engine(Config.SQLALCHEMY_DATABASE_URI)

def test_erd_tables_and_columns(engine):
    insp = inspect(engine)
    for table, cols in ERD.items():
        assert cols <= {c["name"] for c in insp.get_columns(table)}, table

def test_fifty_products_per_category(engine):
    with engine.connect() as c:
        rows = c.execute(text('SELECT "categoryID", count(*) FROM "Product" GROUP BY 1')).all()
    assert len(rows) == 8 and all(n >= 50 for _, n in rows)

def test_rls_enabled_everywhere(engine):
    with engine.connect() as c:
        off = c.execute(text("SELECT relname FROM pg_class JOIN pg_namespace n ON n.oid = relnamespace "
                             "WHERE nspname = 'public' AND relkind = 'r' AND NOT relrowsecurity")).all()
    assert off == []
```

- [ ] **Step 2: Set the local URL (uncommitted), install, initialise Supabase**

Run: `.venv/bin/pip install -r requirements.txt && .venv/bin/flask --app marketplacex.app init-db --reset`
Expected: counts printed, `RLS enabled on N tables` with N equal to the number of models.

- [ ] **Step 3: Run the smoke test and the normal suite**

Run: `.venv/bin/pytest -q -m supabase && .venv/bin/pytest -q`
Expected: 3 passed; normal suite all pass.

- [ ] **Step 4: Manual verification in the running app**

Run `.venv/bin/flask --app marketplacex.app run` and check, recording what was seen: home shows Tiki products with photos; each of the 8 categories lists ≥50; text search "iphone" returns phones; photo upload search returns results; add to cart → checkout → pay succeeds as `alice@demo`; `techzone@demo` sees orders in the seller console; `admin@demo` sees the Cases tab; no support/risk link anywhere. Also confirm the Supabase dashboard's Table Editor shows the seven ERD tables.

- [ ] **Step 5: Commit (without the password)**

```bash
git add requirements.txt pytest.ini README.md tests/test_supabase.py
git add -p marketplacex/config.py   # stage only the engine-options hunk
git diff --cached | grep -cE 'vmzbgxyibhhvoucpugwd:[^@]+@'   # must print 0
git commit -m "feat: run on Supabase Postgres via session pooler; live smoke tests"
```
