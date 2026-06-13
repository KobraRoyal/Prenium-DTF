from django.contrib import admin, messages

from apps.auditlog.services import record_event

from .models import BillingStatement, Invoice, Payment


@admin.register(BillingStatement)
class BillingStatementAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "customer",
        "label",
        "period_start",
        "period_end",
        "status",
        "total_amount",
        "currency",
    )
    list_filter = ("status", "currency")
    search_fields = ("customer__name", "label")
    readonly_fields = ("public_id", "created_at", "updated_at")
    autocomplete_fields = ("customer",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "order",
        "provider",
        "status",
        "amount",
        "currency",
        "paypal_order_id",
        "paypal_capture_id",
        "created_by",
        "created_at",
    )
    list_filter = ("provider", "status", "currency", "created_at")
    search_fields = (
        "order__public_id",
        "order__customer__name",
        "paypal_order_id",
        "paypal_capture_id",
    )
    readonly_fields = (
        "public_id",
        "order",
        "created_by",
        "provider",
        "status",
        "amount",
        "currency",
        "paypal_order_id",
        "paypal_capture_id",
        "approval_url",
        "source",
        "request_snapshot",
        "provider_payload",
        "captured_at",
        "last_error_message",
        "created_at",
        "updated_at",
    )
    fields = readonly_fields
    autocomplete_fields = ("order", "created_by")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "order",
        "invoice_number",
        "status",
        "total_amount",
        "currency",
        "billing_email",
        "issued_at",
        "paid_at",
    )
    list_filter = ("status", "currency", "issued_at")
    search_fields = (
        "invoice_number",
        "order__public_id",
        "order__customer__name",
        "billing_email",
    )
    readonly_fields = (
        "public_id",
        "order",
        "payment",
        "status",
        "invoice_number",
        "subtotal_amount",
        "total_amount",
        "currency",
        "billing_name",
        "billing_email",
        "file",
        "file_name",
        "file_mime_type",
        "source",
        "snapshot",
        "issued_at",
        "paid_recorded_by",
        "created_at",
        "updated_at",
    )
    fields = readonly_fields + ("paid_at",)
    autocomplete_fields = ("order", "payment")
    actions = ("mark_selected_invoices_paid",)

    @admin.action(description="Marquer comme payées (virement reçu)")
    def mark_selected_invoices_paid(self, request, queryset):
        if not request.user.has_perm("billing.mark_invoice_paid"):
            self.message_user(
                request,
                "Permission « marquer facture payée » requise.",
                level=messages.ERROR,
            )
            return
        from apps.billing.services.invoices import InvoiceService

        svc = InvoiceService()
        n = 0
        for invoice in queryset.select_related("order"):
            if invoice.paid_at is not None:
                continue
            svc.mark_invoice_paid_by_staff(
                invoice=invoice,
                actor=request.user,
                source="django_admin.action",
            )
            n += 1
        self.message_user(request, f"{n} facture(s) marquée(s) comme payées.")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("billing.mark_invoice_paid")

    def save_model(self, request, obj, form, change):
        """Saisie manuelle de `paid_at` en admin : enregistre l’auteur."""
        if change and "paid_at" in form.changed_data and obj.paid_at is not None:
            obj.paid_recorded_by = request.user
        super().save_model(request, obj, form, change)
        if change and "paid_at" in form.changed_data and obj.paid_at is not None:
            record_event(
                action="billing.invoice_marked_paid",
                actor=request.user,
                target=obj,
                metadata={"source": "django_admin.invoice_paid_at_edit"},
            )
