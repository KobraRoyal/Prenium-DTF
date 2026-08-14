import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0008_billing_statement_snapshots"),
        ("orders", "0007_monthly_volume_discount_snapshots"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="billing_statement",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="orders",
                to="billing.billingstatement",
            ),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=models.Q(("volume_discount_percent__gte", 0))
                & models.Q(("volume_discount_percent__lte", 100)),
                name="order_volume_discount_percent_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=models.Q(("volume_discount_amount__gte", 0)),
                name="order_volume_discount_amount_nonnegative",
            ),
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(
                condition=models.Q(
                    ("billing_mode", "deferred"),
                    ("billing_statement__isnull", True),
                    ("pricing_status", "priced"),
                    ("status", "submitted"),
                ),
                fields=["customer", "created_at"],
                name="order_billable_month_idx",
            ),
        ),
    ]
