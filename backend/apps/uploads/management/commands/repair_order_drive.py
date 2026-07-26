from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.orders.models import Order
from apps.uploads.models import OrderDriveFolder
from apps.uploads.services.drive import (
    GoogleDriveConfigurationError,
    GoogleDriveGateway,
    GoogleDriveSyncError,
    OrderDriveFolderService,
    repair_order_drive_sync,
)


class Command(BaseCommand):
    help = (
        "Recrée les dossiers commande Drive trashés/manquants et re-synchronise "
        "les uploads + gang sheets depuis le stockage local."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--order",
            action="append",
            dest="orders",
            default=[],
            help="short_ref ou public_id commande (répétable). Défaut: dossiers trashés/manquants.",
        )
        parser.add_argument(
            "--all-mapped",
            action="store_true",
            help="Répare toutes les commandes ayant un OrderDriveFolder.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Liste les commandes concernées sans écrire sur Drive.",
        )

    def handle(self, *args, **options):
        try:
            gateway = GoogleDriveGateway()
        except GoogleDriveConfigurationError as error:
            raise CommandError(str(error)) from error

        orders = self._resolve_orders(
            gateway=gateway,
            order_refs=options["orders"],
            all_mapped=options["all_mapped"],
        )
        if not orders:
            self.stdout.write("Aucune commande à réparer.")
            return

        self.stdout.write(f"{len(orders)} commande(s) à réparer.")
        if options["dry_run"]:
            for order in orders:
                self.stdout.write(f"- {order.short_ref} ({order.customer.name})")
            return

        failures = 0
        for order in orders:
            try:
                result = repair_order_drive_sync(order=order, source="mgmt.repair_order_drive")
            except (GoogleDriveSyncError, GoogleDriveConfigurationError, OSError, KeyError) as error:
                failures += 1
                self.stderr.write(f"FAIL {order.short_ref}: {error}")
                continue

            upload_ok = sum(1 for row in result["uploads"] if row["status"] == "synced")
            gang_ok = sum(1 for row in result["gang_sheets"] if row["status"] == "synced")
            self.stdout.write(
                f"OK {order.short_ref} path={result['relative_path']} "
                f"uploads={upload_ok}/{len(result['uploads'])} "
                f"gangs={gang_ok}/{len(result['gang_sheets'])}"
            )
            for row in result["uploads"]:
                if row["status"] != "synced":
                    self.stderr.write(
                        f"  upload {row['order_upload_public_id']}: "
                        f"{row['status']} {row['last_error']}"
                    )
                    failures += 1
            for row in result["gang_sheets"]:
                if row["status"] != "synced":
                    self.stderr.write(
                        f"  gang {row['gang_sheet_public_id']}: "
                        f"{row['status']} {row['last_error']}"
                    )
                    failures += 1

        if failures:
            raise CommandError(f"Réparation terminée avec {failures} échec(s).")

    def _resolve_orders(self, *, gateway, order_refs, all_mapped):
        if order_refs:
            found = []
            for ref in order_refs:
                order = (
                    Order.objects.select_related("customer", "drive_folder")
                    .filter(Q(public_id=ref) | Q(public_id__startswith=ref))
                    .first()
                )
                if order is None:
                    # short_ref is derived; scan candidates
                    for candidate in Order.objects.select_related("customer", "drive_folder"):
                        if candidate.short_ref == ref or str(candidate.public_id).startswith(ref):
                            order = candidate
                            break
                if order is None:
                    raise CommandError(f"Commande introuvable: {ref}")
                found.append(order)
            return found

        folders = OrderDriveFolder.objects.select_related("order", "order__customer")
        if all_mapped:
            return [folder.order for folder in folders]

        folder_service = OrderDriveFolderService(gateway=gateway)
        damaged = []
        for folder in folders:
            if not folder_service._remote_order_tree_is_active(
                gateway=gateway,
                drive_folder=folder,
            ):
                damaged.append(folder.order)
        return damaged
