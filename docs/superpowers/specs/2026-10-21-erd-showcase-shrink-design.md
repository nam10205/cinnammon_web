# Shrink to an 8-table ERD showcase

Date: 2026-10-21
Status: approved in brainstorming, awaiting spec review
Supersedes: the schema and module scope of `2026-10-21-supabase-erd-database-design.md`

## Goal

The site exists to showcase the ERD in `Picture1.png`. The database shrinks to exactly 8 tables:
the 7 ERD tables with their drawn columns and nothing added, plus one new `Order` table. The
app keeps the basic shop functions (browse, search, cart, checkout, payment, shipping) but
stores nothing outside those 8 tables.

## Decisions

| Topic | Decision |
|---|---|
| Tables | Exactly 8: `FullName`, `Address`, `Customer`, `SearchHistory`, `Category`, `Product`, `ProductImage`, `Order` |
| ERD columns | Exactly as drawn, no additions. Only type change: `imageUrl` varchar(500) (Tiki URLs ~100 chars) |
| Order | One product per row; columns chosen freely since the table is new; no order-line table |
| Logins | No passwords. Login page: 3 quick buttons (Customer Alice, Seller, Admin) + log in by email + sign up |
| Seller / Admin | Hard-coded roles in the app, not database rows. One implicit shop |
| Cart | Browser session only |
| Payment | Simulated card or cash on delivery, stored on `Order` |
| Shipping | Simulated, advances by time: placed → processing → shipped → delivered, 20 s per step |
| Search | Text, voice (mic button, Web Speech API) and image upload, each recorded in `SearchHistory` |
| Data | Keep the Tiki snapshot: 8 categories × 65 products, up to 3 images each |
| Approach | Strip the current app in place; delete every module and table outside this scope |

## Section 1 — Schema

Postgres table names are quoted CamelCase as drawn; keys are `integer`.

| Table | Columns |
|---|---|
| `FullName` | `fullNameID` PK, `firstName`, `middleName`, `lastName` |
| `Address` | `addressID` PK, `ward`, `street`, `detail` |
| `Customer` | `customerID` PK, `fullNameID` FK→FullName, `addressID` FK→Address, `email` (unique), `phoneNumber` |
| `SearchHistory` | `searchHistoryID` PK, `customerID` FK→Customer, `keyword`, `searchType`, `searchedAt` |
| `Category` | `categoryID` PK, `name`, `description` |
| `Product` | `productID` PK, `categoryID` FK→Category, `name`, `brandName`, `description` varchar(255), `price` integer, `stockQuantity` integer, `avgRating` float, `createdAt`, `updatedAt` |
| `ProductImage` | `imageID` PK, `productID` FK→Product, `imageUrl` varchar(500), `featureVector` bytea |
| `Order` | `orderID` PK, `customerID` FK→Customer, `productID` FK→Product, `addressID` FK→Address, `quantity` integer, `unitPrice` integer, `shippingFee` integer, `totalPrice` integer, `paymentMethod` varchar, `paymentStatus` varchar, `status` varchar, `orderedAt` timestamp, `shippedAt` timestamp null, `deliveredAt` timestamp null |

Value sets:

- `searchType`: `text`, `voice`, `image`
- `paymentMethod`: `cod`, `card`
- `paymentStatus`: `unpaid`, `paid`, `refunded`
- `status`: `placed`, `processing`, `shipped`, `delivered`, `cancelled`

Consequences of the exact ERD:

- A customer has one address, `Customer.addressID`. Editing it in the profile inserts a new
  `Address` row and repoints the customer, so existing orders keep the address they shipped to.
- `Address.detail` holds house number plus district/city (e.g. "12A, Quận 1, TP.HCM").
- `price`, `stockQuantity`, `avgRating` are plain columns. `avgRating` comes from Tiki and is
  never recomputed. `updatedAt` changes on product edits and stock changes.
- `description` is truncated to 255 characters.
- Image order is `imageID` order; the first image is the primary. `featureVector` is the
  64-float colour histogram (float32 bytes) of that image, or null when it could not be fetched.
- Row Level Security is enabled on all 8 tables with no policies; the app connects as `postgres`.

## Section 2 — Website

### Login and session

- Login page buttons: "Customer (Alice)" logs in as `alice@demo`; "Seller" and "Admin" set the
  hard-coded role. The session holds `role` and, for customers, `customer_id`.
- Log in by email: case-insensitive match on `Customer.email`; an unknown email shows an error.
- Sign up: first name, middle name (optional), last name, email, phone, ward, street, detail.
  All other fields required; a duplicate email is rejected. Creates FullName, Address,
  Customer and logs the new customer in.
- Logout clears the session, including the cart.

### Visitor (not logged in)

Home (categories, a few products each), category page (sort by price or rating, price filter),
product page (images, price, stock, rating, "Find similar"), all three search types. Searches are
not recorded. Adding to cart works; checkout requires login as a customer.

### Search

