from django import template

register = template.Library()


@register.inclusion_tag("components/tables/kpi_grid.html")
def ui_kpi_grid(items):
    return {"items": items or []}


@register.inclusion_tag("components/tables/orders_table.html")
def ui_orders_table(orders, variant, customer=None):
    return {
        "orders": orders,
        "variant": variant,
        "customer": customer,
    }
