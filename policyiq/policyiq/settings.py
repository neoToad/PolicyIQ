import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv()

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() in ("true", "1", "yes")

# Fail loudly if the insecure scaffold key is used in production.
if not DEBUG and SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set to a cryptographically random value in production. "
        "Set the DJANGO_SECRET_KEY environment variable."
    )
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework.authtoken",
    "documents",
    "queries",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "policyiq.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "policyiq.wsgi.application"
ASGI_APPLICATION = "policyiq.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "policyiq"),
        "USER": os.environ.get("POSTGRES_USER", "policyiq"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "policyiq"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
CHROMA_PERSIST_DIR = BASE_DIR / "chroma"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LLM_BACKEND = os.environ.get("LLM_BACKEND", "ollama")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

# Throttle rates are env-overridable so ops can tune limits without code changes.
# Format is "<count>/<period>" where period is `s`, `m`, `h`, or `d`.
THROTTLE_QUERY_ANON = os.environ.get("THROTTLE_QUERY_ANON", "30/hour")
THROTTLE_QUERY_USER = os.environ.get("THROTTLE_QUERY_USER", "120/hour")
THROTTLE_UPLOAD_ANON = os.environ.get("THROTTLE_UPLOAD_ANON", "5/hour")
THROTTLE_UPLOAD_USER = os.environ.get("THROTTLE_UPLOAD_USER", "30/hour")

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "query_anon": THROTTLE_QUERY_ANON,
        "query_user": THROTTLE_QUERY_USER,
        "upload_anon": THROTTLE_UPLOAD_ANON,
        "upload_user": THROTTLE_UPLOAD_USER,
    },
}

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if origin.strip()
]

# Logging configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(BASE_DIR / "logs" / "policyiq.log"),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 3,
            "formatter": "verbose",
            "delay": True,
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
    "loggers": {
        "documents": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "queries": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}


def _is_test_run() -> bool:
    """Detect Django's test runner or pytest (pytest does not inject 'test' into sys.argv)."""
    if "test" in sys.argv:
        return True
    # When pytest is invoked directly, sys.argv[0] is the pytest executable path.
    return bool(sys.argv and "pytest" in sys.argv[0])


# Use an in-memory SQLite database for tests so they run without PostgreSQL privileges.
if _is_test_run():
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
    # Silence noisy service retry logs during test runs.
    LOGGING["loggers"]["documents"]["level"] = "ERROR"
    LOGGING["loggers"]["queries"]["level"] = "ERROR"
