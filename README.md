# MarketplaceX — Shopee-like Multivendor Marketplace (demo)

A working implementation of the design in `docs/marketplacex-analysis-design.docx` (Information Systems Analysis and Design report, Trần Quang Tiến). Every use case in the report's use case diagram (Figure 1) can be performed in the browser by its actor. The domain model follows §8.1, business rules BR01–BR08 are enforced in code, and the order lifecycle follows the §9.5 state machine.

It is a **modular monolith**, which the report's §15 allows as the first stage: one Flask app whose packages map 1:1 to the services in the component diagram (Figure 2). Payment, carrier and notification providers are simulated adapters.

## Run it

Requires Python 3.9+.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/flask --app marketplacex.app seed      # (re)creates instance/marketplacex.db with demo data
.venv/bin/flask --app marketplacex.app run       # http://127.0.0.1:5000
.venv/bin/python -m pytest -q                    # full test suite
```

### Demo accounts (password `demo123`; the login page also has one-click demo buttons)

| Actor | Email | Notes |
|---|---|---|
| Customer | alice@demo | Has orders in every state, an open return, a held high-value checkout and a chat |
| Seller | sportzone@demo, techhub@demo, stylehouse@demo, gadgetpro@demo, homenest@demo, freshmart@demo, glowbeauty@demo, motoworld@demo | One verified shop each (the *seller* demo button logs in as SportZone) |
| More customers | binh@demo, chi@demo, dung@demo | Delivered orders with verified-purchase reviews |
| Administrator | admin@demo | Admin Portal, including demo clock and settlement controls |
| Support Agent | support@demo | Support Console |
| Risk Analyst | risk@demo | Risk Console |

### Demo data

- **207 products in 25 categories across 8 shops.**
  - The report's 12 prototype products keep their prices, ratings and search vectors, so §13.1's results still reproduce.
  - The other 194 come from a snapshot of [dummyjson.com/products](https://dummyjson.com/products), saved in `marketplacex/data/catalog.json` and loaded by `marketplacex/seed_bulk.py`. Their USD prices are converted at 25,000 ₫ per dollar.
- **Product photos load online**, from cdn.dummyjson.com and Wikimedia Commons.
  - Seeding works offline, but photos need internet. Without it, a placeholder image is shown.
  - Image search uses the prototype's three sample photos, so it only returns the 12 prototype products.

### Shopping assistant (Gemini chatbot)

Customer pages have a chat bubble in the lower-right corner.
- It answers questions about products, vouchers, shipping, returns and the logged-in customer's own orders.
- Each answer is based on our live product search, store policies and that customer's orders, so prices and links are real.
- It gives advice and links only; it cannot place, cancel or refund orders.

To enable it, create a `.env` file in the project root (it is git-ignored):

```
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-3.5-flash
```

Without a key, the bubble still shows but says the assistant is unavailable.

## 5-minute demo script

1. **Customer:** open the login page and click *customer*.
   - Search `black running shoes under 2 million` (text), try the *Voice* tab with `wireless mouse under 500k`, and the *Image* tab with the black-sneaker photo. These reproduce the report's prototype results (§13.1).
   - Add **Biti's Hunter Black Sneakers × 2** to the cart, then *Check out* with vouchers `SALE10, SPORT80`. The quote shows **1,646,000 ₫** (merchandise 1,798,000 − discount 180,000 + shipping 28,000), as in the report.
   - *Place order*, then on the simulated provider page click *Approve (send duplicate callback)*. The duplicate is processed only once.
2. **Seller** (*seller* button = SportZone): Seller Center → the order → *Accept* → *Packed — create label* → *Hand over to carrier* → *Advance tracking* until delivered.
3. **Customer:** open the order and *Review* the item, then *Request return / refund* (refund only).
4. **Seller:** Returns → the case → *Accept*. The refund is issued, the order becomes *Refunded*, and Settlement shows the held entries and the refund reversal.
5. **Admin:** Operations dashboard (§4.5 metrics), *Govern users & content* (approve or reject the pending "Replica Running Shoes" listing), *Platform policy* (fast-forward the clock 8 days, then *Run settlement release*), *Audit log*.
6. **Support:** the dispute queue. To create one, have a seller reject a return and the customer escalate it, then record a reason-coded decision. Search for `alice` (personal data is masked; *Reveal* requires an audited justification).
7. **Risk:** the seeded high-value checkout (Sony headphones × 4 > 20,000,000 ₫) is held. *Release* it, and the customer can then pay from the order page.

## Architecture (Figure 2 → code)

| Component (Figure 2) | Module | Owns |
|---|---|---|
| Customer Application / Seller Center / Administration Portal | `marketplacex/templates/{customer,seller,admin,support,risk}` + each module's `routes.py` | Presentation only; routes call their module's service |
| API Gateway | Flask app + blueprints (`marketplacex/app.py`), `auth.require_role` | Authentication, authorization, error contract with correlation id |
| Identity and Access Service | `modules/identity` | User, Address, password reset |
| Catalog Service | `modules/catalog` | Category, Product, Variant, Offer |
| Seller Service | `modules/seller` | Shop, verification, fulfilment commands |
| Search Service | `modules/search` | Query object, ranking (§10.2), SearchTrace, recommendations |
| Cart Service / Cart Cache | `modules/cart` | Versioned Cart, CartItem, SavedItem, RecentSearch |
| Promotion Service | `modules/promotion` | Campaign, Voucher, Redemption |
| Checkout (saga) | `modules/checkout` | CheckoutGroup, quote hash, compensation |
| Order Service | `modules/order` | Order, OrderItem, OrderStatusHistory, state machine |
| Inventory Service | `modules/inventory` | StockLedger, Reservation |
| Payment Service / Transaction Ledger | `modules/payment`, `adapters/payment_provider.py` | PaymentAttempt, Refund, ProviderCallback |
| Logistics Service | `modules/logistics`, `adapters/logistics_provider.py` | Shipment, TrackingEvent |
| Review Service | `modules/review` | Review |
| Return and Refund Service | `modules/returns` | ReturnCase, Evidence, DisputeDecision |
| Support Service | `modules/support` | SupportCase, CaseNote |
| Risk and Fraud Service | `modules/risk` | RiskAlert |
| Chat Service | `modules/chat` | Conversation, ChatMessage |
| Notification Service | `modules/notification`, `adapters/notification_provider.py` | Notification |
| Settlement Service | `modules/settlement` | LedgerEntry (double entry) |
| Reporting | `modules/reporting` | Read-only metrics |
| Event broker | `marketplacex/events.py` | EventLog, ProcessedEvent (idempotent consumers) |
| Audit | `modules/audit` | Append-only AuditEvent |

## Traceability

### Use cases (Figure 1)

| Use case | Actor | Where | Test |
|---|---|---|---|
| Manage Account | Customer | `/register`, `/login`, `/forgot`, `/account` | tests/test_foundation.py::test_register_and_login |
| Discover Product | Customer | `/`, `/category/<id>`, `/shops/<id>`, `/products/<id>`, `/campaigns/<id>` | tests/test_catalog_inventory.py::test_home_category_and_shop_pages |
| Search by Text | Customer | `/search?mode=text` | tests/test_search.py::test_prototype_top_results |
| Search by Voice | Customer | `/search?mode=voice` (Web Speech API or typed transcript) | tests/test_search.py::test_query_object_common_across_modes |
| Search by Image | Customer | `/search?mode=image` (sample photos; unknown photo → degraded) | tests/test_search.py::test_unknown_image_falls_back_to_text_degraded |
| Manage Cart | Customer | `/cart` | tests/test_cart.py::test_cart_groups_by_shop_and_versions |
| Checkout | Customer | `/checkout` → quote → place | tests/test_checkout.py::test_quote_matches_report |
| Validate Cart | (included in Checkout) | `checkout.service._build` | tests/test_checkout.py::test_unavailable_item_excluded |
| Apply Promotion | (included in Checkout) | `promotion.service.evaluate/reserve` | tests/test_promotion.py::test_report_example_discount |
| Reserve Stock | (included in Checkout) | `inventory.service.reserve` | tests/test_checkout.py::test_place_is_idempotent |
| Authorize Payment | (included in Checkout) | `payment.service.authorize`, `/payments/<id>/pay` | tests/test_checkout.py::test_success_callback_confirms_and_commits |
| Create Order | (included in Checkout) | `order.service.create_orders` | tests/test_checkout.py::test_two_shops_two_orders_one_group |
| Deliver Notification | Notification Provider | `/notifications`, event subscribers | tests/test_tracking_cancel.py::test_confirmation_notifies_customer_and_seller |
| Track Order | Customer | `/orders`, `/orders/<id>` | tests/test_tracking_cancel.py::test_timeline_renders |
| Review Purchase | Customer | `/orders/<id>/items/<item>/review` | tests/test_review.py::test_review_form_route |
| Request Return or Refund | Customer | `/orders/<id>/return`, `/returns/<id>` | tests/test_returns.py::test_refund_only_accept |
| Escalate Dispute | (extends Return) | `/returns/<id>/escalate` | tests/test_returns.py::test_reject_escalate_decide |
| Chat with Seller | Customer | `/chat` | tests/test_chat.py::test_customer_seller_chat |
| Manage Shop | Seller | `/seller/shop` | tests/test_seller_catalog.py::test_shop_profile_and_verification |
| Manage Listing | Seller | `/seller/products` | tests/test_seller_catalog.py::test_submit_goes_pending |
| Manage Inventory and Price | Seller | `/seller/inventory` | tests/test_seller_catalog.py::test_update_offer_and_stale |
| Fulfil Order | Seller | `/seller/orders/<id>` | tests/test_fulfilment.py::test_fulfil_to_delivered |
| Create and Track Shipment | Logistics Provider | labels, carrier simulator `/logistics/shipments/<id>/advance` | tests/test_fulfilment.py::test_delivery_failure_and_reattempt |
| Handle Return | Seller | `/seller/returns/<id>` | tests/test_returns.py::test_return_shipment_inspection |
| View Settlement | Seller | `/seller/settlement` | tests/test_settlement.py::test_release_after_window |
| Chat with Customer | Seller | `/chat` | tests/test_chat.py::test_chat_routes |
| Manage Taxonomy | Administrator | `/admin/categories` | tests/test_admin.py::test_taxonomy_and_campaign |
| Manage Campaign | Administrator | `/admin/campaigns` | tests/test_admin.py::test_taxonomy_and_campaign |
| Configure Platform Policy | Administrator | `/admin/policy` | tests/test_admin.py::test_policy_and_clock |
| Govern Users and Content | Administrator | `/admin/moderation`, `/admin/users` | tests/test_admin.py::test_moderation_requires_reason |
| View Operational Report | Administrator | `/admin/` | tests/test_admin.py::test_reports_shape |
| Manage Support Case | Support Agent | `/support/`, `/support/cases/<id>` | tests/test_support.py::test_case_lifecycle_and_timeline |
| Assist Dispute | Support Agent | `/support/disputes/<id>` | tests/test_support.py::test_dispute_decision_via_console |
| Review Risk Alert | Risk Analyst | `/risk/` | tests/test_risk.py::test_risk_pages |
| Hold or Release Transaction | Risk Analyst | `/risk/alerts/<id>` | tests/test_risk.py::test_high_value_checkout_held_then_released |
| Process Payment | Payment Provider | `/payments/callback` (HMAC-signed) | tests/test_payment.py::test_callback_endpoint |

### Functional requirements

| FR | Requirement | Module | Test |
|---|---|---|---|
| FR01 | Register, sign in, recover account | identity | tests/test_foundation.py::test_password_recovery |
| FR02 | Browse categories, campaigns, shops | catalog, promotion | tests/test_promotion.py::test_campaign_page |
| FR03 | Text / voice / image search | search | tests/test_search.py::test_prototype_top_results |
| FR04 | Filters and facets | search | tests/test_search.py::test_filters_and_facets |
| FR05 | Sorts with deterministic ties | search | tests/test_search.py::test_sort_price_deterministic |
| FR06 | Product commercial fields | catalog | tests/test_catalog_inventory.py::test_product_page_shows_commercial_fields |
| FR07 | Cart grouped by shop, versioned | cart | tests/test_cart.py::test_stale_version_rejected |
| FR08 | Saved products/shops, recent searches | cart | tests/test_cart.py::test_saved_and_recent |
| FR09 | Recommendations with explanation | search | tests/test_search.py::test_recommend_popular_without_customer |
| FR10 | Server revalidates price, stock, vouchers | checkout | tests/test_checkout.py::test_price_change_detected |
| FR11 | Split into shop orders under one group | checkout, order | tests/test_checkout.py::test_two_shops_two_orders_one_group |
| FR12 | Idempotent stock reservation | inventory, checkout | tests/test_checkout.py::test_place_is_idempotent |
| FR13 | Payment with signed async callbacks | payment | tests/test_payment.py::test_duplicate_callback_single_capture |
| FR14 | Shipment, label, pickup | logistics, seller | tests/test_fulfilment.py::test_fulfil_to_delivered |
| FR15 | Tracking with actor, time, reason | order | tests/test_order_state.py::test_transition_writes_history_audit_event |
| FR16 | Cancellation with compensation | order | tests/test_tracking_cancel.py::test_cancel_confirmed_refunds_and_restocks |
| FR17 | Return/refund with evidence and deadline | returns | tests/test_returns.py::test_eligibility_reasons |
| FR18 | Escalation, immutable decision | returns, support | tests/test_returns.py::test_reject_escalate_decide |
| FR19 | Verified review and seller reply | review | tests/test_review.py::test_seller_reply_and_product_page |
| FR20 | Notifications with delivery result | notification | tests/test_tracking_cancel.py::test_notification_inbox_and_read |
| FR21 | Shop profile and verification | seller, admin | tests/test_admin.py::test_verify_shop |
| FR22 | Listing with variants, moderated | catalog | tests/test_seller_catalog.py::test_listing_validation_messages |
| FR23 | Price, stock, purchase limits | seller | tests/test_cart.py::test_purchase_limit |
| FR24 | Accept, pack, hand over, reject | seller | tests/test_fulfilment.py::test_cannot_hand_over_cancelled |
| FR25 | Settlement statement | settlement | tests/test_settlement.py::test_refund_posts_reversal |
| FR26 | Taxonomy, campaigns, platform vouchers | admin | tests/test_admin.py::test_taxonomy_and_campaign |
| FR27 | Moderation with evidence and reasons | admin, review | tests/test_admin.py::test_bulk_moderation_preview_and_job |
| FR28 | Support search with masked data | support | tests/test_support.py::test_customer_page_masks |
| FR29 | Risk evaluation and holds | risk | tests/test_risk.py::test_refund_velocity_holds |
| FR30 | Partner signed, idempotent callbacks | payment | tests/test_payment.py::test_callback_signature_verified |

### Business rules

| BR | Rule | Enforcement | Test |
|---|---|---|---|
| BR01 | Offer = one shop + one variant | `Offer` unique (shop_id, variant_id) | tests/test_catalog_inventory.py::test_offer_unique_per_shop_variant |
| BR02 | Payable = merchandise − discounts + shipping | `checkout.service._build` (server only) | tests/test_checkout.py::test_quote_matches_report |
| BR03 | Reserve before capture, release on timeout/cancel | `inventory.reserve/release`, `checkout.sweep` | tests/test_checkout.py::test_expired_reservation_cancels |
| BR04 | Unique voucher redemption key | `Redemption` unique constraint, `promotion.reserve` | tests/test_promotion.py::test_redemption_unique_per_attempt |
| BR05 | Approved, audited state machine | `order.state_machine`, `order.service.transition` | tests/test_order_state.py::test_illegal_raises |
| BR06 | Review needs delivery, one per item | `review.service.create_review` + unique constraint | tests/test_review.py::test_review_requires_delivery |
| BR07 | Refund ≤ captured − prior refunds | `payment.service.refund` | tests/test_payment.py::test_refund_bound |
| BR08 | Settlement held until window closes | `settlement` held → released on Completed | tests/test_settlement.py::test_open_return_blocks_release |

### Other report sections

| Report section | Where | Test |
|---|---|---|
| §4.3 checkout invariants (compensation) | `checkout.service.compensate` | tests/test_checkout.py::test_payment_fail_compensates |
| §4.2 empty / degraded results | `search.service._relax_hints` | tests/test_search.py::test_empty_results_give_relax_hints |
| §7.3 idempotent consumers | `events.py` ProcessedEvent | tests/test_foundation.py::test_event_consumer_runs_once_on_redelivery |
| §8.5 audit evidence | `audit.service.record` | tests/test_foundation.py::test_audit_record_has_digest |
| §9.5 guards | `order.state_machine.GUARDS` | tests/test_order_state.py::test_return_window_guard |
| §12.5 double-entry ledger | `settlement.service` | tests/test_settlement.py::test_delivery_posts_balanced_held_entries |
| §14 end-to-end journey | full stack | tests/test_e2e.py::test_full_customer_journey |

## Designed, not built (report scope this demo simulates or omits)

- Real MFA and trusted-device management (FR01's device part).
- Real payment, carrier, email/SMS providers: fake adapters only. Payment authorizes and captures in one step.
- Separate microservices, a real event broker, CDN/WAF, multi-zone deployment (the deployment diagram).
- Flash-sale waiting room and performance/SLO verification (§5, §12.4).
- Real voice/image ML: the browser's speech API or a typed transcript, and 3-dimension sample image vectors, as in the report's prototype.
- Multi-currency and multi-market; full country-specific address validation.
- Full WCAG 2.2 audit (the UI uses semantic HTML, labels and visible focus).
- Customer data export/deletion orchestration and legal holds (§11.1).
