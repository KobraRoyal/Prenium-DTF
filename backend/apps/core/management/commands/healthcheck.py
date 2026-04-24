import json

from django.core.management.base import BaseCommand, CommandError

from apps.core.services.health import HealthcheckService


class Command(BaseCommand):
    help = "Runs application health checks."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Output JSON payload.")

    def handle(self, *args, **options):
        service = HealthcheckService()
        payload = service.get_payload()

        if options["json"]:
            self.stdout.write(json.dumps(payload))
        else:
            self.stdout.write(payload["status"])

        if payload["status"] != "ok":
            raise CommandError("Health checks failed.")
