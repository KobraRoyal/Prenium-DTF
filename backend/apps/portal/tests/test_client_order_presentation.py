from datetime import date
from types import SimpleNamespace
from uuid import UUID

from django.test import SimpleTestCase

from apps.portal.client_order_presentation import client_order_identity, client_order_status_banner


class ClientOrderIdentityTests(SimpleTestCase):
    def test_project_identity_uses_business_reference_and_structured_details(self) -> None:
        project = SimpleNamespace(
            name="Collection été",
            customer_reference="",
            project_number="CMD-2026-000104",
            customer_comment="Livraison avant ouverture",
            requested_date=date(2026, 8, 29),
        )
        order = SimpleNamespace(
            public_id=UUID("d23e2006-00d0-4d8d-9807-2de08f2ddf25"),
            customer_note="Collection été\nCommande CMD-2026-000104\nDate souhaitée : 2026-08-29",
            source_b2b_order_project=project,
        )

        identity = client_order_identity(order)

        self.assertEqual(identity.label, "Collection été")
        self.assertEqual(identity.reference, "CMD-2026-000104")
        self.assertEqual(identity.note, "Livraison avant ouverture")
        self.assertEqual(identity.requested_date, date(2026, 8, 29))

    def test_legacy_identity_removes_title_duplicate_from_note(self) -> None:
        order = SimpleNamespace(
            public_id=UUID("d23e2006-00d0-4d8d-9807-2de08f2ddf25"),
            customer_note="Collection été\nLivraison avant ouverture",
            source_b2b_order_project=None,
        )

        identity = client_order_identity(order)

        self.assertEqual(identity.label, "Collection été")
        self.assertEqual(identity.reference, "")
        self.assertEqual(identity.note, "Livraison avant ouverture")
        self.assertIsNone(identity.requested_date)


class ClientOrderStatusBannerTests(SimpleTestCase):
    def test_paid_query_param_takes_priority_over_other_states(self) -> None:
        banner = client_order_status_banner(
            awaits_client_payment=True,
            query_params={
                "paid": "1",
                "checkout": "success",
                "cancelled": "1",
            },
        )

        self.assertIsNotNone(banner)
        assert banner is not None
        self.assertEqual(banner.tone, "success")
        self.assertIn("Paiement confirmé", banner.message)
        self.assertFalse(banner.show_pay_cta)

    def test_cancelled_shows_warning_with_pay_cta(self) -> None:
        banner = client_order_status_banner(
            awaits_client_payment=True,
            query_params={"cancelled": "1"},
        )

        self.assertIsNotNone(banner)
        assert banner is not None
        self.assertEqual(banner.tone, "warning")
        self.assertEqual(banner.message, "Paiement non finalisé.")
        self.assertTrue(banner.show_pay_cta)

    def test_checkout_success_with_pending_payment_shows_single_warning(self) -> None:
        banner = client_order_status_banner(
            awaits_client_payment=True,
            query_params={"checkout": "success"},
        )

        self.assertIsNotNone(banner)
        assert banner is not None
        self.assertEqual(banner.tone, "warning")
        self.assertIn("paiement non finalisé", banner.message.lower())
        self.assertTrue(banner.show_pay_cta)

    def test_checkout_success_without_pending_payment_is_transmitted(self) -> None:
        banner = client_order_status_banner(
            awaits_client_payment=False,
            query_params={"checkout": "success"},
        )

        self.assertIsNotNone(banner)
        assert banner is not None
        self.assertEqual(banner.tone, "success")
        self.assertEqual(banner.message, "Commande transmise.")
        self.assertFalse(banner.show_pay_cta)

    def test_pending_payment_without_query_flash_shows_waiting_message(self) -> None:
        banner = client_order_status_banner(
            awaits_client_payment=True,
            query_params={},
        )

        self.assertIsNotNone(banner)
        assert banner is not None
        self.assertEqual(banner.tone, "warning")
        self.assertIn("attend votre paiement", banner.message.lower())
        self.assertTrue(banner.show_pay_cta)

    def test_no_banner_when_payment_not_required(self) -> None:
        banner = client_order_status_banner(
            awaits_client_payment=False,
            query_params={},
        )

        self.assertIsNone(banner)
