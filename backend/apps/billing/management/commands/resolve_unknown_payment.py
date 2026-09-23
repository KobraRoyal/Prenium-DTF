from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.billing.services.payments import PaymentService


class Command(BaseCommand):
    help = "Ferme une tentative sans référence après rapprochement externe documenté."

    def add_arguments(self, parser):
        parser.add_argument("payment_public_id")
        parser.add_argument(
            "--resolution",
            required=True,
            choices=("no_remote_checkout", "remote_closed"),
        )
        parser.add_argument("--evidence", required=True)
        parser.add_argument("--reason", required=True)

    def handle(self, *args, **options):
        try:
            payment = PaymentService().close_unknown_checkout_after_reconciliation(
                payment_public_id=options["payment_public_id"],
                actor=None,
                resolution=options["resolution"],
                evidence=options["evidence"],
                reason=options["reason"],
                management_command=True,
            )
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        self.stdout.write(self.style.SUCCESS(f"Tentative {payment.public_id} fermée après audit."))
