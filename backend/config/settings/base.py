import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parents[2]


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise ImproperlyConfigured(f"Missing required environment variable: {name}")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return int(raw_value)


def env_list(name: str, default: str = "") -> list[str]:
    raw_value = os.environ.get(name, default)
    return [item.strip() for item in raw_value.split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.core",
    "apps.accounts",
    "apps.customers",
    "apps.auditlog",
    "apps.notifications",
    "apps.catalog",
    "apps.billing",
    "apps.orders",
    "apps.production",
    "apps.portal",
    "apps.prospects",
    "apps.shipping",
    "apps.uploads",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.LoginRateLimitMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "prenium_dtf"),
        "USER": env("POSTGRES_USER", "prenium_dtf"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", "db"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": env_int("POSTGRES_CONN_MAX_AGE", 60),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = env("DJANGO_TIME_ZONE", "Europe/Paris")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = Path(env("DJANGO_STATIC_ROOT", "/tmp/prenium-dtf/static"))
STATICFILES_DIRS = [BASE_DIR / "static_src"]

MEDIA_URL = "/protected-media/"
MEDIA_ROOT = Path(env("DJANGO_MEDIA_ROOT", "/tmp/prenium-dtf/media"))
ORDER_UPLOAD_MAX_BYTES = env_int("ORDER_UPLOAD_MAX_BYTES", 20 * 1024 * 1024)
ORDER_UPLOAD_ALLOWED_MIME_TYPES = tuple(
    env_list(
        "ORDER_UPLOAD_ALLOWED_MIME_TYPES",
        "application/pdf,image/png,image/jpeg,image/svg+xml,image/tiff,"
        "application/postscript,image/vnd.adobe.photoshop,application/x-photoshop",
    )
)
DTF_PRINT_DPI = env_int("DTF_PRINT_DPI", 300)
# Largeur utile film / laize (cm) :
# le prix au m² s’applique à une conso. type « bande » sur cette largeur.
DTF_LAIZE_CM = env_int("DTF_LAIZE_CM", 55)
# pixel_rectangle = aire du rectangle physique (pixels ÷ DPI)
# laize_fit = tient compte de la laize (recommandé atelier)
DTF_METERAGE_AREA_MODE = os.environ.get("DTF_METERAGE_AREA_MODE", "laize_fit")

GOOGLE_DRIVE_SHARED_DRIVE_ID = env("GOOGLE_DRIVE_SHARED_DRIVE_ID", "")
GOOGLE_DRIVE_ROOT_FOLDER_ID = env("GOOGLE_DRIVE_ROOT_FOLDER_ID", "")
GOOGLE_DRIVE_ROOT_FOLDER_NAME = env("GOOGLE_DRIVE_ROOT_FOLDER_NAME", "Commandes")
GOOGLE_DRIVE_ACCESS_TOKEN = os.environ.get("GOOGLE_DRIVE_ACCESS_TOKEN", "")
GOOGLE_DRIVE_API_BASE_URL = os.environ.get(
    "GOOGLE_DRIVE_API_BASE_URL",
    "https://www.googleapis.com/drive/v3",
)
GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON = env("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON", "")
GOOGLE_DRIVE_SYNC_ENABLED = env_bool("GOOGLE_DRIVE_SYNC_ENABLED", False)
GOOGLE_DRIVE_TIMEOUT_SECONDS = env_int("GOOGLE_DRIVE_TIMEOUT_SECONDS", 30)
SENDCLOUD_PUBLIC_KEY = os.environ.get("SENDCLOUD_PUBLIC_KEY", "")
SENDCLOUD_SECRET_KEY = os.environ.get("SENDCLOUD_SECRET_KEY", "")
SENDCLOUD_API_BASE_URL = os.environ.get(
    "SENDCLOUD_API_BASE_URL",
    "https://panel.sendcloud.sc/api/v3",
)
SENDCLOUD_TIMEOUT_SECONDS = env_int("SENDCLOUD_TIMEOUT_SECONDS", 30)
SENDCLOUD_SENDER_NAME = os.environ.get("SENDCLOUD_SENDER_NAME", "")
SENDCLOUD_SENDER_COMPANY_NAME = os.environ.get("SENDCLOUD_SENDER_COMPANY_NAME", "")
SENDCLOUD_SENDER_ADDRESS_LINE_1 = os.environ.get("SENDCLOUD_SENDER_ADDRESS_LINE_1", "")
SENDCLOUD_SENDER_ADDRESS_LINE_2 = os.environ.get("SENDCLOUD_SENDER_ADDRESS_LINE_2", "")
SENDCLOUD_SENDER_HOUSE_NUMBER = os.environ.get("SENDCLOUD_SENDER_HOUSE_NUMBER", "")
SENDCLOUD_SENDER_POSTAL_CODE = os.environ.get("SENDCLOUD_SENDER_POSTAL_CODE", "")
SENDCLOUD_SENDER_CITY = os.environ.get("SENDCLOUD_SENDER_CITY", "")
SENDCLOUD_SENDER_COUNTRY_CODE = os.environ.get("SENDCLOUD_SENDER_COUNTRY_CODE", "")
SENDCLOUD_SENDER_EMAIL = os.environ.get("SENDCLOUD_SENDER_EMAIL", "")
SENDCLOUD_SENDER_PHONE_NUMBER = os.environ.get("SENDCLOUD_SENDER_PHONE_NUMBER", "")

PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.environ.get("PAYPAL_CLIENT_SECRET", "")
PAYPAL_API_BASE_URL = os.environ.get("PAYPAL_API_BASE_URL", "https://api-m.sandbox.paypal.com")
PAYPAL_TIMEOUT_SECONDS = env_int("PAYPAL_TIMEOUT_SECONDS", 30)
PAYPAL_INTERNAL_CONFIRM_TOKEN = os.environ.get("PAYPAL_INTERNAL_CONFIRM_TOKEN", "")

DEFAULT_FROM_EMAIL = os.environ.get("DJANGO_DEFAULT_FROM_EMAIL", "Prenium DTF <noreply@localhost>")
TRANSACTIONAL_EMAILS_ENABLED = env_bool("TRANSACTIONAL_EMAILS_ENABLED", True)
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = env_int("LOGIN_RATE_LIMIT_MAX_ATTEMPTS", 20)
LOGIN_RATE_LIMIT_WINDOW_SECONDS = env_int("LOGIN_RATE_LIMIT_WINDOW_SECONDS", 900)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

REDIS_URL = env("REDIS_URL", "redis://redis:6379/1")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "TIMEOUT": 300,
    }
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = env_int("CELERY_TASK_TIME_LIMIT", 300)
CELERY_TASK_SOFT_TIME_LIMIT = env_int("CELERY_TASK_SOFT_TIME_LIMIT", 240)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/client/"
LOGOUT_REDIRECT_URL = "/login/"

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_SECURE = env_bool("DJANGO_SESSION_COOKIE_SECURE", False)
CSRF_COOKIE_SECURE = env_bool("DJANGO_CSRF_COOKIE_SECURE", False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", False)
SECURE_REFERRER_POLICY = "same-origin"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        }
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
    },
}
