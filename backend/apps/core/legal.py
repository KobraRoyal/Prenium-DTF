from __future__ import annotations

from django.conf import settings


def _text(name: str, default: str = "") -> str:
    return str(getattr(settings, name, default) or "").strip()


def get_legal_context() -> dict[str, object]:
    """Identité du responsable de traitement exposée aux pages légales."""
    privacy_email = _text("LEGAL_PRIVACY_EMAIL") or _text(
        "LEGAL_CONTACT_EMAIL", "privacy@localhost"
    )
    return {
        "brand_name": _text("LEGAL_BRAND_NAME", "Prenium DTF"),
        "controller_name": _text("LEGAL_CONTROLLER_NAME", "IDS Supply"),
        "legal_form": _text("LEGAL_CONTROLLER_LEGAL_FORM"),
        "address": _text("LEGAL_CONTROLLER_ADDRESS"),
        "postal_code": _text("LEGAL_CONTROLLER_POSTAL_CODE"),
        "city": _text("LEGAL_CONTROLLER_CITY"),
        "country": _text("LEGAL_CONTROLLER_COUNTRY", "France"),
        "siren": _text("LEGAL_CONTROLLER_SIREN"),
        "vat_number": _text("LEGAL_CONTROLLER_VAT"),
        "contact_email": _text("LEGAL_CONTACT_EMAIL", "contact@localhost"),
        "privacy_email": privacy_email,
        "publication_director": _text("LEGAL_PUBLICATION_DIRECTOR"),
        "hosting_description": _text(
            "LEGAL_HOSTING_DESCRIPTION",
            "Infrastructure auto-hébergée en France",
        ),
        "google_drive_enabled": bool(getattr(settings, "GOOGLE_DRIVE_SYNC_ENABLED", False)),
        "audit_ip_retention_days": int(getattr(settings, "PRIVACY_AUDIT_IP_RETENTION_DAYS", 365)),
        "payment_payload_retention_days": int(
            getattr(settings, "PRIVACY_PAYMENT_PAYLOAD_RETENTION_DAYS", 90)
        ),
        "shipment_snapshot_retention_days": int(
            getattr(settings, "PRIVACY_SHIPMENT_SNAPSHOT_RETENTION_DAYS", 90)
        ),
        "prospect_pii_retention_days": int(
            getattr(settings, "PRIVACY_PROSPECT_PII_RETENTION_DAYS", 730)
        ),
    }


def legal_identity(request):
    return {"legal": get_legal_context()}