- Text: the search box.
- Voice: a mic button beside the box, using the browser's speech recognition; the recognised
  words fill the box and submit with type `voice`. The button is hidden where the browser lacks
  speech recognition. macOS dictation into the box also works and records as `text`.
- Image: upload a photo; results ranked by cosine similarity to `featureVector`. Keyword stored
  is the uploaded file's name.
- "Find similar" on a product page ranks by that product's vector.
- For a logged-in customer each search inserts a `SearchHistory` row; the search page shows that
  customer's recent searches.

### Customer

- Cart (session): add, change quantity, remove; quantities capped at current stock.
- Checkout: shows the customer's current address; choose payment method.
  - Card: a demo card form; only `4242 4242 4242 4242` (spaces ignored) succeeds. A declined
    card creates no orders. No card data is stored.
  - Creates one `Order` row per cart line in one transaction, all with the same `orderedAt`,
    `addressID` = the customer's current address, `unitPrice` = current product price.
  - Shipping fee: 30,000₫ if the cart subtotal is under 500,000₫, otherwise 0; charged on the
    first row only. `totalPrice` = `quantity × unitPrice + shippingFee`.
  - Stock is checked for every line before any row is written; any shortfall aborts the whole
    checkout. Stock is decremented on success.
  - `paymentStatus`: `paid` for card, `unpaid` for COD.
- My orders: grouped by `orderedAt`; order page shows a progress bar
  (Placed · Processing · Shipped · Delivered) that polls every 5 s.
- Cancel: allowed while `placed` or `processing`. Restores stock; `paid` becomes `refunded`.
- Profile: edit names, phone and address (new Address row as above). Email is not editable.

### Simulated shipping

- `STEP_SECONDS = 20`, one constant.
- Due times: `processing` at `orderedAt + 20 s`; `shipped` at `orderedAt + 40 s`;
  `delivered` at `shippedAt + 20 s`.
- No background worker. Any code that reads orders first advances every non-final order whose
  step is due, stamping `shippedAt` / `deliveredAt` with the due time, not the read time. A COD
  order becomes `paid` on delivery.
- Seller "Skip to next step" moves an order one step now and stamps the current time.

### Seller (hard-coded)

- Products: list with search and category filter; add / edit name, brand, description, price,
  stock, category; add image by URL (vector computed by fetching it, null on failure); remove image.
- Orders: all orders with live status and the skip button.

### Admin (hard-coded)

- Overview: row counts for all 8 tables.
- Categories: add, edit, delete (only when it has no products).
- Customers: list; detail shows full name, address, orders and search history.
- Orders: all orders; cancel (same rules as customer cancel).

### Assistant

The Gemini chat bubble stays. Its context is products and the asking customer's orders only;
voucher and return-policy context is removed. No table.

## Section 3 — Code, Supabase, testing

### Kept and slimmed

`catalog`, `search`, `identity`, `cart` (session), `order` (checkout, payment, shipping),
`seller`, `admin`, `assistant`; `tiki.py`, `data/tiki_catalog.json`, `seed_tiki.py`,
`init-db [--reset]`, `enable_rls()`.

### Deleted

Modules: inventory, checkout, payment, logistics, returns, review, chat, promotion, settlement,
cases, notification, audit, reporting. Also `adapters/`, platform policies, the prototype
`seed.py`, their templates and tests. Settings worth keeping become constants
(`SHIPPING_FEE = 30_000`, `FREE_SHIPPING_FROM = 500_000`, `STEP_SECONDS = 20`).

### Seed

8 categories × 65 products from the snapshot; 10 customers with Vietnamese names and addresses
(Alice = `alice@demo`); ~30 search history rows across all three types; ~20 orders dated over
the past weeks, mixed card/COD, mostly delivered, a couple cancelled.

### Supabase

`init-db --reset` drops every existing table (the current 46), creates the 8, enables RLS and
seeds. The connection URL with the password stays only in the uncommitted local `config.py`.

### Testing

Pytest on in-memory SQLite, rewritten for the smaller app:

- quick logins, email login (unknown, case-insensitive), sign-up (duplicate email, missing fields)
- profile address edit creates a new Address; old orders keep theirs
- cart caps at stock
- multi-line checkout, shipping-fee threshold (499,999 vs 500,000), card accept/decline, COD
- step advancement with a controllable clock, including stamps equal to due times
- cancel allowed only in `placed`/`processing`; stock restored; refund on paid
- seller/admin pages refuse customers and visitors; customer pages refuse seller/admin
- search history for text, voice and image; none for visitors; image and similar search ranking
- admin category delete refused when not empty
- seed: 8 tables populated, every category ≥ 50 products

`@pytest.mark.supabase` smoke test: exactly these 8 tables exist, each with exactly the columns
above, RLS on, every category ≥ 50 products. Manual click-through on Supabase.

## Out of scope

UI redesign with the impeccable skill (next sub-project), real payments, real carriers,
reviews, chat, vouchers, returns.
