from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.billing.forms import PaymentGatewaySettingsForm
from apps.billing.services.gateway_settings import payment_gateway_settings_service
from apps.portal.htmx import with_toast
from apps.portal.views_common import StaffDomainPermissionMixin


class StaffPaymentSettingsView(StaffDomainPermissionMixin, View):
    required_permission = "billing.view_paymentgatewaysettings"
    template_name = "portal/staff/settings/payments.html"

    def _context(self, *, form, snapshot):
        return {
            "form": form,
            "snapshot": snapshot,
            "nav_mode": "staff",
            "nav_key": "staff-payment-settings",
            "can_change_payment_gateways": self.request.user.has_perm(
                "billing.change_paymentgatewaysettings"
            ),
        }

    def get(self, request):
        snapshot = payment_gateway_settings_service.snapshot()
        form = PaymentGatewaySettingsForm(snapshot=snapshot)
        return render(request, self.template_name, self._context(form=form, snapshot=snapshot))

    def post(self, request):
        if not request.user.has_perm("billing.change_paymentgatewaysettings"):
            raise PermissionDenied

        snapshot = payment_gateway_settings_service.snapshot()
        form = PaymentGatewaySettingsForm(request.POST, snapshot=snapshot)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                self._context(form=form, snapshot=snapshot),
                status=400,
            )
        try:
            payment_gateway_settings_service.update(
                paypal_enabled=form.cleaned_data["paypal_enabled"],
                stripe_enabled=form.cleaned_data["stripe_enabled"],
                paypal_client_id=form.cleaned_data["paypal_client_id"],
                paypal_client_secret=form.cleaned_data["paypal_client_secret"],
                paypal_webhook_id=form.cleaned_data["paypal_webhook_id"],
                stripe_publishable_key=form.cleaned_data["stripe_publishable_key"],
                stripe_secret_key=form.cleaned_data["stripe_secret_key"],
                stripe_webhook_secret=form.cleaned_data["stripe_webhook_secret"],
                actor=request.user,
                source="staff_payment_settings",
                ip_address=request.META.get("REMOTE_ADDR"),
            )
        except ImproperlyConfigured:
            form.add_error(
                None,
                "Chiffrement des secrets indisponible. Configurez "
                "PAYMENT_SECRET_ENCRYPTION_KEYS (ou WEB_PUSH_ENCRYPTION_KEYS) "
                "dans l’environnement serveur, puis redémarrez web/worker/beat.",
            )
            return render(
                request,
                self.template_name,
                self._context(form=form, snapshot=snapshot),
                status=503,
            )
        except ValidationError as error:
            messages = getattr(error, "message_dict", {}) or {}
            if not messages:
                form.add_error(None, error)
            for field, field_messages in messages.items():
                target = None if field in {"__all__", "non_field_errors"} else field
                if target is not None and target not in form.fields:
                    target = None
                for message in field_messages:
                    form.add_error(target, message)
            return render(
                request,
                self.template_name,
                self._context(form=form, snapshot=snapshot),
                status=400,
            )
        response = HttpResponseRedirect(reverse("portal:staff-payment-settings"))
        return with_toast(response, "Moyens de paiement enregistrés.", "success")
