import django
from django.conf import settings


def pytest_configure():
    if not settings.configured:
        settings.configure(
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                "django.contrib.auth",
                "django.contrib.sessions",
                "django.contrib.messages",
                "django.contrib.staticfiles",
                "rest_framework",
                "fiscguy",
            ],
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": ":memory:",
                }
            },
            SECRET_KEY="fake-key-for-tests",
            STATIC_URL="/static/",
            LOGIN_URL="/login/",
            MIDDLEWARE=[
                "django.contrib.sessions.middleware.SessionMiddleware",
                "django.middleware.csrf.CsrfViewMiddleware",
                "django.contrib.auth.middleware.AuthenticationMiddleware",
                "django.contrib.messages.middleware.MessageMiddleware",
            ],
            TEMPLATES=[
                {
                    "BACKEND": "django.template.backends.django.DjangoTemplates",
                    "APP_DIRS": True,
                    "OPTIONS": {
                        "context_processors": [
                            "django.template.context_processors.request",
                            "django.contrib.auth.context_processors.auth",
                            "django.contrib.messages.context_processors.messages",
                        ]
                    },
                }
            ],
            ROOT_URLCONF="fiscguy.urls",
            FISCGUY_PERMISSION_CLASSES=["rest_framework.permissions.AllowAny"],
            DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
            REST_FRAMEWORK={
                "DEFAULT_AUTHENTICATION_CLASSES": [],
                "DEFAULT_PERMISSION_CLASSES": [],
            },
        )
        django.setup()

        from django.core.management import call_command

        call_command("migrate", run_syncdb=True, verbosity=0)
