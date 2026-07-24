# Generated manually — Stripe provider fields + settlement choice.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0004_alter_invoice_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="stripe_checkout_session_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="payment",
            name="stripe_payment_intent_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(
            model_name="payment",
            name="provider",
            field=models.CharField(
                choices=[("paypal", "PayPal"), ("stripe", "Stripe")],
                default="paypal",
                max_length=16,
            ),
        ),
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(fields=["provider", "status"], name="billing_pay_provide_a1b2c3_idx"),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                condition=~models.Q(stripe_checkout_session_id=""),
                fields=("stripe_checkout_session_id",),
                name="uniq_payment_stripe_checkout_session_id_non_empty",
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                condition=~models.Q(stripe_payment_intent_id=""),
                fields=("stripe_payment_intent_id",),
                name="uniq_payment_stripe_payment_intent_id_non_empty",
            ),
        ),
    ]
