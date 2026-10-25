from django.db import migrations

import fiscguy.fields
from fiscguy.security import decrypt_value, encrypt_value


def encrypt_existing(apps, schema_editor):
    Device = apps.get_model("fiscguy", "Device")
    for pk, value in Device.objects.values_list("id", "activation_key"):
        if value:
            Device.objects.filter(id=pk).update(activation_key=encrypt_value(value))


def decrypt_existing(apps, schema_editor):
    Device = apps.get_model("fiscguy", "Device")
    for pk, value in Device.objects.values_list("id", "activation_key"):
        if value:
            Device.objects.filter(id=pk).update(activation_key=decrypt_value(value))


class Migration(migrations.Migration):
    dependencies = [
        ("fiscguy", "0015_audit_log_and_permissions"),
    ]

    operations = [
        migrations.AlterField(
            model_name="device",
            name="activation_key",
            field=fiscguy.fields.EncryptedTextField(),
        ),
        migrations.RunPython(encrypt_existing, reverse_code=decrypt_existing),
    ]
