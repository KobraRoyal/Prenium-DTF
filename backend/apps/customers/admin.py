from django.contrib import admin

from apps.auditlog.admin import AdminAuditMixin

from .models import Customer, CustomerBillingProfile, CustomerMembership


class CustomerBillingProfileInline(admin.StackedInline):
    model = CustomerBillingProfile
    extra = 0


@admin.register(Customer)
class CustomerAdmin(AdminAuditMixin, admin.ModelAdmin):
    audit_create_action = "admin.customer.created"
    audit_update_action = "admin.customer.updated"
    audit_delete_action = "admin.customer.deleted"
    audit_fields = (
        "name",
        "billing_email",
        "is_active",
        "default_shipping_mode",
        "preferred_settlement_method",
        "negotiated_file_preparation_fee_eur",
        "billing_city",
        "shipping_city",
    )
    list_display = (
        "name",
        "billing_email",
        "default_shipping_mode",
        "preferred_settlement_method",
        "is_active",
    )
    readonly_fields = ("public_id", "created_at", "updated_at")
    search_fields = ("name", "billing_email", "billing_city", "shipping_city")
    inlines = (CustomerBillingProfileInline,)
    fieldsets = (
        (None, {"fields": ("name", "billing_email", "is_active", "notes")}),
        (
            "Adresse de facturation",
            {
                "fields": (
                    "billing_address_line1",
                    "billing_address_line2",
                    "billing_postal_code",
                    "billing_city",
                    "billing_country",
                )
            },
        ),
        (
            "Adresse de livraison (réf. expédition par défaut)",
            {
                "fields": (
                    "shipping_address_line1",
                    "shipping_address_line2",
                    "shipping_postal_code",
                    "shipping_city",
                    "shipping_country",
                )
            },
        ),
        (
            "Logistique & tarification fichier",
            {
                "fields": (
                    "default_shipping_mode",
                    "negotiated_file_preparation_fee_eur",
                ),
                "description": (
                    "Mode d’acheminement par défaut (retrait / expédition / livraison directe). "
                    "Forfait « préparation fichier » : vide = prix du catalogue "
                    "(ex. 10 € par fichier)."
                ),
            },
        ),
        (
            "Règlement",
            {
                "fields": ("preferred_settlement_method",),
                "description": (
                    "PayPal (flux en ligne) ou virement — indique comment le client "
                    "règle habituellement ses factures."
                ),
            },
        ),
    )


@admin.register(CustomerMembership)
class CustomerMembershipAdmin(AdminAuditMixin, admin.ModelAdmin):
    audit_create_action = "admin.customer_membership.created"
    audit_update_action = "admin.customer_membership.updated"
    audit_delete_action = "admin.customer_membership.deleted"
    audit_fields = ("customer", "user", "role", "is_active")
    list_display = ("customer", "user", "role", "is_active")
    readonly_fields = ("public_id", "created_at", "updated_at")
    list_filter = ("role", "is_active")
    search_fields = ("customer__name", "user__email")
    autocomplete_fields = ("customer", "user")
