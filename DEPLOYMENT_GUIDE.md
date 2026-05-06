# PythonAnywhere Deployment Guide

This guide prepares the HIT Canteen / PaySafe project for a simple school-demo deployment on PythonAnywhere while keeping local development unchanged.

## Project layout

- Django backend root: `backend`
- `manage.py`: `backend/manage.py`
- Django settings module: `config.settings`
- Development database: SQLite
- Email: Gmail SMTP
- Online payments: Paynow

## 1. Push the project to GitHub

From your local machine:

```powershell
cd "C:\Users\kneet\OneDrive\Desktop\Hit 200 dox\project"
git add .
git commit -m "Prepare project for PythonAnywhere deployment"
git push
```

## 2. Clone the project on PythonAnywhere

Open a PythonAnywhere Bash console and run:

```bash
cd /home/seantrigger
git clone https://github.com/yourusername/your-repo.git
cd project
```

## 3. Create a virtual environment

Use a Python version supported by your PythonAnywhere account:

```bash
mkvirtualenv --python=/usr/bin/python3.10 hitcanteen-venv
workon hitcanteen-venv
```

If `mkvirtualenv` is not available, use:

```bash
python3.10 -m venv ~/.virtualenvs/hitcanteen-venv
source ~/.virtualenvs/hitcanteen-venv/bin/activate
```

## 4. Install requirements

```bash
cd /home/seantrigger/project
pip install --upgrade pip
pip install -r requirements.txt
```

## 5. Create the `.env` file

Copy the example file:

```bash
cd /home/seantrigger/project
cp .env.example .env
nano .env
```

Put in your real values:

```env
DEBUG=False
DJANGO_SECRET_KEY=change-this-secret-key
HIT_TICKET_SECRET=change-this-ticket-secret

DATABASE_URL=sqlite:///hit_canteen.db
TIME_ZONE=Africa/Harare
ACCESS_TOKEN_MINUTES=60

PYTHONANYWHERE_DOMAIN=seantrigger.pythonanywhere.com
EXTRA_ALLOWED_HOSTS=seantrigger.pythonanywhere.com,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS_EXTRA=https://seantrigger.pythonanywhere.com
STATIC_URL=/static/
STATIC_ROOT=/home/seantrigger/project/staticfiles
SECURE_SSL_REDIRECT=True

EMAIL_NOTIFICATIONS_ENABLED=True
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=yourgmail@gmail.com
EMAIL_HOST_PASSWORD=your-gmail-app-password
DEFAULT_FROM_EMAIL=yourgmail@gmail.com
WORK_NOTIFICATION_EMAIL=yourgmail@gmail.com

PAYNOW_INTEGRATION_ID=23824
PAYNOW_INTEGRATION_KEY=your-paynow-integration-key
PAYNOW_RESULT_URL=https://seantrigger.pythonanywhere.com/api/v1/payments/paynow/result
PAYNOW_RETURN_URL=https://seantrigger.pythonanywhere.com/student/
PAYNOW_INITIATE_URL=https://www.paynow.co.zw/interface/initiatetransaction
PAYNOW_INCLUDE_AUTH_EMAIL=False

WEBHOOK_SECRET_MOBILE_MONEY=change-mobile-money-webhook-secret
WEBHOOK_SECRET_BANK_CARD=change-bank-card-webhook-secret
WEBHOOK_SECRET_ONLINE_PAYMENT=change-online-payment-webhook-secret
```

Important:

- `EMAIL_HOST_PASSWORD` must be a Gmail App Password, not your normal Gmail password
- `PAYNOW_RESULT_URL` must use your live PythonAnywhere HTTPS domain
- `PAYNOW_RETURN_URL` should point back to `/student/`
- `PAYNOW_INCLUDE_AUTH_EMAIL=False` is recommended for the current Paynow test-mode flow

## 6. Run migrations

```bash
cd /home/seantrigger/project
workon hitcanteen-venv
python backend/manage.py migrate
```

## 7. Create a superuser

```bash
python backend/manage.py createsuperuser
```

## 8. Run collectstatic

```bash
python backend/manage.py collectstatic --noinput
```

## 9. Configure the Web app on PythonAnywhere

In the PythonAnywhere dashboard:

1. Open the **Web** tab
2. Create a new web app
3. Choose **Manual configuration**
4. Choose the same Python version you used for the virtual environment
5. Set the virtualenv path to:

```text
/home/seantrigger/.virtualenvs/hitcanteen-venv
```

## 10. Configure the WSGI file

