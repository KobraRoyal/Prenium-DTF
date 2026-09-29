from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand, CommandError

from apps.customers.models import Customer
from apps.pod.services.ops_demo import PodOpsBootstrapService


class Command(BaseCommand):
    help = (
        "Seed atelier POD WMS à partir du fichier unique de la bibliothèque Drive HD "
        "(mapping, stocks, file, picking, lots RIP, pose, QC)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            default="staff.ops@prenium.local",
            help="Compte staff utilisé pour créer le seed (défaut: staff.ops@prenium.local).",
        )

    def handle(self, *args, **options):
        email = options["email"]
        actor = get_user_model().objects.filter(email=email, is_staff=True).first()
        if actor is None:
            raise CommandError(
                f"Compte staff introuvable: {email}. Lancez d'abord seed_sprint09_recipe."
            )
        self._ensure_seed_permissions(actor)
        customer = None
        from apps.pod.models import ShopifyStore

        demo_store = ShopifyStore.objects.filter(slug="demo-boutique").select_related("customer").first()
        if demo_store is not None and demo_store.customer_id:
            customer = demo_store.customer
        if customer is None:
            customer = (
                Customer.objects.filter(name="Seed Client A").first()
                or Customer.objects.filter(name__icontains="démo").first()
                or Customer.objects.filter(name__icontains="demo").first()
            )
        try:
            result = PodOpsBootstrapService().ensure_ready(actor=actor, customer=customer)
        except Exception as exc:  # noqa: BLE001 - surface seed diagnostics clearly
            raise CommandError(str(exc)) from exc
        if result["drive_hd_file"] is None:
            raise CommandError(
                "Aucun fichier dans GOOGLE_DRIVE_POD_HD_SOURCE_FOLDER_ID. "
                "Placez le PDF HD source puis relancez seed_pod_wms."
            )

        drive = result["drive_hd_file"]
        pipeline = result["pipeline"]
        self.stdout.write(self.style.SUCCESS("Seed POD WMS prêt."))
        self.stdout.write(f"- Drive HD : {drive['name']}")
        self.stdout.write(f"- Variante POD : {result['shopify_variant'].sku}")
        self.stdout.write(f"- Support : {result['blank_variant'].sku}")
        self.stdout.write(f"- File À produire : {pipeline['queue_order']}")
        self.stdout.write(f"- Session picking : {pipeline['pick_session'] or 'déjà créée'}")
        self.stdout.write(
            f"- Pose (waiting_press) : {', '.join(pipeline['pose_units']) or '—'}"
        )
        self.stdout.write(f"- QC (pressed) : {', '.join(pipeline['qc_units']) or '—'}")
        self.stdout.write(
            "Parcours : Suivi → À produire → Pose → Contrôle qualité → Stocks."
        )

    def _ensure_seed_permissions(self, actor) -> None:
        specs = (
            ("accounts", "access_staff_portal"),
            ("pod", "access_pod_atelier"),
            ("pod", "manage_pod_catalog"),
            ("pod", "operate_pod_production"),
            ("inventory", "manage_warehouse"),
            ("customers", "view_customer"),
        )
        missing = []
        for app_label, codename in specs:
            if actor.has_perm(f"{app_label}.{codename}"):
                continue
            permission = Permission.objects.filter(
                content_type__app_label=app_label,
                codename=codename,
            ).first()
            if permission is None:
                raise CommandError(
                    f"Permission manquante en base: {app_label}.{codename}. "
                    "Appliquez les migrations POD."
                )
            missing.append(permission)
        if missing:
            actor.user_permissions.add(*missing)
