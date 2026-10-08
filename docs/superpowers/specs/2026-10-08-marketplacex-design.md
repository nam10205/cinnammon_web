# MarketplaceX Demo Website — Design Spec

Date: 2026-10-08
Source: `docs/marketplacex-analysis-design.docx` (Tran Quang Tien, "Shopee-like Multivendor E-Commerce Platform" report)

## 1. Intent

- **Purpose:** a course deliverable that demonstrates the report's design is implementable. It runs locally with seeded data and is presented live.
- **Constraint:** must be buildable in a few hours.
- **Success criteria:**
  1. Every use case in Figure 1 (use case diagram) can be performed through the UI by the matching actor.
  2. Every entity in report §8.1, plus the classes the use cases need, exists as a persisted model with the stated relationships and constraints.
  3. Business rules BR01–BR08 and the order state machine (§9.5) are enforced in code and covered by tests.
  4. Module and method names match the report (component diagram, §7 interfaces), so the report-to-code traceability in §15.3 holds.
- **Strategy:** breadth over depth. Infrastructure-heavy non-functional requirements are simulated or documented as out of scope (§9 of this spec).

## 2. Stack and Architecture

- Python 3.9+ (the machine has 3.9.6), Flask, Flask-SQLAlchemy, SQLite, Jinja templates, Bootstrap 5 via CDN, pytest.
- **Modular monolith.** The report's §15 explicitly permits this as a first stage. Each service in Figure 2 is one module.

```
marketplacex/
  app.py            # create_app(), registers blueprints
  config.py
  extensions.py     # db, event bus
  events.py         # in-process publish/subscribe + EventLog table
  errors.py         # domain exceptions
  seed.py           # demo data
  modules/
    identity/ catalog/ seller/ search/ cart/ promotion/ checkout/ order/
    inventory/ payment/ logistics/ review/ returns/ support/ risk/
    chat/ notification/ settlement/ reporting/ admin/ audit/
      each: models.py, service.py, routes.py (where it has UI)
  adapters/
    payment_provider.py  logistics_provider.py  notification_provider.py
  templates/ base.html, customer/, seller/, admin/, support/, risk/
  static/sample_images/
tests/
README.md
```

### 2.1 Dependency rules (from report §7.2)
- Routes call only their module's `service.py`. Templates never query models.
- A module writes only its own tables. Cross-module effects go through another module's service function or an event.
- External callbacks enter via `adapters/` and are converted into service calls.
- Notifications, settlement and reporting react to events, not direct calls.

### 2.2 Event bus
- `events.publish(name, aggregate_id, payload)` appends to an `EventLog` table (eventId, name, aggregateId, occurredAt, payload JSON) and calls the subscribers registered in-process, synchronously.
- Events used:
  - `OrderCreated`
  - `OrderStatusChanged`
  - `PaymentAuthorized`
  - `PaymentChanged`
  - `TrackingChanged`
  - `ReturnStatusChanged`
  - `RiskDecisionMade`
  - `ProductChanged`
- Consumers record processed event ids (`ProcessedEvent`) so redelivery is safe.

### 2.3 Authentication
- Session-based login with hashed passwords (werkzeug).
- A **demo login switcher** on the login page offers one-click login as each seeded role.
- Role checks use a `@require_role(...)` decorator. Resource ownership is checked in services (deny by default).

## 3. Domain Model (class diagram)

Money is integer VND (`*_vnd` columns). Quantities are non-negative (DB check constraints). Mutable operational rows carry `version` for optimistic concurrency.

