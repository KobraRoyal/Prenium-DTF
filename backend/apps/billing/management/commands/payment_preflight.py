import ipaddress
from urllib import error, request
from urllib.parse import urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import Count, Exists, OuterRef, Q
from django.http.request import validate_host
from django.utils import timezone

from apps.auditlog.models import AuditLogEntry
from apps.billing.models import Payment
from apps.billing.services.gateway_settings import payment_gateway_settings_service
from apps.billing.services.gateways import PaymentGatewayError, open_provider_request
from apps.billing.services.payments import (
    STRIPE_FAILURE_RECONCILIATION_MESSAGE,
    UNKNOWN_CHECKOUT_RETRY_WINDOWS,
)
from apps.billing.services.paypal import PayPalGateway
from apps.billing.services.stripe_gateway import StripeGateway


def probe_public_webhook_route(url: str) -> bool:
    """Vérifie sans POST que le point d'entrée public accepte les webhooks."""
    http_request = request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with open_provider_request(http_request, timeout=10):
            return False
    except error.HTTPError as exc:
        allowed = {method.strip().upper() for method in exc.headers.get("Allow", "").split(",")}
        return exc.code == 405 and "POST" in allowed
    except (error.URLError, PaymentGatewayError, TimeoutError):
        return False


class Command(BaseCommand):
    help = "Vérifie la configuration et les données avant activation des paiements."

    def add_arguments(self, parser):
        parser.add_argument(
            "--live",
            action="store_true",
            help="Exige PayPal et Stripe en mode production avec webhooks et HTTPS.",
        )

    def handle(self, *args, **options):
        config = payment_gateway_settings_service.effective()
        live = options["live"]
        errors = []
        if live and not config.paypal_live:
            errors.append("PayPal n'est pas activé avec ses identifiants.")
        if live and not config.stripe_live:
            errors.append("Stripe n'est pas activé avec sa clé secrète.")
        if config.paypal_live:
            if not config.paypal_webhook_id:
                errors.append("PAYPAL_WEBHOOK_ID manque pour PayPal actif.")
            api_url = urlsplit(settings.PAYPAL_API_BASE_URL)
            if live and (api_url.scheme != "https" or api_url.hostname != "api-m.paypal.com"):
                errors.append("PAYPAL_API_BASE_URL doit être https://api-m.paypal.com en live.")
        if config.stripe_live:
            if not config.stripe_webhook_secret:
                errors.append("STRIPE_WEBHOOK_SECRET manque pour Stripe actif.")
            elif not str(config.stripe_webhook_secret).startswith("whsec_"):
                errors.append(
                    "Le secret webhook Stripe doit commencer par whsec_ (pas l'ID d'endpoint we_…)."
                )
            if live and not config.stripe_secret_key.startswith(("sk_live_", "rk_live_")):
                errors.append("La clé Stripe active n'est pas une clé live.")
            if live and str(settings.STRIPE_API_BASE_URL).rstrip("/") != "https://api.stripe.com":
                errors.append("STRIPE_API_BASE_URL doit être https://api.stripe.com en live.")
        if live:
            if (
                "billing",
                "0011_payment_single_payable_or_captured",
            ) not in MigrationRecorder(connection).applied_migrations():
                errors.append("Migration billing.0011 non appliquée sur cette base.")
            with connection.cursor() as cursor:
                unique_payment_index = connection.introspection.get_constraints(
                    cursor, Payment._meta.db_table
                ).get("uniq_payable_or_captured_payment_per_order")
            if not (
                unique_payment_index
                and unique_payment_index.get("unique")
                and unique_payment_index.get("columns") == ["order_id"]
            ):
                errors.append("Index unique des paiements actifs/capturés absent de la base.")
            try:
                public_url = urlsplit(settings.PUBLIC_BASE_URL)
                hostname = (public_url.hostname or "").lower().rstrip(".")
                public_port = public_url.port
            except ValueError:
                public_url = None
                hostname = ""
                public_port = -1
            try:
                address = ipaddress.ip_address(hostname)
            except ValueError:
                address = None
            if (
                public_url is None
                or public_url.scheme != "https"
                or not hostname
                or public_port not in (None, 443)
                or hostname == "localhost"
                or hostname.endswith((".localhost", ".local", ".internal", ".test", ".invalid"))
                or (address is not None and not address.is_global)
                or public_url.username is not None
                or public_url.password is not None
                or public_url.path.rstrip("/")
                or public_url.query
                or public_url.fragment
            ):
                errors.append("PUBLIC_BASE_URL doit être une URL HTTPS publique.")
            if "*" in settings.ALLOWED_HOSTS or not validate_host(hostname, settings.ALLOWED_HOSTS):
                errors.append(
                    "PUBLIC_BASE_URL doit figurer dans DJANGO_ALLOWED_HOSTS sans wildcard."
                )
        duplicate_orders = list(
            Payment.objects.filter(
                status__in=(
                    Payment.Status.PENDING,
                    Payment.Status.APPROVED,
                    Payment.Status.CAPTURED,
                )
            )
            .values("order_id")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
            .values_list("order_id", flat=True)[:20]
        )
        if duplicate_orders:
            errors.append(
                f"Paiements actifs ou capturés multiples sur commandes {duplicate_orders}; "
                "rapprochement et fermeture des sessions distantes requis."
            )
        unresolved_stripe_ids = list(
            Payment.objects.filter(
                provider=Payment.Provider.STRIPE,
                status__in=(Payment.Status.PENDING, Payment.Status.APPROVED),
                last_error_message=STRIPE_FAILURE_RECONCILIATION_MESSAGE,
            ).values_list("public_id", flat=True)[:20]
        )
        if unresolved_stripe_ids:
            errors.append(
                f"Échecs Stripe encore à rapprocher avant activation : {unresolved_stripe_ids}."
            )
        for provider, reference_field in (
            (Payment.Provider.STRIPE, "stripe_checkout_session_id"),
            (Payment.Provider.PAYPAL, "paypal_order_id"),
        ):
            stale_ids = list(
                Payment.objects.filter(
                    provider=provider,
                    status__in=(Payment.Status.PENDING, Payment.Status.APPROVED),
                    created_at__lt=timezone.now() - UNKNOWN_CHECKOUT_RETRY_WINDOWS[provider],
                    **{reference_field: ""},
                ).values_list("public_id", flat=True)[:20]
            )
            if stale_ids:
                errors.append(
                    f"Tentatives {provider} sans référence distante hors fenêtre "
                    f"d'idempotence : {stale_ids}. Rapprochement manuel requis."
                )
        if live and not errors:
            for label, gateway_type in (("PayPal", PayPalGateway), ("Stripe", StripeGateway)):
                try:
                    gateway_type().probe_readiness()
                except PaymentGatewayError as exc:
                    errors.append(f"{label} : vérification API échouée ({type(exc).__name__}).")
        if live and not errors:
            reconciled_unknown = AuditLogEntry.objects.filter(
                action="billing.unknown_checkout_manually_closed",
                status=AuditLogEntry.Status.SUCCESS,
                target_model="Payment",
                target_public_id=OuterRef("public_id"),
            )
            unknown_terminal = list(
                Payment.objects.filter(
                    status__in=(Payment.Status.FAILED, Payment.Status.CANCELLED),
                )
                .filter(
                    Q(provider=Payment.Provider.STRIPE, stripe_checkout_session_id="")
                    | Q(provider=Payment.Provider.PAYPAL, paypal_order_id="")
                )
                .annotate(_reconciled=Exists(reconciled_unknown))
                .filter(_reconciled=False)
                .values_list("public_id", flat=True)[:20]
            )
            if unknown_terminal:
                errors.append(
                    "Tentatives historiques fermées sans référence ni preuve de "
                    f"rapprochement : {unknown_terminal}."
                )
            stripe_gateway = StripeGateway()
            stripe_to_check = (
                Payment.objects.filter(
                    provider=Payment.Provider.STRIPE,
                    status__in=(
                        Payment.Status.PENDING,
                        Payment.Status.APPROVED,
                        Payment.Status.FAILED,
                        Payment.Status.CANCELLED,
                    ),
                )
                .select_related("order", "order__customer")
                .order_by("pk")
            )
            for payment in stripe_to_check.iterator(chunk_size=100):
                active = payment.status in (Payment.Status.PENDING, Payment.Status.APPROVED)
                if not payment.stripe_checkout_session_id:
                    if active:
                        errors.append(
                            f"Tentative Stripe {payment.public_id} sans référence distante "
                            "à rapprocher avant bascule."
                        )
                    continue
                try:
                    session = stripe_gateway.verify_checkout_binding(
                        provider_payment_id=payment.stripe_checkout_session_id,
                        payment_public_id=payment.public_id,
                        order_public_id=payment.order.public_id,
                        customer_public_id=payment.order.customer.public_id,
                        amount=payment.amount,
                        currency=payment.currency,
                        allow_legacy_missing_payment_id=True,
                    )
                except PaymentGatewayError as exc:
                    errors.append(
                        f"Tentative Stripe {payment.public_id} : lecture ou lien distant "
                        f"invalide ({type(exc).__name__})."
                    )
                    continue
                if not isinstance(session, dict):
                    errors.append(
                        f"Tentative Stripe {payment.public_id} : réponse distante invalide."
                    )
                    continue
                methods = session.get("payment_method_types")
                if active and methods != ["card"]:
                    errors.append(
                        f"Tentative Stripe {payment.public_id} avec moyens de paiement "
                        "historiques à rapprocher avant bascule."
                    )
                    continue
                expected_status = "open" if active else "expired"
                if (
                    session.get("status") != expected_status
                    or session.get("payment_status") != "unpaid"
                ):
                    errors.append(
                        f"Tentative Stripe {payment.public_id} avec état distant "
                        "à rapprocher avant bascule."
                    )
            paypal_gateway = PayPalGateway()
            paypal_to_check = (
                Payment.objects.filter(
                    provider=Payment.Provider.PAYPAL,
                    status__in=(
                        Payment.Status.PENDING,
                        Payment.Status.APPROVED,
                        Payment.Status.FAILED,
                        Payment.Status.CANCELLED,
                    ),
                )
                .select_related("order", "order__customer")
                .order_by("pk")
            )
            for payment in paypal_to_check.iterator(chunk_size=100):
                active = payment.status in (Payment.Status.PENDING, Payment.Status.APPROVED)
                if not payment.paypal_order_id:
                    if active:
                        errors.append(
                            f"Tentative PayPal {payment.public_id} sans référence distante "
                            "à rapprocher avant bascule."
                        )
                    continue
                try:
                    remote_order = paypal_gateway.verify_checkout_binding(
                        provider_payment_id=payment.paypal_order_id,
                        payment_public_id=payment.public_id,
                        order_public_id=payment.order.public_id,
                        amount=payment.amount,
                        currency=payment.currency,
                        allow_legacy_custom_id=True,
                    )
                except PaymentGatewayError as exc:
                    errors.append(
                        f"Tentative PayPal {payment.public_id} : lecture ou lien distant "
                        f"invalide ({type(exc).__name__})."
                    )
                    continue
                if not isinstance(remote_order, dict):
                    errors.append(
                        f"Tentative PayPal {payment.public_id} : réponse distante invalide."
                    )
                    continue
                remote_status = str(remote_order.get("status") or "").upper()
                allowed = (
                    {"CREATED", "SAVED", "PAYER_ACTION_REQUIRED", "APPROVED"}
                    if active
                    else {"VOIDED"}
                )
                if remote_status not in allowed:
                    errors.append(
                        f"Tentative PayPal {payment.public_id} avec état distant "
                        "à rapprocher avant bascule."
                    )
        if live and not errors:
            for label, url in payment_gateway_settings_service.webhook_urls().items():
                if not probe_public_webhook_route(url):
                    errors.append(f"Webhook {label} inaccessible ou route POST publique absente.")
        if errors:
            raise CommandError("Préflight paiements échoué : " + " ".join(errors))
        self.stdout.write(
            self.style.SUCCESS(
                "Préflight paiements réussi pour configuration, lecture API et routes publiques. "
                "Création, capture et livraison webhook restent à valider en conditions réelles."
            )
        )
