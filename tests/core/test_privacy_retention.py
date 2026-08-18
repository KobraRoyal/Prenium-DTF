from datetime import timedelta

import pytest
from apps.accounts.services.privacy import apply_privacy_retention, sanitize_provider_payload
from apps.auditlog.models import AuditLogEntry
from apps.billing.models import Payment
from apps.customers.models import Customer
from apps.orders.models import Order
from apps.prospects.models import ProspectProfile
from apps.shipping.models import Shipment
from django.utils import timezone


def test_sanitize_provider_payload_keeps_technical_ids_only():
    sanitized = sanitize_provider_payload(
        {
            "id": "cs_test_1",
            "status": "complete",
            "customer_details": {"email": "hidden@example.com"},
            "url": "https://checkout.example/secret",
        }
    )
    assert sanitized == {"id": "cs_test_1", "status": "complete"}
    assert "hidden@example.com" not in str(sanitized)


@pytest.mark.django_db
def test_privacy_retention_clears_old_ip_payloads_and_prospects():
    old = timezone.now() - timedelta(days=800)
    audit = AuditLogEntry.objects.create(
        action="security.login_rate_limited",
        ip_address="203.0.113.10",
    )
    AuditLogEntry.objects.filter(pk=audit.pk).update(created_at=old)

    customer = Customer.objects.create(name="Retention Co")
    order = Order.objects.create(customer=customer, source="test")
    payment = Payment.objects.create(
        order=order,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.CAPTURED,
        amount="10.00",
        currency="EUR",
        provider_payload={"id": "cs_1", "customer_details": {"email": "pay@example.com"}},
    )
    Payment.objects.filter(pk=payment.pk).update(updated_at=old)

    shipment = Shipment.objects.create(
        order=order,
        request_snapshot={"recipient": {"email": "ship@example.com", "city": "Lyon"}},
    )
    Shipment.objects.filter(pk=shipment.pk).update(updated_at=old)

    prospect = ProspectProfile.objects.create(
        first_name="Léa",
        last_name="Durand",
        email="prospect-old@example.com",
        phone="+33600000000",
        company="Old Co",
        country="FR",
        activity_type=ProspectProfile.ActivityType.BRAND,
        service_interest=ProspectProfile.ServiceInterest.DTF_METER,
        project_timing=ProspectProfile.ProjectTiming.EXPLORING,
        monthly_volume=ProspectProfile.MonthlyVolume.LT10,
        order_frequency=ProspectProfile.OrderFrequency.PUNCTUAL,
        urgency=ProspectProfile.Urgency.LOW,
        status=ProspectProfile.Status.REJECTED,
        is_open=False,
    )
    ProspectProfile.objects.filter(pk=prospect.pk).update(updated_at=old)

    stats = apply_privacy_retention(
        audit_ip_days=365,
        payment_payload_days=90,
        shipment_snapshot_days=90,
        prospect_pii_days=730,
    )

    audit.refresh_from_db()
    payment.refresh_from_db()
    shipment.refresh_from_db()
    prospect.refresh_from_db()
    assert audit.ip_address is None
    assert payment.provider_payload.get("id") == "cs_1"
    assert "pay@example.com" not in str(payment.provider_payload)
    assert shipment.request_snapshot["recipient"]["email"] == "[redacted]"
    assert prospect.phone == ""
    assert prospect.email.endswith("@invalid.localhost")
    assert stats["audit_ips_cleared"] == 1
    assert stats["prospects_anonymized"] == 1