| Module | Class | Key fields / relationships |
|---|---|---|
| identity | User | id, email, password_hash, name, role ∈ {customer, seller, admin, support, risk}, status ∈ {active, suspended} |
| identity | Address | user_id → User (1..*), recipient, phone, line, city, is_default |
| seller | Shop | id, owner_id → User (Seller 1..* Shop), name, location, verification_status ∈ {unverified, pending, verified, rejected}, verification_info |
| catalog | Category | id, name, parent_id (tree), attribute_schema (JSON list of required attribute names) |
| catalog | Product | id, shop_id, category_id, title, description, brand, attributes (JSON), status ∈ {draft, pending, active, rejected, suspended}, moderation_reason, image_vector (JSON 3 floats), image_url, created_at |
| catalog | Variant | id, product_id (Product 1..*), name, sku; unique (product_id, name) |
| catalog | Offer | id, shop_id, variant_id, price_vnd, original_price_vnd, purchase_limit, sold_count, rating_avg, rating_count, version. **BR01:** unique (shop_id, variant_id) |
| inventory | StockLedger | offer_id (one per fulfilment location, single default location), available, reserved, committed, version |
| inventory | Reservation | id, offer_id, attempt_id, qty, expires_at, status ∈ {held, committed, released}; unique (offer_id, attempt_id) |
| cart | Cart | id, customer_id (0..1 active), version |
| cart | CartItem | cart_id, offer_id, qty, selected |
| cart | SavedItem | customer_id, kind ∈ {product, shop}, target_id |
| cart | RecentSearch | customer_id, query_text, created_at |
| promotion | Campaign | id, name, budget_vnd, spent_vnd, starts_at, ends_at, active |
| promotion | Voucher | id, campaign_id, code, kind ∈ {percent, fixed, free_shipping}, value, min_spend_vnd, max_discount_vnd, shop_id (null = platform voucher), usage_limit, used_count |
| promotion | Redemption | id, voucher_id, customer_id, campaign_id, attempt_id, order_group_id, amount_vnd, status ∈ {held, committed, released}. **BR04:** unique (customer_id, campaign_id, attempt_id) |
| checkout | CheckoutGroup | id, customer_id, idempotency_key (unique per customer), quote_hash, quote_expires_at, cart_version, status ∈ {quoted, placing, completed, failed}, merchandise_vnd, discount_vnd, shipping_vnd, total_vnd, failure_reason |
| order | Order | id, group_id (CheckoutGroup 1..*), shop_id, customer_id, address_snapshot (JSON), status, merchandise_vnd, discount_vnd, shipping_vnd, total_vnd, delivered_at, version |
| order | OrderItem | order_id (1..*), offer_id, title_snapshot, variant_snapshot, unit_price_vnd, qty, discount_vnd |
| order | OrderStatusHistory | order_id, from_status, to_status, actor_id, reason, at |
| payment | PaymentAttempt | id, group_id (CheckoutGroup 1..*), amount_vnd, status ∈ {pending, authorized, captured, failed, voided}, provider_ref (unique), captured_vnd |
| payment | Refund | id, payment_id, return_case_id, amount_vnd, idempotency_key (unique), status ∈ {pending, succeeded, failed}, provider_ref |
| logistics | Shipment | id, order_id (Order 0..*), kind ∈ {forward, return}, return_case_id, carrier, tracking_no, label_url, status, weight_g, promised_pickup_at |
| logistics | TrackingEvent | shipment_id, seq, status, location, at (ordered) |
| review | Review | id, order_item_id, customer_id, rating 1–5, comment, seller_reply, status ∈ {visible, hidden}. **BR06:** unique (order_item_id) |
| returns | ReturnCase | id, order_id, customer_id, reason, remedy ∈ {refund_only, return_and_refund}, status, seller_response, seller_deadline, inspection_result, refund_amount_vnd |
| returns | ReturnCaseItem | case_id, order_item_id, qty |
| returns | Evidence | case_id, author_id, kind ∈ {statement, image}, content/url, at (append-only) |
| returns | DisputeDecision | case_id (0..1), decided_by, reason_code, outcome ∈ {refund_customer, side_with_seller, partial}, amount_vnd, note, at (immutable) |
| support | SupportCase | id, customer_id, order_id, subject, status ∈ {open, pending, resolved}, assignee_id |
| support | CaseNote | case_id, author_id, body, at |
| risk | RiskAlert | id, target_type ∈ {checkout, refund, account}, target_id, rule, score, status ∈ {open, held, released, dismissed}, decided_by, reason |
| chat | Conversation | id, customer_id, shop_id; unique pair |
| chat | ChatMessage | conversation_id, sender_id, body, at |
| notification | Notification | id, user_id, channel ∈ {in_app, email, sms, push}, template, body, status ∈ {sent, failed}, created_at, read_at |
| settlement | LedgerEntry | id, order_id, shop_id, account ∈ {customer_payment, seller_payable, platform_fee, shipping, voucher_funding, refund}, debit_vnd, credit_vnd, status ∈ {held, released}, entry_group (balanced per group) |
| admin | PlatformPolicy | key, value (return_window_days, platform_fee_pct, seller_response_hours, reservation_ttl_min, risk thresholds) |
| admin | Clock | single-row demo time offset ("fast-forward") used by all `now()` calls |
| audit | AuditEvent | actor_id, role, action, target_type, target_id, reason, before_digest, after_digest, correlation_id, at (append-only) |
| events | EventLog, ProcessedEvent | see §2.2 |

