# Supabase Postgres database per ERD, real Tiki.vn catalogue, three roles

Date: 2026-10-21
Status: approved in brainstorming, awaiting spec review

## Goal

Move MarketplaceX from SQLite to a fresh Supabase Postgres database whose core is the ERD in
`Picture1.png`, keep every existing marketplace feature by attaching the old tables to that core,
fill it with real product data (>50 products per category, real photos) from Tiki.vn, and reduce
the roles to customer, seller and admin.

Sub-project 1 of 2. Sub-project 2 (UI redesign with the impeccable skill) starts after this ships.

## Decisions

| Topic | Decision |
|---|---|
| ERD vs app | ERD tables are the core, created exactly as drawn; old tables attach to them |
| Data source | Tiki.vn public listing/detail API, snapshot committed to repo |
| Logins | One `account` table (email, password hash, role, status) for all roles; `Customer` links 1:1 via `accountID` |
| Price / stock | `Product.price` = lowest offer price, `Product.stockQuantity` = total available stock, both derived and kept in sync; Variant/Offer/StockLedger stay |
| Support / risk | Admin takes over disputes, not-received claims and stuck orders; risk holds removed entirely |
| Old data | Not migrated; fresh database with seed data only |
| `imageUrl` | `varchar(500)` instead of the ERD's `varchar(50)`: Tiki image URLs are ~90–130 characters. The ERD picture should be updated to match |

## Section 1 — Schema

### ERD tables (names and columns verbatim, quoted CamelCase in Postgres)

Added columns are appended; ERD columns are never renamed or removed.

| Table | ERD columns | Added columns | Replaces |
|---|---|---|---|
| `Address` | `addressID` PK, `ward`, `street`, `detail` | `customerID` FK, `recipient`, `phone`, `district`, `city`, `isDefault` | `address` |
| `FullName` | `fullNameID` PK, `firstName`, `middleName`, `lastName` | — | `user.name` (customers) |
| `Customer` | `customerID` PK, `fullNameID` FK, `addressID` FK (default address), `email`, `phoneNumber` | `accountID` FK unique | customer part of `user` |
| `SearchHistory` | `searchHistoryID` PK, `customerID` FK, `keyword`, `searchType` (`text`/`image`), `searchedAt` | — | `recent_search` |
| `Category` | `categoryID` PK, `name`, `description` | `parentID`, `attributeSchema` | `category` |
| `Product` | `productID` PK, `categoryID` FK, `name`, `brandName`, `description` varchar(255), `price` integer, `stockQuantity` integer, `avgRating` float, `createdAt`, `updatedAt` | `shopID` FK, `status`, `attributes`, `moderationReason` | `product` |
| `ProductImage` | `imageID` PK, `productID` FK, `imageUrl`, `featureVector` bytea | `sortOrder` | `product.image_url`, `product.image_vector` |

Relationships as in the ERD: Customer→FullName (1:1), Customer→Address (default), Customer→SearchHistory
(1:0..n), Category→Product (1:0..n), Product→ProductImage (1:1..n). A customer may own several
Address rows through `Address.customerID`.

### Kept tables

`account` (renamed from `user`), shop, variant, offer, stock ledger, reservation, cart, cart item,
saved item, checkout group, order, order item, order status history, payment attempt, refund,
provider callback, review, return case and related, shipment, tracking event, conversation, chat
message, notification, campaign, voucher, settlement, audit event, platform policy, clock, search
trace. Foreign keys that pointed at `user`/`product`/`category`/`address` point at the new tables.

### Removed

Support and risk modules: models, routes, services, templates, nav links, tests, and the
`risk_*` platform policies. `ROLES = ("customer", "seller", "admin")`.

### Derived fields

`catalog.sync_product(product)` recomputes `price` (min offer price), `stockQuantity` (sum of
ledger `available`), `avgRating` (from reviews) and `updatedAt`. It is called in the same
transaction as any offer price change, stock ledger change, or review create/update.

### Feature vectors

64-float colour/texture histogram (Pillow) of each product's primary image, stored as float32
bytes in `featureVector`. Image search computes the same vector for an uploaded photo and ranks by
cosine similarity. Replaces the hard-coded 3-dimension vectors in `search/images.py`.

### Supabase security

Row Level Security enabled on every table with no policies, closing the PostgREST anon API. The
app connects as `postgres`, which bypasses RLS.

## Section 2 — Real data

- `scripts/fetch_tiki.py` (one-off): 8 categories — Phones, Laptops, Home appliances, Fashion,
  Beauty, Books, Sports, Food & drinks — 65 products each (520 total). Listing + detail call per
  product; ~0.3 s between requests; browser user-agent.
- Output: `marketplacex/data/tiki_catalog.json`, committed. Seeding never calls Tiki.
- Mapping: name/brand/description (truncated to 255) → Product; price → offer price; list price →
  offer original price; rating/review count → `avgRating` and offer rating fields; up to 3 photos →
  ProductImage hot-linked from `salt.tikicdn.com`, first is primary; stock random 20–200.
- Variants: default single variant; up to 3 when Tiki lists options (colour/storage).
- Feature vectors computed once at fetch time and cached in the snapshot.
- Shops: ~6 themed shops (TechZone, HomeNest, StyleHub, GlowUp Beauty, ReadMore Books, FitLife),
  each with a seller account.
- Accounts: 1 admin, sellers, ~10 customers with Vietnamese names split into FullName and
  plausible HCMC/Hanoi addresses. README demo logins kept, minus support/risk.
- Also seeded: vouchers, a few completed orders, reviews.

## Section 3 — App, connection, testing

### Connection

- URL: `postgresql+psycopg2://postgres.vmzbgxyibhhvoucpugwd:<password>@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres?sslmode=require`
  (session pooler).
- Committed `config.py` reads `DATABASE_URL`; the local working copy hard-codes the URL and stays
  uncommitted (same as the Gemini key). The password never enters git.
- Engine options: `pool_pre_ping=True`, `pool_size=5`.
- Dependencies added: `psycopg2-binary`, `Pillow`.

### Commands

- `flask --app marketplacex.app init-db [--reset]`: create tables, enable RLS, seed from the
  snapshot. `--reset` drops everything first.
- App startup never creates or seeds on Postgres; auto create/seed remains only for tests and
  SQLite.

### Code

- Models rewritten for Section 1; all modules updated (FullName / account display name, Address,
  SearchHistory, ProductImage-based image search).
- Cart/checkout/order/payment keep working through Offer.
- New admin "Cases" tab: disputes, not-received claims, stuck orders, reusing the former support
  service code with role checks changed to admin. Order-detail buttons open admin cases.
- Risk evaluation removed from checkout and refunds.
- No UI redesign beyond these link/nav changes.

### Testing

- Existing suite stays on in-memory SQLite; models stay portable (`LargeBinary`, `JSON`).
- Support/risk tests deleted; equivalent admin-flow tests added or adapted.
- New tests: `sync_product`, SearchHistory recording, ProductImage image search, seed counts
  (every category ≥ 50 products).
- `@pytest.mark.supabase` smoke test (skipped by default): seven ERD tables exist with exactly the
  ERD columns plus the documented additions, every category ≥ 50 products, RLS enabled on every
  table.
- Manual run on Supabase: browse, search, cart, checkout, seller and admin logins.

## Out of scope

UI redesign (sub-project 2), Supabase Storage for uploads, migration of old SQLite data.
