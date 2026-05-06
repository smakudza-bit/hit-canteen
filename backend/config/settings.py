import os
from pathlib import Path
from datetime import timedelta
from decouple import config

try:
    import dj_database_url
except ImportError:
    dj_database_url = None

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent


def clean_env(name, default=''):
    value = config(name, default=default)
    if isinstance(value, str):
        return value.strip().strip('"').strip("'")
    return value


def split_env_list(name, default=''):
    value = clean_env(name, default=default)
    if not value:
        return []
    return [item.strip() for item in str(value).split(',') if item.strip()]


SECRET_KEY = config('DJANGO_SECRET_KEY', default='change-this-secret')
DEBUG = config('DEBUG', default=True, cast=bool)
PYTHONANYWHERE_DOMAIN = clean_env('PYTHONANYWHERE_DOMAIN', default='')

ALLOWED_HOSTS = [
    '127.0.0.1',
    'localhost',
    '.ngrok-free.dev',
    '.ngrok-free.app',
    '.onrender.com',
]
render_external_hostname = clean_env('RENDER_EXTERNAL_HOSTNAME', default='')
if render_external_hostname:
    ALLOWED_HOSTS.append(render_external_hostname)
if PYTHONANYWHERE_DOMAIN:
    ALLOWED_HOSTS.append(PYTHONANYWHERE_DOMAIN)
    if not PYTHONANYWHERE_DOMAIN.startswith('.'):
        ALLOWED_HOSTS.append(f'.{PYTHONANYWHERE_DOMAIN}')
ALLOWED_HOSTS += split_env_list('EXTRA_ALLOWED_HOSTS')
ALLOWED_HOSTS = list(dict.fromkeys(ALLOWED_HOSTS))

CSRF_TRUSTED_ORIGINS = [
    'https://.ngrok-free.dev',
    'https://.ngrok-free.app',
]
if render_external_hostname:
    CSRF_TRUSTED_ORIGINS.append(f'https://{render_external_hostname}')
if PYTHONANYWHERE_DOMAIN:
    CSRF_TRUSTED_ORIGINS.append(f'https://{PYTHONANYWHERE_DOMAIN}')
CSRF_TRUSTED_ORIGINS += split_env_list('CSRF_TRUSTED_ORIGINS_EXTRA')
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(CSRF_TRUSTED_ORIGINS))

CORS_ALLOWED_ORIGINS = split_env_list('CORS_ALLOWED_ORIGINS')
CORS_ALLOW_CREDENTIALS = config('CORS_ALLOW_CREDENTIALS', default=True, cast=bool)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'canteen',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [PROJECT_ROOT / 'web'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DATABASE_URL = config('DATABASE_URL', default='sqlite:///hit_canteen.db')
if DATABASE_URL.startswith('sqlite:///'):
    sqlite_path = DATABASE_URL.replace('sqlite:///', '')
    if os.path.isabs(sqlite_path):
        db_name = sqlite_path
    else:
        db_name = str(PROJECT_ROOT / sqlite_path)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': db_name,
        }
    }
elif (
    DATABASE_URL.startswith('postgres://')
    or DATABASE_URL.startswith('postgresql://')
    or DATABASE_URL.startswith('postgresql+psycopg://')
):
    normalized_database_url = (
        DATABASE_URL
        .replace('postgresql+psycopg://', 'postgresql://')
        .replace('postgres://', 'postgresql://', 1)
    )
    if dj_database_url:
        DATABASES = {
            'default': dj_database_url.parse(
                normalized_database_url,
                conn_max_age=600,
                ssl_require='sslmode=require' in normalized_database_url.lower() or '.aivencloud.com' in normalized_database_url.lower(),
            )
        }
    else:
        import urllib.parse as up
        parsed = up.urlparse(normalized_database_url)
        query_params = dict(up.parse_qsl(parsed.query))
        db_config = {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': parsed.path.lstrip('/'),
            'USER': parsed.username,
            'PASSWORD': parsed.password,
            'HOST': parsed.hostname,
            'PORT': str(parsed.port or 5432),
        }
        sslmode = query_params.get('sslmode')
        if sslmode:
            db_config['OPTIONS'] = {'sslmode': sslmode}
        DATABASES = {'default': db_config}
else:
    raise ValueError('Unsupported DATABASE_URL scheme')

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = config('TIME_ZONE', default='Africa/Harare')
USE_I18N = True
USE_TZ = True

STATIC_URL = clean_env('STATIC_URL', default='/static/')
STATIC_ROOT = Path(clean_env('STATIC_ROOT', default=str(PROJECT_ROOT / 'staticfiles')))
STATICFILES_DIRS = [PROJECT_ROOT / 'web']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'canteen.User'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=config('ACCESS_TOKEN_MINUTES', default=60, cast=int)),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'AUTH_HEADER_TYPES': ('Bearer',),
}

HIT_TICKET_SECRET = clean_env('HIT_TICKET_SECRET', default='change-ticket-secret')
WEBHOOK_SECRET_MOBILE_MONEY = clean_env('WEBHOOK_SECRET_MOBILE_MONEY', default='change-mobile-money-secret')
WEBHOOK_SECRET_BANK_CARD = clean_env('WEBHOOK_SECRET_BANK_CARD', default='change-bank-card-secret')
WEBHOOK_SECRET_ONLINE_PAYMENT = clean_env('WEBHOOK_SECRET_ONLINE_PAYMENT', default='change-online-payment-secret')

PAYNOW_INTEGRATION_ID = clean_env('PAYNOW_INTEGRATION_ID', default='')
PAYNOW_INTEGRATION_KEY = clean_env('PAYNOW_INTEGRATION_KEY', default='')
PAYNOW_RESULT_URL = clean_env('PAYNOW_RESULT_URL', default='')
PAYNOW_RETURN_URL = clean_env('PAYNOW_RETURN_URL', default='')
PAYNOW_INITIATE_URL = clean_env('PAYNOW_INITIATE_URL', default='https://www.paynow.co.zw/interface/initiatetransaction')
PAYNOW_INCLUDE_AUTH_EMAIL = config('PAYNOW_INCLUDE_AUTH_EMAIL', default=True, cast=bool)

EMAIL_NOTIFICATIONS_ENABLED = config('EMAIL_NOTIFICATIONS_ENABLED', default=False, cast=bool)
EMAIL_BACKEND = clean_env('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = clean_env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = clean_env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = clean_env('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
DEFAULT_FROM_EMAIL = clean_env('DEFAULT_FROM_EMAIL', default='no-reply@hitcanteen.local')
WORK_NOTIFICATION_EMAIL = clean_env('WORK_NOTIFICATION_EMAIL', default='')

USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=not DEBUG, cast=bool)
