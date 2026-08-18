from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.test import SimpleTestCase

from apps.b2b_order_projects.models import B2BOrderProject
from apps.portal.dashboard_focus import (
    attach_project_dashboard_verbs,
    build_client_dashboard_focus,
    exclude_focused_item,
    format_linear_m,
    format_money,
    project_action_label,
)


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


def _project(status, name="Lot atelier"):
    return SimpleNamespace(
        public_id=uuid4(),
        project_number="PRJ-TEST",
        name=name,
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
        self.assertIn('href="{{ client_focus.action_url }}"', template)
        self.assertIn("client-dashboard-focus__verb", template)
        self.assertIn("client_focus.action_url", template)
        self.assertIn("client-dashboard-head", template)
        self.assertIn("client-dashboard-board", template)
        self.assertIn('aria-label="{{ client_focus.heading }}"', template)
        self.assertIn("client_focus.title", template)
        self.assertIn(">Encours</h2>", template)
        self.assertNotIn("Déjà en tête de page.", template)
        self.assertIn("listed_projects or not client_focus.project_public_id", template)
        self.assertIn('order.status != "submitted"', template)
        self.assertIn("listed_projects", template)
        self.assertIn("project.dashboard_verb", template)
        self.assertIn('"Commande à reprendre"', focus_builder)
        self.assertIn('"Action nécessaire"', focus_builder)
        self.assertIn('"Expédition à suivre"', focus_builder)
        self.assertIn('"Dernière commande"', focus_builder)
        self.assertIn('query="?panel=shipping"', focus_builder)

    def test_client_focus_prioritizes_actionable_project_over_payment(self) -> None:
        project = _project(B2BOrderProject.Status.ACTION_REQUIRED)
        focus = build_client_dashboard_focus(
            customer=SimpleNamespace(public_id=uuid4()),
            recent_projects=[project],
            recent_orders=[_order(awaits_payment=True)],
            new_order_url="/nouvelle-commande/",
        )

        self.assertEqual(focus["label"], "Action nécessaire")
        self.assertEqual(focus["action_label"], "Corriger")
        self.assertEqual(focus["heading"], "Corriger · Lot atelier")
        self.assertEqual(focus["title"], "Lot atelier")
        self.assertIn("PRJ-TEST", focus["detail"])
        self.assertIn("1 visuel", focus["detail"])
        self.assertNotIn("visuel(s)", focus["detail"])
        self.assertIn("project", focus["action_url"])
        self.assertEqual(
            exclude_focused_item(items=[project], public_id=focus["project_public_id"]),
            [],
        )

    def test_client_focus_uses_transmit_verb_when_project_is_ready(self) -> None:
        focus = build_client_dashboard_focus(
            customer=SimpleNamespace(public_id=uuid4()),
            recent_projects=[_project(B2BOrderProject.Status.READY_TO_SUBMIT, name="tftttf")],
            recent_orders=[],
            new_order_url="/nouvelle-commande/",
        )

        self.assertEqual(focus["label"], "Prêt à transmettre")
        self.assertEqual(focus["action_label"], "Transmettre")
        self.assertEqual(focus["heading"], "Transmettre · tftttf")

    def test_client_focus_prioritizes_payment_over_non_actionable_project(self) -> None:
        focus = build_client_dashboard_focus(
            customer=SimpleNamespace(public_id=uuid4()),
            recent_projects=[_project(B2BOrderProject.Status.UNDER_REVIEW)],
            recent_orders=[_order(awaits_payment=True)],
            new_order_url="/nouvelle-commande/",
        )

        self.assertEqual(focus["label"], "Action nécessaire")
        self.assertTrue(focus["action_url"].endswith("?panel=billing&pay=1"))

    def test_collaborator_skips_payment_focus_for_order_tracking(self) -> None:
        focus = build_client_dashboard_focus(
            customer=SimpleNamespace(public_id=uuid4()),
            recent_projects=[],
            recent_orders=[_order(awaits_payment=True)],
            new_order_url="/nouvelle-commande/",
            can_view_account_finance=False,
        )

        self.assertEqual(focus["label"], "Dernière commande")
        self.assertEqual(focus["action_label"], "Ouvrir")
        self.assertFalse(focus["action_url"].endswith("?panel=billing&pay=1"))

    def test_client_focus_links_tracking_to_internal_shipping_panel(self) -> None:
        focus = build_client_dashboard_focus(
            customer=SimpleNamespace(public_id=uuid4()),
            recent_projects=[],
            recent_orders=[_order(tracking_number="TRACK-42")],
            new_order_url="/nouvelle-commande/",
        )

        self.assertEqual(focus["label"], "Expédition à suivre")
        self.assertTrue(focus["action_url"].endswith("?panel=shipping"))

    def test_listed_projects_reuse_status_verbs(self) -> None:
        ready = _project(B2BOrderProject.Status.READY_TO_SUBMIT)
        draft = _project(B2BOrderProject.Status.DRAFT)
        attach_project_dashboard_verbs([ready, draft])
        self.assertEqual(project_action_label(B2BOrderProject.Status.READY_TO_SUBMIT), "Transmettre")
        self.assertEqual(ready.dashboard_verb, "Transmettre")
        self.assertEqual(draft.dashboard_verb, "Compléter")

    def test_linear_meters_are_formatted_without_trailing_zeros(self) -> None:
        self.assertEqual(format_linear_m("20.0000"), "20 m")
        self.assertEqual(format_linear_m("0.0000"), "0 m")
        self.assertEqual(format_linear_m("12.3500"), "12,4 m")
        self.assertEqual(format_money("128.50"), "128,50 €")
