from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import CatalogService
from apps.customers.models import Customer, CustomerBillingProfile, CustomerMembership
from apps.orders.models import Order
from apps.orders.services.orders import OrderService
from apps.orders.services.pricing import OrderPricingService
from apps.production.models import ProductionJob
from apps.production.services.workflow import ProductionWorkflowService
from apps.shipping.models import Shipment
from apps.uploads.models import OrderDriveFolder, OrderUpload, OrderUploadDriveSync
from apps.uploads.services.inspections import OrderUploadInspectionService

MINIMAL_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0bIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xa6\x1d\xc9"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)

order_service = OrderService()
order_pricing_service = OrderPricingService()


@dataclass(frozen=True)
class SeedUsers:
    admin: object
    staff_ops: object
    staff_limited: object
    client_a_owner: object
    client_a_member: object
    client_b_owner: object
    hybrid: object


class Command(BaseCommand):
    help = (
        "Données de démo recette — alignées B2B "
        "(facturation différée, profils client, tarification serveur). "
        "Mots de passe : voir docs/ACCES_RECETTE_PORTAIL.md"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Supprime les données seed existantes avant régénération.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            self._reset_seed_data()

        users = self._seed_users()
        customer_a, customer_b = self._seed_customers_and_memberships(users)
        self._seed_customer_billing_profiles(customer_a, customer_b)
        self._seed_catalog_services()
        orders = self._seed_b2b_orders(users, customer_a, customer_b)
        self._seed_uploads_inspections_drive(users, orders)
        self._seed_shipments(users, orders)

        self.stdout.write(
            self.style.SUCCESS("Seed recette B2B généré (facturation différée + workflow).")
        )
        self.stdout.write("")
        self.stdout.write(
            "Identifiants : voir docs/ACCES_RECETTE_PORTAIL.md (mot de passe commun seed)."
        )
        self.stdout.write("")
        self.stdout.write("Scénarios commandes (customer_note) :")
        self.stdout.write("- SEED09:A_B2B_DRAFT — brouillon + fichier")
        self.stdout.write(
            "- SEED09:A_B2B_SUBMITTED — soumise, fichiers variés, Drive, tarif en attente"
        )
        self.stdout.write("- SEED09:A_B2B_PRICED — tarifée (métrage commande)")
        self.stdout.write(
            "- SEED09:A_B2B_IN_PRODUCTION / READY_SHIP / SHIPPED / SHIPPING_FAILED — chaîne GPAO"
        )
        self.stdout.write("- SEED09:B_B2B_1 / SEED09:B_B2B_BLOCKED — client B (isolation)")

    def _reset_seed_data(self):
        user_model = get_user_model()
        seed_emails = [
            "admin@prenium.local",
            "staff.ops@prenium.local",
            "staff.limited@prenium.local",
            "client.a.owner@prenium.local",
            "client.a.member@prenium.local",
            "client.b.owner@prenium.local",
            "hybrid.ops.client@prenium.local",
        ]
        Customer.objects.filter(name__startswith="Seed ").delete()
        CatalogService.objects.filter(code__startswith="seed-").delete()
        user_model.objects.filter(email__in=seed_emails).delete()

    def _seed_users(self) -> SeedUsers:
        user_model = get_user_model()

        admin, _ = user_model.objects.get_or_create(
            email="admin@prenium.local",
            defaults={
                "is_superuser": True,
                "is_staff": True,
                "is_active": True,
                "staff_mfa_required": True,
                "staff_mfa_enabled": True,
            },
        )
        admin.is_superuser = True
        admin.is_staff = True
        admin.is_active = True
        admin.staff_mfa_required = True
        admin.staff_mfa_enabled = True
        admin.set_password("pass1234")
        admin.save()

        staff_ops, _ = user_model.objects.get_or_create(
            email="staff.ops@prenium.local",
            defaults={"is_staff": True, "is_active": True},
        )
        staff_ops.is_staff = True
        staff_ops.is_active = True
        staff_ops.staff_mfa_required = True
        staff_ops.staff_mfa_enabled = True
        staff_ops.set_password("pass1234")
        staff_ops.save()

        staff_limited, _ = user_model.objects.get_or_create(
            email="staff.limited@prenium.local",
            defaults={"is_staff": True, "is_active": True},
        )
        staff_limited.is_staff = True
        staff_limited.is_active = True
        staff_limited.staff_mfa_required = True
        staff_limited.staff_mfa_enabled = False
        staff_limited.set_password("pass1234")
        staff_limited.save()

        client_a_owner, _ = user_model.objects.get_or_create(
            email="client.a.owner@prenium.local",
            defaults={"is_active": True},
        )
        client_a_owner.set_password("pass1234")
        client_a_owner.save()

        client_a_member, _ = user_model.objects.get_or_create(
            email="client.a.member@prenium.local",
            defaults={"is_active": True},
        )
        client_a_member.set_password("pass1234")
        client_a_member.save()

        client_b_owner, _ = user_model.objects.get_or_create(
            email="client.b.owner@prenium.local",
            defaults={"is_active": True},
        )
        client_b_owner.set_password("pass1234")
        client_b_owner.save()

        hybrid, _ = user_model.objects.get_or_create(
            email="hybrid.ops.client@prenium.local",
            defaults={"is_staff": True, "is_active": True},
        )
        hybrid.is_staff = True
        hybrid.is_active = True
        hybrid.staff_mfa_required = True
        hybrid.staff_mfa_enabled = True
        hybrid.set_password("pass1234")
        hybrid.save()

        self._assign_permissions(staff_ops, self._staff_ops_permissions())
        self._assign_permissions(
            staff_limited, ["accounts.access_staff_portal", "orders.view_order"]
        )
        self._assign_permissions(hybrid, ["accounts.access_staff_portal", "orders.view_order"])

        return SeedUsers(
            admin=admin,
            staff_ops=staff_ops,
            staff_limited=staff_limited,
            client_a_owner=client_a_owner,
            client_a_member=client_a_member,
            client_b_owner=client_b_owner,
            hybrid=hybrid,
        )

    def _assign_permissions(self, user, permission_names: list[str]):
        permissions = []
        for name in permission_names:
            app_label, codename = name.split(".")
            permissions.append(
                Permission.objects.get(codename=codename, content_type__app_label=app_label)
            )
        user.user_permissions.set(permissions)

    def _staff_ops_permissions(self) -> list[str]:
        """Couvre fiche commande staff : fichiers, production, scan, expédition,
        facturation, tarif.
        """
        return [
            "accounts.access_staff_portal",
            "notifications.view_emailtemplate",
            "notifications.change_emailtemplate",
            "catalog.view_catalogservice",
            "orders.view_order",
            "orders.change_order",
            "uploads.view_orderupload",
            "uploads.view_orderuploadinspection",
            "uploads.review_orderupload",
            "uploads.view_orderuploaddrivesync",
            "production.view_productionjob",
            "production.transition_productionjob",
            "production.scan_productionjob",
            "production.scan_transition_productionjob",
            "shipping.view_shipment",
            "shipping.create_shipment",
            "billing.view_payment",
            "billing.view_invoice",
            "billing.mark_invoice_paid",
        ]

    def _seed_customers_and_memberships(self, users: SeedUsers):
        customer_a, _ = Customer.objects.get_or_create(
            name="Seed Client A",
            defaults={"billing_email": "billing.a@prenium.local", "is_active": True},
        )
        customer_b, _ = Customer.objects.get_or_create(
            name="Seed Client B",
            defaults={"billing_email": "billing.b@prenium.local", "is_active": True},
        )

        CustomerMembership.objects.update_or_create(
            customer=customer_a,
            user=users.client_a_owner,
            defaults={"role": CustomerMembership.Role.OWNER, "is_active": True},
        )
        CustomerMembership.objects.update_or_create(
            customer=customer_a,
            user=users.client_a_member,
            defaults={"role": CustomerMembership.Role.MEMBER, "is_active": True},
        )
        CustomerMembership.objects.update_or_create(
            customer=customer_b,
            user=users.client_b_owner,
            defaults={"role": CustomerMembership.Role.OWNER, "is_active": True},
        )
        CustomerMembership.objects.update_or_create(
            customer=customer_a,
            user=users.hybrid,
            defaults={"role": CustomerMembership.Role.MEMBER, "is_active": True},
        )
        return customer_a, customer_b

    def _seed_customer_billing_profiles(self, customer_a: Customer, customer_b: Customer):
        CustomerBillingProfile.objects.update_or_create(
            customer=customer_a,
            defaults={
                "billing_cycle": CustomerBillingProfile.BillingCycle.MONTHLY,
                "price_per_sqm_eur": Decimal("25.00"),
                "credit_limit_eur": Decimal("5000.00"),
                "enforce_credit_block": False,
            },
        )
        CustomerBillingProfile.objects.update_or_create(
            customer=customer_b,
            defaults={
                "billing_cycle": CustomerBillingProfile.BillingCycle.BI_MONTHLY,
                "price_per_sqm_eur": None,
                "credit_limit_eur": Decimal("1500.00"),
                "enforce_credit_block": True,
            },
        )

    def _seed_catalog_services(self):
        CatalogService.objects.update_or_create(
            code="seed-dtf-meter",
            defaults={
                "name": "Seed DTF au metre",
                "description": "Service DTF seed — grille recette",
                "service_type": CatalogService.ServiceType.DTF_TRANSFER,
                "unit": CatalogService.Unit.LINEAR_METER,
                "base_price": Decimal("25.00"),
                "currency": "EUR",
                "display_order": 1,
                "is_active": True,
            },
        )
        CatalogService.objects.update_or_create(
            code="seed-file-prep",
            defaults={
                "name": "Seed Preparation fichier",
                "description": "Service seed — optionnel",
                "service_type": CatalogService.ServiceType.FILE_PREPARATION,
                "unit": CatalogService.Unit.FIXED,
                "base_price": Decimal("10.00"),
                "currency": "EUR",
                "display_order": 2,
                "is_active": True,
            },
        )

    def _ensure_b2b_order(self, *, customer: Customer, actor, note: str) -> Order:
        existing = Order.objects.filter(customer=customer, customer_note=note).first()
        if existing:
            return existing
        return order_service.create_b2b_deferred_order(
            customer=customer,
            actor=actor,
            customer_note=note,
            source="seed_recipe",
        )

    def _submit_b2b(self, *, customer: Customer, actor, order: Order) -> Order:
        if order.status != Order.Status.DRAFT:
            return order
        return order_service.submit_b2b_deferred_order(
            customer=customer,
            actor=actor,
            order_public_id=order.public_id,
            source="seed_recipe",
        )

    def _price_order_with_linear(self, order: Order, actor, linear_m: Decimal):
        """Métrage linéaire commande + calcul prix serveur (cohérent workflow B2B)."""
        Order.objects.filter(pk=order.pk).update(meterage_override_linear_m=linear_m)
        order.refresh_from_db()
        order_pricing_service.compute_and_persist_order_pricing(
            order=order,
            actor=actor,
            source="seed_recipe",
        )
        order.refresh_from_db()

    def _seed_b2b_orders(
        self,
        users: SeedUsers,
        customer_a: Customer,
        customer_b: Customer,
    ) -> dict[str, Order]:
        orders: dict[str, Order] = {}

        # Brouillon + fichier (soumission manuelle en recette possible)
        orders["a_b2b_draft"] = self._ensure_b2b_order(
            customer=customer_a,
            actor=users.client_a_owner,
            note="SEED09:A_B2B_DRAFT",
        )
        self._upsert_upload(
            order=orders["a_b2b_draft"],
            actor=users.client_a_owner,
            filename="seed-draft-only.png",
            mime_type="image/png",
            content=MINIMAL_PNG_BYTES,
        )

        # Soumise — scénario riche (fichiers + états variés), tarif en attente
        o_sub = self._ensure_b2b_order(
            customer=customer_a,
            actor=users.client_a_owner,
            note="SEED09:A_B2B_SUBMITTED",
        )
        self._upsert_upload(
            order=o_sub,
            actor=users.client_a_owner,
            filename="seed-valid-image.png",
            mime_type="image/png",
            content=MINIMAL_PNG_BYTES,
        )
        self._upsert_upload(
            order=o_sub,
            actor=users.client_a_owner,
            filename="seed-valid-proof.pdf",
            mime_type="application/pdf",
            content=b"%PDF-1.4 seed\n%%EOF",
        )
        self._upsert_upload(
            order=o_sub,
            actor=users.client_a_member,
            filename="seed-warning.bin",
            mime_type="application/octet-stream",
            content=b"\x00\x01\x02\x03",
        )
        self._upsert_upload(
            order=o_sub,
            actor=users.client_a_member,
            filename="seed-error-image.png",
            mime_type="image/png",
            content=b"not-a-real-png",
        )
        orders["a_b2b_submitted"] = self._submit_b2b(
            customer=customer_a, actor=users.client_a_owner, order=o_sub
        )

        def _priced(note: str, linear: Decimal) -> Order:
            o = self._ensure_b2b_order(customer=customer_a, actor=users.client_a_owner, note=note)
            self._upsert_upload(
                order=o,
                actor=users.client_a_owner,
                filename="seed-price-base.png",
                mime_type="image/png",
                content=MINIMAL_PNG_BYTES,
            )
            o = self._submit_b2b(customer=customer_a, actor=users.client_a_owner, order=o)
            self._price_order_with_linear(o, users.staff_ops, linear)
            return o

        orders["a_b2b_priced"] = _priced("SEED09:A_B2B_PRICED", Decimal("2.5000"))
        orders["a_b2b_in_production"] = _priced("SEED09:A_B2B_IN_PRODUCTION", Decimal("3.0000"))
        orders["a_b2b_ready_ship"] = _priced("SEED09:A_B2B_READY_SHIP", Decimal("3.5000"))
        orders["a_b2b_shipped"] = _priced("SEED09:A_B2B_SHIPPED", Decimal("2.2000"))
        orders["a_b2b_shipping_failed"] = _priced("SEED09:A_B2B_SHIPPING_FAILED", Decimal("1.8000"))

        self._set_production_status(
            orders["a_b2b_in_production"], ProductionJob.Status.IN_PROGRESS, users.staff_ops
        )
        self._set_production_status(
            orders["a_b2b_ready_ship"], ProductionJob.Status.READY_TO_SHIP, users.staff_ops
        )
        self._set_production_status(
            orders["a_b2b_shipped"], ProductionJob.Status.COMPLETED, users.staff_ops
        )
        self._set_production_status(
            orders["a_b2b_shipping_failed"], ProductionJob.Status.READY_TO_SHIP, users.staff_ops
        )

        # Client B — isolation + OF bloqué
        o_b1 = self._ensure_b2b_order(
            customer=customer_b,
            actor=users.client_b_owner,
            note="SEED09:B_B2B_1",
        )
        self._upsert_upload(
            order=o_b1,
            actor=users.client_b_owner,
            filename="seed-client-b.png",
            mime_type="image/png",
            content=MINIMAL_PNG_BYTES,
        )
        orders["b_b2b_1"] = self._submit_b2b(
            customer=customer_b, actor=users.client_b_owner, order=o_b1
        )

        o_bb = self._ensure_b2b_order(
            customer=customer_b,
            actor=users.client_b_owner,
            note="SEED09:B_B2B_BLOCKED",
        )
        self._upsert_upload(
            order=o_bb,
            actor=users.client_b_owner,
            filename="seed-client-b-blocked.png",
            mime_type="image/png",
            content=MINIMAL_PNG_BYTES,
        )
        o_bb = self._submit_b2b(customer=customer_b, actor=users.client_b_owner, order=o_bb)
        self._set_production_status(o_bb, ProductionJob.Status.BLOCKED, users.staff_ops)
        orders["b_b2b_blocked"] = o_bb

        return orders

    def _set_production_status(self, order: Order, target_status: str, actor):
        workflow = ProductionWorkflowService()
        job = workflow.get_or_create_for_order(order=order)
        if job.status == target_status:
            return

        transition_paths = {
            ProductionJob.Status.QUEUED: [],
            ProductionJob.Status.IN_PROGRESS: [ProductionJob.Status.IN_PROGRESS],
            ProductionJob.Status.READY_TO_SHIP: [
                ProductionJob.Status.IN_PROGRESS,
                ProductionJob.Status.READY_TO_SHIP,
            ],
            ProductionJob.Status.BLOCKED: [ProductionJob.Status.BLOCKED],
            ProductionJob.Status.COMPLETED: [
                ProductionJob.Status.IN_PROGRESS,
                ProductionJob.Status.READY_TO_SHIP,
                ProductionJob.Status.COMPLETED,
            ],
        }
        if job.status != ProductionJob.Status.QUEUED:
            job.status = target_status
            job.last_transition_by = actor
            job.last_transition_at = timezone.now()
            if target_status == ProductionJob.Status.IN_PROGRESS and job.started_at is None:
                job.started_at = timezone.now()
            if target_status == ProductionJob.Status.COMPLETED and job.completed_at is None:
                job.completed_at = timezone.now()
            job.save()
            return

        for to_status in transition_paths[target_status]:
            workflow.transition_job(
                order_public_id=order.public_id,
                to_status=to_status,
                actor=actor,
                source="seed_recipe",
                reason=f"Seed status -> {to_status}",
            )

    def _seed_uploads_inspections_drive(self, users: SeedUsers, orders: dict[str, Order]):
        inspection_service = OrderUploadInspectionService()

        o_sub = orders["a_b2b_submitted"]
        uploads_to_inspect = list(o_sub.uploads.all())
        for upload in uploads_to_inspect:
            inspection_service.inspect_upload(
                order_upload=upload,
                actor=users.staff_ops,
                source="seed_recipe",
            )

        drive_folder = self._upsert_drive_folder(o_sub)
        upload_png = o_sub.uploads.filter(original_filename="seed-valid-image.png").first()
        upload_pdf = o_sub.uploads.filter(original_filename="seed-valid-proof.pdf").first()
        upload_warn = o_sub.uploads.filter(original_filename="seed-warning.bin").first()
        if upload_png:
            self._upsert_drive_sync(
                upload_png,
                drive_folder=drive_folder,
                status=OrderUploadDriveSync.Status.PENDING,
            )
        if upload_pdf:
            self._upsert_drive_sync(
                upload_pdf,
                drive_folder=drive_folder,
                status=OrderUploadDriveSync.Status.SYNCED,
                drive_file_id="seed-drive-file-synced",
            )
        if upload_warn:
            self._upsert_drive_sync(
                upload_warn,
                drive_folder=drive_folder,
                status=OrderUploadDriveSync.Status.FAILED,
                last_error="Simulated Drive sync failure for recipe.",
            )

    def _upsert_upload(self, *, order, actor, filename: str, mime_type: str, content: bytes):
        upload = (
            OrderUpload.objects.select_related("order")
            .filter(order=order, original_filename=filename)
            .first()
        )
        if upload is None:
            upload = OrderUpload(
                order=order,
                uploaded_by=actor,
                original_filename=filename,
                mime_type=mime_type,
                size_bytes=len(content),
            )
            upload.file.save(filename, ContentFile(content), save=False)
            upload.save()
        return upload

    def _upsert_drive_folder(self, order: Order):
        return OrderDriveFolder.objects.update_or_create(
            order=order,
            defaults={
                "shared_drive_id": "seed-shared-drive",
                "relative_path": f"Commandes/SEED/{order.public_id}",
                "order_folder_id": f"seed-folder-{str(order.public_id)[:8]}",
                "folder_ids": {
                    "00_source_client": f"seed-src-{str(order.public_id)[:8]}",
                    "01_controle": f"seed-ctrl-{str(order.public_id)[:8]}",
                    "04_shipping": f"seed-ship-{str(order.public_id)[:8]}",
                },
            },
        )[0]

    def _upsert_drive_sync(
        self,
        upload: OrderUpload,
        *,
        drive_folder: OrderDriveFolder,
        status: str,
        drive_file_id: str = "",
        last_error: str = "",
    ):
        defaults = {
            "drive_folder": drive_folder,
            "status": status,
            "drive_filename": upload.original_filename,
            "remote_folder_id": drive_folder.folder_ids.get("00_source_client", ""),
            "drive_file_id": drive_file_id,
            "last_error": last_error,
            "last_attempt_at": timezone.now(),
            "synced_at": timezone.now() if status == OrderUploadDriveSync.Status.SYNCED else None,
            "attempt_count": 1,
        }
        OrderUploadDriveSync.objects.update_or_create(order_upload=upload, defaults=defaults)

    def _seed_shipments(self, users: SeedUsers, orders: dict[str, Order]):
        created_order = orders["a_b2b_shipped"]
        failed_order = orders["a_b2b_shipping_failed"]

        created_shipment, _ = Shipment.objects.update_or_create(
            order=created_order,
            defaults={
                "created_by": users.staff_ops,
                "updated_by": users.staff_ops,
                "status": Shipment.Status.CREATED,
                "sendcloud_shipment_id": "seed-sc-shipment-created",
                "sendcloud_parcel_id": "seed-sc-parcel-created",
                "sendcloud_status_code": "READY_TO_SEND",
                "sendcloud_status_message": "Ready to send",
                "shipping_option_code": "seed:standard",
                "contract_id": 517,
                "tracking_number": "SEEDTRACK123",
                "tracking_url": "https://tracking.seed.local/SEEDTRACK123",
                "label_filename": f"{created_order.public_id}-seed-label.pdf",
                "label_mime_type": "application/pdf",
                "label_retrieved_at": timezone.now(),
                "last_api_sync_at": timezone.now(),
                "last_error_message": "",
                "source": "seed_recipe",
                "request_snapshot": {
                    "shipping_option_code": "seed:standard",
                    "recipient": {"name": "Seed Client A"},
                    "parcel": {"weight": {"value": "1.200", "unit": "kg"}},
                },
            },
        )
        if not created_shipment.label_file:
            created_shipment.label_file.save(
                created_shipment.label_filename,
                ContentFile(b"%PDF-1.4 seed shipment label\n%%EOF"),
                save=True,
            )

        Shipment.objects.update_or_create(
            order=failed_order,
            defaults={
                "created_by": users.staff_ops,
                "updated_by": users.staff_ops,
                "status": Shipment.Status.FAILED,
                "sendcloud_shipment_id": "",
                "sendcloud_parcel_id": "",
                "sendcloud_status_code": "ERROR",
                "sendcloud_status_message": "Carrier unavailable",
                "shipping_option_code": "seed:standard",
                "contract_id": 517,
                "tracking_number": "",
                "tracking_url": "",
                "label_filename": "",
                "label_mime_type": "",
                "label_retrieved_at": None,
                "last_api_sync_at": timezone.now(),
                "last_error_message": "Simulated Sendcloud failure for recipe.",
                "source": "seed_recipe",
                "request_snapshot": {
                    "shipping_option_code": "seed:standard",
                    "recipient": {"name": "Seed Client A"},
                    "parcel": {"weight": {"value": "0.900", "unit": "kg"}},
                },
            },
        )