### 3.1 Order state machine (report §9.5, exact)

```
Draft          -> PendingPayment, Cancelled
PendingPayment -> Confirmed [paymentAuthorized], PaymentFailed, Cancelled
Confirmed      -> Preparing, Cancelled
Preparing      -> ReadyToShip, CancelRequested
ReadyToShip    -> Shipped [beforeHandover: not cancelled], CancelRequested
Shipped        -> Delivered [deliveryEvidenceValid], DeliveryException, ReturnRequested
Delivered      -> Completed, ReturnRequested [withinReturnWindow], Disputed
Completed      -> ReturnRequested [withinReturnWindow, policy permits]
ReturnRequested-> Returned, Rejected, Refunded
CancelRequested-> Cancelled, (back to previous state if seller declines)
```
- `order.service.transition(order, to, actor, reason)` is the **only** way to change status.
- It checks the table and guards, writes OrderStatusHistory and AuditEvent, then publishes `OrderStatusChanged` (the entry action). Notifications subscribe to that event.
- Illegal moves raise `IllegalTransition`.
- `Cancelled`, `Refunded`, `Returned`, `Rejected` and `PaymentFailed` are terminal in the demo.
- `DeliveryException` is set by the fake carrier's "fail delivery" option and can move back to `Shipped` (re-attempt) or to `Cancelled`.
- Order `Disputed` is used only when a customer disputes a Delivered order without a return (e.g. item not received). It moves to `Refunded` or `Completed` by support decision.
- Escalating a return dispute changes the **ReturnCase** status to `disputed`; the order stays `ReturnRequested`.

## 4. Business Rules → Enforcement

| Rule | Where enforced |
|---|---|
| BR01 offer = one shop + one variant | Offer unique constraint; catalog service |
| BR02 payable = merchandise − discounts + shipping + fees | `checkout.service.compute_totals`; server-only; client total never accepted |
| BR03 reserve stock before payment, release on timeout or cancel | inventory `reserve/commit/release`; saga order; expiry sweep |
| BR04 unique voucher redemption key | Redemption unique constraint; promotion `reserve` |
| BR05 approved state machine + audit | §3.1 |
| BR06 review needs delivered item, one per item | review service + unique constraint |
| BR07 refund ≤ captured − prior successful refunds | `payment.service.refund` |
| BR08 settlement held until return/dispute window | settlement ledger `held` → `released` on Completed |

## 5. Use Case → Screen Mapping

Every Figure 1 use case is listed. "FR" references the report.

