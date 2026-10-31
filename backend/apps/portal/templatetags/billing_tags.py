from django import template
from django.utils.formats import number_format

from apps.portal.services.billing_breakdown import (
    order_billing_breakdown,
)
from apps.portal.services.billing_breakdown import (
    order_vat_preview as vat_preview,
)

register = template.Library()


@register.filter
def billing_quantity(value):
    return number_format(value.normalize(), use_l10n=True)


@register.inclusion_tag("components/portal/order_billing_breakdown.html")
def billing_breakdown(order):
    return order_billing_breakdown(order)


@register.simple_tag
def order_vat_preview(order):
    return vat_preview(order)
