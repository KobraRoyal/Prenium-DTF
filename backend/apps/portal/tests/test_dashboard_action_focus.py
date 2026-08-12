from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.test import SimpleTestCase

from apps.b2b_order_projects.models import B2BOrderProject
from apps.portal.dashboard_focus import build_client_dashboard_focus


class _OrderWithoutShipment(SimpleNamespace):
    @property
    def shipment(self):
        raise ObjectDoesNotExist


def _order(*, awaits_payment=False, tracking_number=""):
    order = _OrderWithoutShipment(
        public_id=uuid4(),
        source_b2b_order_project=None,
        customer_note="",
        status="submitted",
        awaits_client_payment=awaits_payment,
    )
    if tracking_number:
        order = SimpleNamespace(**vars(order))
        order.shipment = SimpleNamespace(tracking_number=tracking_number)
    return order


def _project(status):
    return SimpleNamespace(
        public_id=uuid4(),
        project_number="PRJ-TEST",
        status=status,
        items=SimpleNamespace(all=lambda: [object()]),
        get_status_display=lambda: "Action requise",
    )


class DashboardActionFocusTests(SimpleTestCase):
    def test_staff_dashboard_surfaces_one_real_next_action(self) -> None:
        template = (Path(settings.BASE_DIR) / "templates/portal/staff/dashboard.html").read_text(
            encoding="utf-8"
        )
        view = (Path(settings.BASE_DIR) / "apps/portal/views_staff_dashboard.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("Prochain geste", template)
        self.assertIn("worklist_rows.0.next_action", template)
        self.assertIn('"action_url"', view)
        self.assertIn('"Blocages à lever"', view)

    def test_client_dashboard_prioritizes_resume_payment_or_tracking(self) -> None:
        template = (Path(settings.BASE_DIR) / "templates/portal/client/dashboard.html").read_text(
            encoding="utf-8"
        )
        focus_builder = (Path(settings.BASE_DIR) / "apps/portal/dashboard_focus.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("client-dashboard-focus", template)
        self.assertIn("client_focus.action_url", template)
        self.assertIn('"Commande à reprendre"', focus_builder)
        self.assertIn('"Action nécessaire"', focus_builder)
        self.assertIn('"Expédition à suivre"', focus_builder)
        self.assertIn('"Dernière commande"', focus_builder)
        self.assertIn('query="?panel=shipping"', focus_builder)

    def test_client_focus_prioritizes_actionable_project_over_payment(self) -> None:
        focus = build_client_dashboard_focus(
            customer=SimpleNamespace(public_id=uuid4()),
            recent_projects=[_project(B2BOrderProject.Status.ACTION_REQUIRED)],
            recent_orders=[_order(awaits_payment=True)],
            new_order_url="/nouvelle-commande/",
        )

        self.assertEqual(focus["label"], "Commande à reprendre")
        self.assertIn("project", focus["action_url"])

    def test_client_focus_prioritizes_payment_over_non_actionable_project(self) -> None:
        focus = build_client_dashboard_focus(
            customer=SimpleNamespace(public_id=uuid4()),
            recent_projects=[_project(B2BOrderProject.Status.UNDER_REVIEW)],
            recent_orders=[_order(awaits_payment=True)],
            new_order_url="/nouvelle-commande/",
        )

        self.assertEqual(focus["label"], "Action nécessaire")
        self.assertTrue(focus["action_url"].endswith("?panel=billing&pay=1"))

    def test_client_focus_links_tracking_to_internal_shipping_panel(self) -> None:
        focus = build_client_dashboard_focus(
            customer=SimpleNamespace(public_id=uuid4()),
            recent_projects=[],
            recent_orders=[_order(tracking_number="TRACK-42")],
            new_order_url="/nouvelle-commande/",
        )

        self.assertEqual(focus["label"], "Expédition à suivre")
        self.assertTrue(focus["action_url"].endswith("?panel=shipping"))
