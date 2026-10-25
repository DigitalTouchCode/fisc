import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("fiscguy", "0014_receipt_fiscal_day_no_taxes_is_standard"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="device",
            options={
                "ordering": ["-created_at"],
                "permissions": [
                    ("manage_device", "Can register devices and manage certificates"),
                    ("close_day", "Can open and close fiscal days"),
                    ("view_receipts", "Can view receipts"),
                ],
            },
        ),
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("actor_name", models.CharField(blank=True, max_length=150)),
                ("action", models.CharField(max_length=64)),
                ("device_ref", models.CharField(blank=True, max_length=100)),
                ("detail", models.CharField(blank=True, max_length=255)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "device",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="fiscguy.device",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [models.Index(fields=["action", "-created_at"], name="fiscguy_audit_action_idx")],
            },
        ),
    ]
