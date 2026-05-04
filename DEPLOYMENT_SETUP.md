# HIT Canteen Deployment Setup

This project is now prepared for:

- **Aiven** for PostgreSQL
- **Render** for Django hosting
- **Vercel** for an optional split frontend

## Recommended deployment order

1. Create the **Aiven PostgreSQL** database
2. Deploy the **Django app to Render**
3. Confirm the app works on Render end to end
4. Only then move the frontend to **Vercel** if needed

## 1. Aiven

Create a PostgreSQL database in Aiven and copy the connection values:

- host
- port
- database name
- username
- password

Build the `DATABASE_URL` like this:

```env
DATABASE_URL=postgresql://USERNAME:PASSWORD@HOST:PORT/DATABASE?sslmode=require
```

## 2. Render

Use the existing project files:

- `build.sh`
- `render.yaml`

### Render build command

```bash
./build.sh
```

### Render start command

```bash
python -m gunicorn config.wsgi:application --chdir backend
```

### Render environment values

Copy values from:

- `.env.render.example`

Important values to replace:

- `DATABASE_URL`
- `DJANGO_SECRET_KEY`
- `HIT_TICKET_SECRET`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `DEFAULT_FROM_EMAIL`
- `WORK_NOTIFICATION_EMAIL`
- `YOUR-RENDER-SERVICE`

### Required Paynow values on Render

```env
PAYNOW_INTEGRATION_ID=23824
PAYNOW_INTEGRATION_KEY=52ed5a83-8b9c-4f10-bbd0-8c4e1c5fccec
PAYNOW_RESULT_URL=https://YOUR-RENDER-SERVICE.onrender.com/api/v1/payments/paynow/result
PAYNOW_RETURN_URL=https://YOUR-RENDER-SERVICE.onrender.com/student/
```

Make sure:

- the URLs use `https`
- there are no quotes
- there are no trailing spaces

## 3. Restart and verify Render

After setting environment variables:

1. Trigger a new deploy on Render
2. Wait for:
   - migrations
   - collectstatic
   - gunicorn startup
3. Open the Render URL in a browser

## 4. Optional Vercel frontend

Only do this if you want the frontend hosted separately from Django.

Use:

- `.env.vercel.example`

Set:

```env
HIT_API_BASE_URL=https://YOUR-RENDER-SERVICE.onrender.com
```

Then deploy the frontend to Vercel.

If you split the frontend, also set Django CORS/CSRF values on Render:

```env
CORS_ALLOWED_ORIGINS=https://YOUR-FRONTEND.vercel.app
CSRF_TRUSTED_ORIGINS_EXTRA=https://YOUR-FRONTEND.vercel.app,https://YOUR-RENDER-SERVICE.onrender.com
```

## 5. Final retest checklist

After deployment, verify:

1. Login works
2. Student dashboard loads
3. Meal menu loads
4. Staff dashboard loads
5. Admin dashboard loads
6. Static files render correctly
7. Paynow top-up starts correctly
8. Paynow callback updates the student wallet

## 6. Local fallback

For local development, keep using:

- `.env.example`
- SQLite
- local Django server