### Customer
| Use case | Screen / behavior |
|---|---|
| Manage Account | Register, login, profile, address CRUD, saved items, recent searches with delete (FR01, FR08) |
| Discover Product | Home with category tree, campaign banner and shop pages; product detail showing variant, price, original price, shop, rating, sold count, delivery promise (FR02, FR06) |
| Search by Text | Query text → common `Query` object → ranking (FR03) |
| Search by Voice | Browser Web Speech API transcript (or typed transcript fallback) → same pipeline, `type='voice'` |
| Search by Image | Pick or upload a sample image. Seeded images map to 3-dim vectors; an unknown upload falls back to text with a "degraded" banner (§4.2) |
| (search features) | Filters: category, brand, price range, min rating, location, in-stock. Sorts: relevance, sales, rating, newest, price (ties broken by offer id). Facets. Empty result suggests which filter to relax. Each result shows a ranking trace id (FR04, FR05, §4.1) |
| Manage Cart | Items grouped by shop; change qty, select, remove; version increments; totals recalculated (FR07) |
| Checkout (+ Validate Cart, Apply Promotion, Reserve Stock, Authorize Payment, Create Order) | Quote page, then Place Order. See §6.1 |
| Track Order | Orders list; detail with status timeline (actor, time, reason) and shipment tracking events; Cancel button while the state machine allows (FR15, FR16) |
| Review Purchase | On delivered/completed items: rating + comment; one per item (FR19) |
| Request Return or Refund | Form: items + qty, reason, remedy, evidence (text + image upload) (FR17) |
| Escalate Dispute (extends Return) | Button visible when the seller rejects or the deadline passes → case goes to support (FR18) |
| Chat with Seller | Conversation per shop from product/shop/order page |
| Deliver Notification (included) | Bell icon inbox of notifications (FR20) |

### Seller (Seller Center)
| Use case | Screen / behavior |
|---|---|
| Manage Shop | Create/edit shop, submit verification info → admin verifies (FR21) |
| Manage Listing | Product create/edit with variants, attributes (validated against category schema), image; submit → pending moderation. Validation: required attributes, prohibited terms list, unique variant names, price range > 0 (UC03, FR22) |
| Manage Inventory and Price | Table of offers: price, original price, stock, purchase limit (FR23) |
| Fulfil Order (+ Create and Track Shipment) | Order queue: Accept (Confirmed→Preparing), Mark packed + weight + create shipment/label (→ReadyToShip), Hand over (→Shipped, blocked if cancelled), Reject with reason (→Cancelled + compensation). The fake carrier's "Advance tracking" button adds events and eventually marks Delivered (UC04, FR14, FR24) |
| Handle Return | Case inbox: accept, propose partial refund, reject with reason before deadline; mark inspection pass/fail when the return shipment arrives |
| View Settlement | Ledger statement per shop: held vs released, fees, refunds (FR25) |
| Chat with Customer | Conversations list |

### Administrator (Admin Portal)
| Use case | Screen / behavior |
|---|---|
| Manage Taxonomy | Category tree CRUD with attribute schema (FR26) |
| Manage Campaign | Campaign + platform voucher CRUD, budgets (FR26) |
| Configure Platform Policy | Edit PlatformPolicy values; prohibited-terms list; "fast-forward clock" demo control |
| Govern Users and Content | Moderation queue for pending listings (approve/reject with reason), shop verification, review hide, user suspend. Every action requires a reason code → AuditEvent (FR27, §4.4) |
| View Operational Report | Dashboard: orders by status, paid-to-packed time, cancellations by actor, refund aging, payment mismatches, zero-result search rate, notification failures (§4.5) |

### Support Agent
| Use case | Screen / behavior |
|---|---|
| Manage Support Case | Search customer/order/case; phone and email masked until "reveal" with a reason (audited); case notes (FR28) |
| Assist Dispute | Disputed return cases: immutable timeline + evidence bundle; record a reason-coded DisputeDecision that triggers refund or closes the case |

### Risk Analyst
| Use case | Screen / behavior |
|---|---|
| Review Risk Alert | Alert queue. Rules: checkout total > threshold, more than N vouchers per day for a customer, more than N refunds per 30 days, new account + high value (FR29) |
| Hold or Release Transaction | Hold keeps the checkout in PendingPayment (or the refund pending); Release resumes; Reject cancels with compensation |