Open the PythonAnywhere WSGI file and replace its contents with:

```python
import os
import sys

path = "/home/seantrigger/project/backend"
if path not in sys.path:
    sys.path.append(path)

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

Replace:

- `yourusername`
- `YOUR-REPO`

## 11. Configure static files

In the **Static files** section on PythonAnywhere, add:

- URL:

```text
/static/
```

- Directory:

```text
/home/seantrigger/project/staticfiles
```

## 12. Reload the web app

Click **Reload** in the PythonAnywhere Web tab.

## 13. Test the system

Test these in order:

1. Open `https://seantrigger.pythonanywhere.com/`
2. Register a student account
3. Confirm email verification link is received
4. Log in as student
5. Check wallet page
6. Add a wallet top-up through Paynow
7. Place a meal order
8. Confirm QR ticket is generated
9. Log in as staff and test QR scanning
10. Log in as admin and open admin pages

## 14. How to test email

### Quick test from PythonAnywhere console

```bash
cd /home/seantrigger/project
workon hitcanteen-venv
python backend/manage.py shell
```

Then:

```python
from canteen.utils import send_notification_email
result = send_notification_email(
    "your-hit-email@hit.ac.zw",
    "HIT Canteen Email Test",
    "This is a deployment test email.",
    category="smtp_test"
)
print(result.status, result.error_message)
```

Expected:

- `sent` means SMTP is working
- `failed` means check Gmail app password or SMTP config

## 15. How to test Paynow callback

### Top-up test

1. Start a wallet top-up from the student portal
2. Complete the Paynow confirmation flow
3. Return to the student portal
4. Confirm:
   - wallet balance changes
   - transaction history updates

### Order-payment test

1. Add a meal to cart
2. Choose `Pay with Mobile Money` or `Pay with Bank/Card`
3. Complete Paynow confirmation
4. Return to the student portal
5. Confirm:
   - order status becomes paid
   - QR ticket appears

### If callback seems delayed

The app also supports verified Paynow polling for pending transactions. If the callback is delayed, refresh the student page or transaction history and confirm the transaction updates there.

## 16. Common errors and fixes

### DisallowedHost

Problem:

```text
Invalid HTTP_HOST header
```

Fix:

- confirm `.env` contains:

```env
PYTHONANYWHERE_DOMAIN=seantrigger.pythonanywhere.com
EXTRA_ALLOWED_HOSTS=seantrigger.pythonanywhere.com,localhost,127.0.0.1
```

- reload the web app

### CSRF verification failed

Fix:

- confirm:

```env
CSRF_TRUSTED_ORIGINS_EXTRA=https://seantrigger.pythonanywhere.com
```

- reload the web app

### Static files not loading

Fix:

1. run:

```bash
python backend/manage.py collectstatic --noinput
```

2. confirm the PythonAnywhere static mapping:

```text
/static/ -> /home/seantrigger/project/staticfiles
```

3. reload the web app

### Gmail authentication failed

Problem examples:

```text
535 5.7.8 Username and Password not accepted
```

Fix:

1. enable 2-Step Verification on the Gmail account
2. create a Gmail App Password
3. set:

```env
EMAIL_HOST_USER=yourgmail@gmail.com
EMAIL_HOST_PASSWORD=your-gmail-app-password
```

4. reload the web app

### Paynow callback not updating payment status

Check:

1. `PAYNOW_RESULT_URL` is exactly your live HTTPS PythonAnywhere callback URL
2. `PAYNOW_RETURN_URL` points to the live student page
3. Paynow can reach your PythonAnywhere web app from the internet
4. the transaction remains `pending` only until callback or verified polling settles it

Example:

```env
PAYNOW_RESULT_URL=https://seantrigger.pythonanywhere.com/api/v1/payments/paynow/result
PAYNOW_RETURN_URL=https://seantrigger.pythonanywhere.com/student/
```

### Email verification link opens but login still blocked

Check:

1. the verification URL matches the live domain
2. the student record is marked verified
3. the account is not suspended

## 17. Useful admin commands

Run system checks:

```bash
python backend/manage.py check
```

Open a Django shell:

```bash
python backend/manage.py shell
```

Create demo data by visiting the app or by running:

```bash
python backend/manage.py shell -c "from canteen.views import _ensure_seed_data; _ensure_seed_data()"
```

## 18. Final reminder

Do not commit your real `.env` file to GitHub.

Commit:

- `.env.example`
- code changes
- this deployment guide

Do not commit:

- real Gmail app password
- Paynow integration key
- Django secret key
- live `.env`
