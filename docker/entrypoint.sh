#!/usr/bin/env sh
set -e

python backend/manage.py migrate --noinput
python backend/manage.py collectstatic --noinput
exec gunicorn config.wsgi:application --chdir backend --bind 0.0.0.0:8000 --workers 3 --timeout 120