### External providers (secondary actors)
| Use case | Behavior |
|---|---|
| Process Payment | `FakePaymentProvider.authorize` returns pending. The checkout result page offers "Simulate callback: success / fail / duplicate" (signed with an HMAC that the adapter verifies). Duplicate callbacks are no-ops (FR13, FR30) |
| Create and Track Shipment | `FakeLogisticsProvider.quote/create_shipment/next_event` |
| Deliver Notification | `FakeNotificationProvider.send` writes Notification rows; configurable failure rate for the report's "notification failure" metric |

## 6. Key Flows

### 6.1 Checkout saga (report §9.2)
1. `checkout.quote(customer, address_id, voucher_codes)`:
   - Load selected cart items and the cart version.
   - Reprice from Offer and check stock and purchase limits.
   - `promotion.evaluate` (platform + shop vouchers, min spend, caps, budget).
   - `logistics.quote` per shop package.
   - Compute BR02 totals per shop and for the group.
   - Create a CheckoutGroup(status=quoted) with `quote_hash = sha256(items, prices, vouchers, address, totals)` and `quote_expires_at = now + 10 min`.
2. `checkout.place_order(customer, group_id, idempotency_key, quote_hash)`:
   - If the key is already used by this customer → return the existing group outcome.
   - If the hash mismatches, has expired, or a recompute differs → `QuoteChanged` with the changed items listed.
   - `inventory.reserve(items, attempt_id, ttl)` → `promotion.reserve(redemptions, attempt_id, ttl)` → `risk.evaluate_checkout(ctx)`.
   - If the risk result is held: the group stays `placing`, orders are created in `PendingPayment`, and an alert is raised.
   - Otherwise: `payment.authorize(amount, token, attempt_id)` → PaymentAttempt pending → `order.create_orders(snapshot)` (one per shop, status PendingPayment).
3. The payment callback (verified) sets the attempt to authorized, publishes `PaymentAuthorized`, moves each order to Confirmed, commits inventory and promotion reservations, publishes `OrderCreated` → notifications, and clears the cart's selected items.
4. **Failure or timeout at any step:** release reservations and redemptions in reverse order, void the payment, move orders to PaymentFailed/Cancelled, set the group to failed. An expiry sweep (run at the start of each checkout/order request) releases reservations past TTL and cancels their PendingPayment orders.
5. **Invariants:** the client never sends totals; one provider_ref → one captured payment; a failed checkout always ends with no held stock or vouchers.

### 6.2 Cancellation
- Customer cancel is allowed in Draft, PendingPayment or Confirmed (direct to Cancelled), or Preparing/ReadyToShip (→CancelRequested, the seller approves).
- Cancelled → release or return stock, void or refund the payment.

### 6.3 Return, refund and dispute (report §9.4)
1. `returns.open_case(order_item(s), reason, remedy, evidence)` checks eligibility:
   - order Delivered/Completed
   - within `return_window_days` of delivered_at
   - qty ≤ purchased − already returned
   - no open case for the item
   - Ineligible → an error with the specific reason.
2. If eligible: create the case, order → ReturnRequested, set the seller deadline, notify the seller.
3. Seller accepts:
   - refund_only → refund.
   - return_and_refund → return Shipment, tracking, inspection pass → refund. Inspection fail → customer may escalate.
4. Seller rejects, or the deadline passes → customer may Escalate → case status `disputed` → Support DisputeDecision.
   - `refund_customer` / `partial` → refund.
   - `side_with_seller` → order `Rejected`.
5. Refund amount = (unit price × qty − proportional item discount), plus shipping if it's a full return.
   - `payment.refund(amount, idempotency_key)` enforces BR07.
   - Refund callback → case Refunded, order → Refunded, ledger refund entries.
6. Every privileged read or decision writes an AuditEvent.

### 6.4 Settlement
- On Delivered: write balanced ledger entries (customer_payment / seller_payable / platform_fee / shipping / voucher_funding), status `held`.
- On Completed (an admin "fast-forward" past the return window, then the "run settlement" button transitions eligible Delivered orders to Completed): entries → `released`.
- Refunds post reversing entries.

