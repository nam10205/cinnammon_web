# MarketplaceX

A small Flask shop that showcases an 8-table entity-relationship design. Customers browse a catalogue of real Tiki.vn products, search by text, voice or image, check out with a simulated card or cash on delivery, and follow their orders. A seller and an admin view sit on top of the same tables. A Gemini shopping assistant answers questions about products and the customer's own orders.

## Run it

Requires Python 3.9+.

1. Install the requirements:

   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

2. Point `DATABASE_URL` at the database, as an environment variable or a line in `.env` (git-ignored).
   - Supabase Postgres, through the session pooler (port 5432). `<project-ref>` is `vmzbgxyibhhvoucpugwd`; `<password>` is the database password from the Supabase dashboard.

     ```
     DATABASE_URL=postgresql+psycopg2://postgres.<project-ref>:<password>@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres?sslmode=require
     ```

   - Without `DATABASE_URL`, the app uses a local SQLite file, `instance/marketplacex.db`.

3. Create the schema and seed it. Seeding a remote database takes a few minutes. `--reset` drops every table in the database, including leftovers of older schemas, and wipes all data.

   ```bash
   .venv/bin/flask --app marketplacex.app init-db --reset
   ```

   - Without `--reset`, `init-db` refuses to touch a database that already has customers.
   - On Postgres it also enables row level security on every table. The app connects as the table owner, so RLS only closes Supabase's public API.

4. Run the app and the tests:

   ```bash
   .venv/bin/flask --app marketplacex.app run       # http://127.0.0.1:5000
   .venv/bin/python -m pytest -q                    # full test suite, on in-memory SQLite
   .venv/bin/python -m pytest -q -m supabase        # live checks of the Supabase schema, seed and RLS
   ```

Optional: for the shopping assistant, add `GEMINI_API_KEY=your-key` (and `GEMINI_MODEL=gemini-3.5-flash`) to `.env`. Without a key the chat bubble says the assistant is unavailable.

## Demo logins

The login page has three one-click buttons: **customer** (alice@demo), **seller** and **admin**.
- Any seeded customer can sign in by email alone, for example `binh@demo`. The others are chi, dung, giang, hoa, khanh, linh, minh and nam, all `@demo`.
- New customers can sign up with a name, email, phone and address.

## Database

Eight tables, created by `db.create_all()` and seeded from `marketplacex/data/tiki_catalog.json`.

| Table | Holds |
|---|---|
| `FullName` | First, middle and last name of a customer |
| `Address` | Ward, street and a detail line (house number, district, city) |
| `Customer` | Email and phone, linked to one `FullName` and one `Address` |
| `SearchHistory` | A customer's past searches: keyword, type (`text`, `voice`, `image`) and time |
| `Category` | The 8 Tiki categories |
| `Product` | Name, brand, description, price in VND, stock, average rating and timestamps |
| `ProductImage` | Up to three photo URLs per product, with an image feature vector for image search |
| `Order` | One product per order: quantity, prices, shipping fee, payment method and status, and shipping timestamps |

The seed loads 8 categories with 65 products each, 10 demo customers, 30 searches and 20 orders.

## Simulations

- **Card payment:** use `4242 4242 4242 4242`. Any other number is declined.
- **Cash on delivery:** the order is placed unpaid and marked paid on delivery.
- **Shipping:** an order moves placed, processing, shipped, delivered, one step every 20 seconds.
- **Seller skip:** the seller can skip an order straight to its next step instead of waiting.
- **Shipping fee:** 30,000 VND, free from 500,000 VND.
