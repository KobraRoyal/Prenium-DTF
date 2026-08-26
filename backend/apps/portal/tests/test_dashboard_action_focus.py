from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.test import SimpleTestCase

from apps.b2b_order_projects.models import B2BOrderProject
from apps.portal.dashboard_focus import (
    attach_volume_nudge,
    build_client_dashboard_focus,
    split_dashboard_lists,
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
        ) + (
            Path(settings.BASE_DIR)
            / "templates/portal/staff/partials/dashboard_worklist_panel.html"
        ).read_text(encoding="utf-8")
        order_detail = (
            Path(settings.BASE_DIR) / "templates/portal/staff/order_detail.html"
        ).read_text(encoding="utf-8") + (
            Path(settings.BASE_DIR)
            / "templates/components/portal/page_head_actions/staff_order_detail.html"
        ).read_text(encoding="utf-8")

        self.assertNotIn("Prochain geste", template)
        self.assertNotIn("atelier-next-action", template)
        self.assertNotIn("Prochain geste", order_detail)
        self.assertNotIn("atelier-next-action", order_detail)
        self.assertIn("page_head_actions/staff_order_detail.html", order_detail)
        self.assertIn("staff_order_focus.action_label", order_detail)
        self.assertIn("Imprimer le lot", template)

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
        self.assertEqual(focus["detail"], "Action requise")
        self.assertIn("project", focus["action_url"])

    def test_focused_project_is_removed_from_dashboard_lists(self) -> None:
        project = _project(B2BOrderProject.Status.READY_TO_SUBMIT)
        focus = build_client_dashboard_focus(
            customer=SimpleNamespace(public_id=uuid4()),
            recent_projects=[project],
            recent_orders=[],
            new_order_url="/nouvelle-commande/",
        )
        remaining_projects, remaining_orders = split_dashboard_lists(
            focus=focus,
            recent_projects=[project],
            recent_orders=[],
        )

        self.assertEqual(focus["kind"], "resume")
        self.assertEqual(remaining_projects, [])
        self.assertEqual(remaining_orders, [])

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


def _tier(*, threshold="5.0000", percent="10.00"):
    return SimpleNamespace(
        minimum_monthly_linear_m=Decimal(threshold),
        discount_percent=Decimal(percent),
    )


class VolumeNudgeTests(SimpleTestCase):
    def test_cash_start_nudge_asks_for_first_paid_sheet(self) -> None:
        nudge = attach_volume_nudge(
            {
                "monthly_volume_linear_m": Decimal("0.0000"),
                "current_tier": None,
                "next_tier": _tier(),
                "remaining_to_next_tier_linear_m": Decimal("5.0000"),
                "policy": "prospective",
            },
            stored_copy={},
        )

        self.assertEqual(nudge["nudge_stage"], "start")
        self.assertEqual(nudge["nudge_headline"], "Encore 5 m pour -10 %")
        self.assertEqual(
            nudge["nudge_message"],
            "Le palier s’applique à cette commande, sans rétroactivité.",
        )

    def test_deferred_max_nudge_celebrates_retroactive_rate(self) -> None:
        nudge = attach_volume_nudge(
            {
                "monthly_volume_linear_m": Decimal("12.0000"),
                "current_tier": _tier(threshold="10.0000", percent="20.00"),
                "next_tier": None,
                "remaining_to_next_tier_linear_m": None,
                "policy": "retroactive",
            },
            stored_copy={},
        )

        self.assertEqual(nudge["nudge_stage"], "max")
        self.assertEqual(nudge["nudge_headline"], "Palier max : -20 %")
        self.assertEqual(
            nudge["nudge_message"],
            "Meilleur taux du mois, sur tout le DTF encours.",
        )

    def test_hot_nudge_when_close_to_next_tier(self) -> None:
        nudge = attach_volume_nudge(
            {
                "monthly_volume_linear_m": Decimal("4.2000"),
                "current_tier": None,
                "next_tier": _tier(),
                "remaining_to_next_tier_linear_m": Decimal("0.8000"),
                "policy": "prospective",
            },
            stored_copy={},
        )

        self.assertEqual(nudge["nudge_stage"], "hot")
        self.assertEqual(nudge["nudge_headline"], "Plus que 0,8 m pour -10 %")
        self.assertNotIn("0,8 m", nudge["nudge_message"])
        self.assertEqual(
            nudge["nudge_message"],
            "Le prochain palier s’applique à la commande qui le franchit.",
        )

    def test_custom_copy_interpolates_placeholders(self) -> None:
        nudge = attach_volume_nudge(
            {
                "monthly_volume_linear_m": Decimal("0.0000"),
                "current_tier": None,
                "next_tier": _tier(),
                "remaining_to_next_tier_linear_m": Decimal("5.0000"),
                "policy": "prospective",
            },
            stored_copy={"start_immediate": "Plus que {remaining_m} m pour -{next_percent} %."},
        )

        self.assertEqual(nudge["nudge_message"], "Plus que 5 m pour -10 %.")
