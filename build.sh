#!/usr/bin/env bash
set -o errexit

pip install --root-user-action=ignore -r requirements.txt
python backend/manage.py collectstatic --noinput
python backend/manage.py migrate
