import django
from django.conf import settings


def pytest_configure():
    if not settings.configured:
        settings.configure(
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                "fiscguy",
            ],
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": ":memory:",
                }
            },
            SECRET_KEY="fake-key-for-tests",
        )
        django.setup()

        from django.core.management import call_command

        call_command("migrate", run_syncdb=True, verbosity=0)
