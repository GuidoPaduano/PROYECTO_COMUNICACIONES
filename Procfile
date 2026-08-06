web: python manage.py migrate && gunicorn -w 3 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000} boletin.asgi:application
worker: celery -A boletin worker --loglevel=info
