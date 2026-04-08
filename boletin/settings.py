from pathlib import Path
import os
import secrets
from dotenv import load_dotenv
import dj_database_url  # 👉 Asegurate de tenerlo en requirements.txt
from corsheaders.defaults import default_headers  # ✅ para extender headers permitidos en CORS

# ⚠️ Cargar el archivo .env antes de usar cualquier os.environ
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")
RESEND_API_KEY_EFFECTIVE = RESEND_API_KEY
RESEND_ENABLED = bool(RESEND_API_KEY_EFFECTIVE and RESEND_FROM_EMAIL)


def _split_env_list(var_name: str, default_list: list[str]) -> list[str]:
    raw = os.environ.get(var_name, "").strip()
    if not raw:
        return default_list
    return [p.strip() for p in raw.split(",") if p.strip()]

# SECRET_KEY para producción desde variable de entorno (o valor por defecto si no está)
DEBUG = os.environ.get('DEBUG', 'False') == 'True'
ALLOW_VERCEL_ORIGINS = os.environ.get("ALLOW_VERCEL_ORIGINS", "False") == "True"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "").strip()
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = secrets.token_urlsafe(50)
    else:
        raise Exception("DJANGO_SECRET_KEY no configurado.")

# Frontend (para links de reset de contraseña)
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "").strip()
if not FRONTEND_BASE_URL:
    if DEBUG:
        FRONTEND_BASE_URL = "http://localhost:3000"
    else:
        raise Exception("FRONTEND_BASE_URL no configurado.")
PASSWORD_RESET_PATH = os.environ.get("PASSWORD_RESET_PATH", "/reset-password")
SCHOOL_PARENT_HOSTS = _split_env_list("SCHOOL_PARENT_HOSTS", [])

if not DEBUG and not RESEND_ENABLED:
    raise Exception(
        "RESEND_API_KEY/RESEND_FROM_EMAIL not configured. "
        "Set RESEND_API_KEY and RESEND_FROM_EMAIL."
    )

# ALLOWED_HOSTS desde entorno o valores seguros por defecto
ALLOWED_HOSTS = os.environ.get(
    'ALLOWED_HOSTS',
    'proyectocomunicaciones-production.up.railway.app,localhost,127.0.0.1,0.0.0.0'
).split(',')

# En desarrollo, permitir cualquier Host para evitar errores 400 al acceder por IP LAN
if DEBUG:
    ALLOWED_HOSTS = list({*ALLOWED_HOSTS, "localhost", "127.0.0.1", "0.0.0.0"})

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'calificaciones',

    # APIs
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',  # ✅ para /api/token/blacklist/

    # CORS
    'corsheaders',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',       # ✅ PONER PRIMERO
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Sirve estáticos en prod
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

# Base de datos (PostgreSQL en Railway / SQLite local opcional)
DATABASE_URL = os.environ.get('DATABASE_URL', '')
DB_SSL_REQUIRE = DATABASE_URL.startswith('postgres://') or DATABASE_URL.startswith('postgresql://')
DATABASES = {
    'default': dj_database_url.config(
        default=DATABASE_URL,
        conn_max_age=600,
        ssl_require=DB_SSL_REQUIRE
    )
}

CACHE_URL = os.environ.get("REDIS_URL", "").strip() or os.environ.get("CACHE_URL", "").strip()
if CACHE_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": CACHE_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "boletin-default-cache",
        }
    }

# Verificación de configuración para entorno local
if 'ENGINE' not in DATABASES['default']:
    raise Exception(
        "La variable de entorno DATABASE_URL no está definida o es inválida.\n"
        "Exportala en tu entorno local o cargala desde un archivo .env antes de correr el servidor.\n\n"
        "Windows (cmd):   set DATABASE_URL=postgres://usuario:contraseña@host:puerto/dbname\n"
        "Git Bash / Linux: export DATABASE_URL=postgres://usuario:contraseña@host:puerto/dbname"
    )

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Archivos estáticos
STATIC_URL = '/static/'
STATIC_ROOT = str(BASE_DIR / "staticfiles")
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# 🔁 Redirección post-login por rol
LOGIN_REDIRECT_URL = '/redir/'
LOGOUT_REDIRECT_URL = '/accounts/login/'
LOGIN_URL = '/accounts/login/'

# ✅ CSRF (confía también en el front local y en tu IP LAN)
CSRF_TRUSTED_ORIGINS = [
    'https://proyectocomunicaciones-production.up.railway.app',
    'http://localhost:3000',
    'http://localhost:3001',
    'http://localhost:3002',
    'http://127.0.0.1:3000',
    'http://127.0.0.1:3001',
    'http://127.0.0.1:3002',
    'http://192.168.1.38:3000',  # ← agregado: acceso por IP LAN
    # 'http://192.168.1.38:3001',  # ← opcional si a veces Next usa 3001
]

# ✅ Configuración DRF + JWT: DRF entiende sesión y/o JWT
CSRF_TRUSTED_ORIGINS = _split_env_list("CSRF_TRUSTED_ORIGINS", CSRF_TRUSTED_ORIGINS)
if ALLOW_VERCEL_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append("https://*.vercel.app")

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'calificaciones.jwt_auth.CookieJWTAuthentication',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '5/min',
        'user': '10/min',
    },
    # Si querés exigir auth por defecto, descomentá:
    # 'DEFAULT_PERMISSION_CLASSES': (
    #     'rest_framework.permissions.IsAuthenticated',
    # ),
}

