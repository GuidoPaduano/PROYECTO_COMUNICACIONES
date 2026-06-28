web: python manage.py migrate && daphne -b 0.0.0.0 -p ${PORT:-8000} boletin.asgi:application
worker: celery -A boletin worker --loglevel=info
