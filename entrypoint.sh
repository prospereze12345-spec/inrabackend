#!/bin/bash
set -e
python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py seed_plans
exec gunicorn config.wsgi:application --bind 0.0.0.0:10000