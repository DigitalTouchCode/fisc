from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fiscguy", "0013_receiptline_hs_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="receipt",
            name="fiscal_day_no",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="taxes",
            name="is_standard",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="receipt",
            name="receipt_number",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddConstraint(
            model_name="receipt",
            constraint=models.UniqueConstraint(
                condition=models.Q(("receipt_number__isnull", False)),
                fields=("device", "receipt_number"),
                name="unique_receipt_number_per_device",
            ),
        ),
    ]
