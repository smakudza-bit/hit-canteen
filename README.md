# HIT Canteen Digital Payment and Management System (Django)

This implementation now uses a modern Django backend (not FastAPI), with DRF + JWT auth.

## Stack

- Django 5.2
- Django REST Framework
- SimpleJWT
- PostgreSQL (production) / SQLite (local)
- Gunicorn + Nginx (HTTPS reverse proxy)
- Docker Compose deployment

## Implemented Features

- Student registration using university ID
- JWT login
- Digital wallet with ledger-based balance
- Payment initiation + signed webhook callback processing
- Idempotency-key protection for top-up and order creation
- One-time signed QR meal ticket generation and redemption
- Queue slot capacity + estimated wait time
- Admin KPIs, fraud alerts, and demand forecasting
- Audit trail events for critical operations

## API Endpoints

- `POST /api/v1/auth/register-student`
- `POST /api/v1/auth/login`
- `GET /api/v1/wallet`
- `GET /api/v1/wallet/ledger`
- `POST /api/v1/wallet/topup/initiate` (requires `Idempotency-Key`)
- `POST /api/v1/payments/webhook/{provider}` (requires `X-Signature`)
- `POST /api/v1/payments/dev/simulate-success/{tx_id}`
- `GET /api/v1/menu`
- `GET /api/v1/pickup-slots`
- `POST /api/v1/orders` (requires `Idempotency-Key`)
- `GET /api/v1/orders/{order_id}`
- `GET /api/v1/tickets/{order_id}`
- `POST /api/v1/tickets/validate-scan`
- `GET /api/v1/admin/kpis`
- `GET /api/v1/admin/reports/revenue`
- `GET /api/v1/admin/reports/fraud-alerts`
- `GET /api/v1/admin/reports/demand-forecast`

## Local Run (VS Code)

1. Copy `.env.example` to `.env`.
2. Run VS Code tasks:
   - `Create venv`
   - `Install deps`
   - `Run migrations`
   - `Run Django`
3. Open `http://127.0.0.1:8000/`.

Demo logins:

- Staff: `staff@hit.ac.zw` / `Staff123!`
- Admin: `admin@hit.ac.zw` / `Admin123!`

## Docker (Production-style)

1. Copy `.env.example` to `.env` and set strong secrets.
2. Put TLS certs in `docker/nginx/certs/`:
   - `fullchain.pem`
   - `privkey.pem`
3. Run:

```powershell
docker compose up --build -d
```

The app runs migrations and `collectstatic` on startup, then serves through Gunicorn behind Nginx TLS.

## Webhook Signature

For `/api/v1/payments/webhook/{provider}`:

- Header: `X-Signature`
- Value: `HMAC_SHA256(raw_body, provider_secret)`
- Secrets from env:
  - `WEBHOOK_SECRET_MOBILE_MONEY`
  - `WEBHOOK_SECRET_BANK_CARD`
  - `WEBHOOK_SECRET_ONLINE_PAYMENT`

## Notes

- `POST /api/v1/payments/dev/simulate-success/{tx_id}` is for development testing and should be disabled in strict production.

## Test Suite

Run the Django tests:

`powershell
python backend/manage.py test canteen
`

Coverage includes:

- Top-up idempotency
- Order idempotency
- Webhook signature verification
- Webhook replay safety (no double credit)
- One-time ticket redemption (duplicate scan blocked)
- Admin-role access enforcement on KPI endpoint

## Admin Dashboards and Filters

Django Admin (/django-admin/) now includes role-aware finance/fraud operations:

- Finance dashboard: /django-admin/canteen/paymenttransaction/finance-dashboard/ (admin only)
- Fraud dashboard: /django-admin/canteen/fraudalert/fraud-dashboard/ (staff/admin)

Enhanced admin list filters/search are provided for:

- PaymentTransaction
- WalletLedgerEntry
- Order
- FraudAlert
- AuditLog