# ✅ SimpleJWT — rotación + blacklist (para logout robusto)
from datetime import timedelta
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.environ.get("JWT_ACCESS_MINUTES", "60"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.environ.get("JWT_REFRESH_DAYS", "7"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}
JWT_ACCESS_COOKIE_NAME = os.environ.get("JWT_ACCESS_COOKIE_NAME", "access_token")
JWT_REFRESH_COOKIE_NAME = os.environ.get("JWT_REFRESH_COOKIE_NAME", "refresh_token")
JWT_COOKIE_PATH = os.environ.get("JWT_COOKIE_PATH", "/")
JWT_COOKIE_DOMAIN = os.environ.get("JWT_COOKIE_DOMAIN", "").strip() or None
JWT_COOKIE_SAMESITE = os.environ.get("JWT_COOKIE_SAMESITE", "Lax")
JWT_COOKIE_SECURE = os.environ.get("JWT_COOKIE_SECURE", "True" if not DEBUG else "False") == "True"
JWT_ACCESS_COOKIE_AGE = int(os.environ.get("JWT_ACCESS_COOKIE_AGE", str(int(SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()))))
JWT_REFRESH_COOKIE_AGE = int(os.environ.get("JWT_REFRESH_COOKIE_AGE", str(int(SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()))))

# ✅ CORS
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:3002",
    "http://172.16.0.2:3000",
    "http://192.168.1.38:3000",  # ← agregado: front por IP LAN
    # "http://192.168.1.38:3001",  # ← opcional si a veces Next usa 3001
]
CORS_ALLOWED_ORIGINS = _split_env_list("CORS_ALLOWED_ORIGINS", CORS_ALLOWED_ORIGINS)
CORS_ALLOW_CREDENTIALS = True

# (Opcional, solo en dev) permite cualquier IP de la subred 192.168.*:3000
# para no tener que tocar settings si cambia la IP por DHCP.
CORS_ALLOWED_ORIGIN_REGEXES = []
if DEBUG:
    CORS_ALLOWED_ORIGIN_REGEXES = [
        r"^http://192\.168\.\d{1,3}\.\d{1,3}:3000$",
    ]

# ✅ Permitir el header custom de vista previa
CORS_ALLOWED_ORIGIN_REGEXES = _split_env_list("CORS_ALLOWED_ORIGIN_REGEXES", CORS_ALLOWED_ORIGIN_REGEXES)
if ALLOW_VERCEL_ORIGINS:
    CORS_ALLOWED_ORIGIN_REGEXES.append(r"^https://.*\.vercel\.app$")

CORS_ALLOW_HEADERS = list(default_headers) + [
    "x-preview-role",   # ← necesario para enviar el rol simulado por header
]

# ✅ Cookies seguras según entorno
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

# Nota: mantener Lax para dev; si necesitás enviar cookies cross-site por fetch,
# deberás usar SameSite=None y HTTPS:
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# ✅ Detrás de proxy (Railway/Heroku)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# (Opcional) Forzar HTTPS en prod
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

# Alertas academicas por notas
ALERTAS_ACADEMICAS_VENTANA_DIAS = int(os.environ.get("ALERTAS_ACADEMICAS_VENTANA_DIAS", "45"))
ALERTAS_ACADEMICAS_SYNC_EN_CARGA_MASIVA = os.environ.get("ALERTAS_ACADEMICAS_SYNC_EN_CARGA_MASIVA", "False") == "True"
# No hay worker diferido para inasistencias; si no se evalúan al guardar,
# las alertas esperadas por la app quedan omitidas silenciosamente.
ALERTAS_INASISTENCIAS_SYNC_EN_GUARDADO = os.environ.get("ALERTAS_INASISTENCIAS_SYNC_EN_GUARDADO", "True") == "True"
ALERTAS_ACADEMICAS_COOLDOWN_DIAS = int(os.environ.get("ALERTAS_ACADEMICAS_COOLDOWN_DIAS", "7"))
ALERTAS_ACADEMICAS_ESCALADO_DIAS = int(os.environ.get("ALERTAS_ACADEMICAS_ESCALADO_DIAS", "14"))
ALERTAS_ACADEMICAS_EMAIL_ENABLED = os.environ.get("ALERTAS_ACADEMICAS_EMAIL_ENABLED", "False") == "True"

ALERTAS_INASISTENCIAS_CONSECUTIVAS = int(os.environ.get("ALERTAS_INASISTENCIAS_CONSECUTIVAS", "2"))
ALERTAS_INASISTENCIAS_COOLDOWN_DIAS = int(os.environ.get("ALERTAS_INASISTENCIAS_COOLDOWN_DIAS", "7"))
ALERTAS_INASISTENCIAS_REAPERTURA_DIAS = int(os.environ.get("ALERTAS_INASISTENCIAS_REAPERTURA_DIAS", "14"))
ALERTAS_INASISTENCIAS_UMBRALES_FALTAS = os.environ.get("ALERTAS_INASISTENCIAS_UMBRALES_FALTAS", "10,20,25")