### 6.5 Search ranking (report §10.2)
- `Score = 0.55·lexical + 0.20·semantic + 0.10·offer_quality + 0.08·seller_quality + 0.05·delivery_fit + 0.02·freshness`.
- Lexical: token overlap of the normalized query with title/brand/category, with Vietnamese diacritics stripped and a small synonym dictionary (e.g. "giày"→"shoes").
- Semantic: cosine similarity of the image vector (image mode) or a keyword-derived vector (text mode).
- Hard filters (price ceiling parsed from "under 2 million"/"500k", category, stock, active status) apply before scoring.
- Sorts are deterministic (tie-break by offer id).
- Each search writes a SearchTrace row (trace id, query JSON, result count) for the zero-result metric.
- Seed data reproduces the report's prototype results: "black running shoes under 2 million" → Nike Air Zoom; "wireless mouse under 500k" (voice) → Logitech; the shoe image vector → Biti's Hunter.

## 7. Error Handling

- Domain exceptions in `errors.py`:
  - `IllegalTransition`
  - `InsufficientStock`
  - `PurchaseLimitExceeded`
  - `VoucherInvalid`
  - `VoucherExhausted`
  - `QuoteChanged`
  - `QuoteExpired`
  - `RefundExceedsCaptured`
  - `NotEligible`
  - `StaleVersion`
  - `Forbidden`
  - `InvalidSignature`
- A Flask error handler turns them into a flash message plus a redirect back (HTML), or JSON `{code, message, correlation_id}` for callback endpoints.
- A correlation id is generated per request and stored on AuditEvent and EventLog.
- Stale `version` on cart/offer edits → `StaleVersion`: "This item was updated elsewhere, please retry."

## 8. Testing

Pytest with an in-memory SQLite app fixture.

- **Unit tests:**
  - every legal transition in §3.1 passes and representative illegal ones (PendingPayment→Shipped, Cancelled→anything) raise
  - BR02 totals match the report example (2 Biti's shoes + 2 vouchers → 1,646,000 VND with 28,000 shipping)
  - BR04 duplicate redemption rejected
  - BR06 review on undelivered item / second review rejected
  - BR07 refund bound
  - inventory reserve/commit/release never goes negative
  - ranking reproduces the 3 prototype top results
- **Idempotency:**
  - the same `place_order` key twice → one group, one reservation set
  - a duplicate payment callback → one Confirmed transition
  - a bad signature → rejected
- **Compensation:** payment-fail callback → stock and vouchers released, orders PaymentFailed.
- **End-to-end (Flask test client):** search → add to cart → checkout → callback success → seller fulfil → carrier deliver → review → return → seller accept → refund → ledger balanced.

## 9. Out of Scope (documented in README as "designed, not built")

- Real MFA and device trust.
- Real payment, carrier, email and SMS providers (fake adapters only).
- Separate microservices, a real broker, CDN/WAF.
- Flash-sale waiting room and performance SLO verification.
- Real voice/image ML (simulated, as in the report's prototype).
- Multi-currency and multi-market.
- Full WCAG audit (semantic HTML + labels only).
- Data export/deletion orchestration.
- The deployment diagram infrastructure.

## 10. Seed Data

- **Users:**
  - customer `alice@demo`
  - 3 sellers, each with a verified shop: SportZone, TechHub, StyleHouse
  - `admin@demo`, `support@demo`, `risk@demo`
  - all with password `demo123`
- **Catalog:**
  - category tree: Fashion > Shoes, Fashion > Clothing, Electronics > Accessories, Beauty
  - the report's 12 prototype products with prices, ratings, sales, stock and image vectors
- **Promotions:** campaign "10.10 Sale" with a platform voucher (10% max 100k) and a shop voucher (fixed 80k).
- **Orders:** a few pre-made orders in Delivered, Shipped and Completed states, one open return case and one open risk alert, so every console has data at demo start.
- **Policy:** return window 7 days, platform fee 5%, seller response 48h, reservation TTL 15 min.

## 11. Report Traceability

The README includes a table mapping each Figure 1 use case, FR01–FR30, BR01–BR08 and Figure 2 component to its module, route and test, satisfying report §15.3.
