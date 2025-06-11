from pathlib import Path
import os
from dotenv import load_dotenv
import dj_database_url  # 👉 Asegurate de tenerlo en requirements.txt

# ⚠️ Cargar el archivo .env antes de usar cualquier os.environ
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# SECRET_KEY para producción desde variable de entorno (o valor por defecto si no está)
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-+*^tqw7091lf!2qengz$$auv-l!=8-7ua1d7vuc3s%f5gga*!v')

# DEBUG desde variable de entorno (por defecto True para desarrollo)
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

# ALLOWED_HOSTS desde entorno o valores seguros por defecto
ALLOWED_HOSTS = os.environ.get(
    'ALLOWED_HOSTS',
    'proyectocomunicaciones-production.up.railway.app,localhost,127.0.0.1'
).split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'calificaciones',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Para servir archivos estáticos
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'boletin.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'boletin.wsgi.application'

# Base de datos PostgreSQL desde Railway
DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('DATABASE_URL'),
        conn_max_age=600,
        ssl_require=True
    )
}

# Verificación de configuración para entorno local
if 'ENGINE' not in DATABASES['default']:
    raise Exception(
        "La variable de entorno DATABASE_URL no está definida o es inválida.\n"
        "Exportala en tu entorno local o cargala desde un archivo .env antes de correr el servidor.\n\n"
        "Windows (cmd):   set DATABASE_URL=postgres://usuario:contraseña@host:puerto/dbname\n"
        "Git Bash / Linux: export DATABASE_URL=postgres://usuario:contraseña@host:puerto/dbname"
    )

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Archivos estáticos
STATIC_URL = '/static/'
STATIC_ROOT = str(BASE_DIR / "staticfiles")

# Usar Whitenoise para producción (sirve archivos estáticos desde STATIC_ROOT)
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_REDIRECT_URL = '/mi_panel/'
LOGOUT_REDIRECT_URL = '/accounts/login/'
LOGIN_URL = '/accounts/login/'

# Para evitar errores CSRF en producción
CSRF_TRUSTED_ORIGINS = ['https://proyectocomunicaciones-production.up.railway.app']
