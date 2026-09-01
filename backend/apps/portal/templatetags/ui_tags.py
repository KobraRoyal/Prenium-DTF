from urllib.parse import urlencode

from django import template
from django.urls import reverse

from apps.portal.order_status_presentation import prepare_orders_for_list

register = template.Library()


def _normalize_list_tabs(
    context,
    tabs,
    *,
    url_name=None,
    query_param="status",
    preserve_query=(),
    htmx_target=None,
    htmx_swap="outerHTML",
    htmx_push_url=True,
    htmx_indicator=None,
):
    request = context.get("request")
    normalized = []
    for tab in tabs or []:
        item = dict(tab)
        if "href" not in item and url_name:
            param_value = item.get("key", item.get("value"))
            params = {query_param: param_value}
            if request is not None:
                for param in preserve_query:
                    value = request.GET.get(param)
                    if value:
                        params[param] = value
            item["href"] = f"{reverse(url_name)}?{urlencode(params)}"
        if htmx_target and item.get("href"):
            item["htmx"] = {
                "get": item["href"],
                "target": htmx_target,
                "swap": htmx_swap,
                "push_url": htmx_push_url,
                "indicator": htmx_indicator,
            }
        if "count" in item and "is_empty" not in item:
            item["is_empty"] = not item["count"]
        normalized.append(item)
    return normalized


@register.inclusion_tag("components/ui/list_tabs.html", takes_context=True)
def ui_list_tabs(
    context,
    tabs,
    aria_label,
    element="link",
    url_name=None,
    query_param="status",
    preserve_query=None,
    extra_class="",
    htmx_target=None,
    htmx_swap="outerHTML",
    htmx_push_url=True,
    htmx_indicator=None,
):
    preserve = preserve_query or ()
    if isinstance(preserve, str):
        preserve = (preserve,)
    return {
        "tabs": _normalize_list_tabs(
            context,
            tabs,
            url_name=url_name,
            query_param=query_param,
            preserve_query=preserve,
            htmx_target=htmx_target,
            htmx_swap=htmx_swap,
            htmx_push_url=htmx_push_url,
            htmx_indicator=htmx_indicator,
        ),
        "aria_label": aria_label,
        "element": element,
        "extra_class": extra_class,
    }


@register.inclusion_tag("components/tables/kpi_grid.html")
def ui_kpi_grid(items):
    return {"items": items or []}


@register.inclusion_tag("components/tables/orders_table.html")
def ui_orders_table(orders, variant, customer=None):
    return {
        "orders": prepare_orders_for_list(orders),
        "variant": variant,
        "customer": customer,
    }


@register.inclusion_tag("components/tables/atelier_worklist_table.html")
def ui_atelier_worklist_table(rows):
    return {"rows": rows or []}


@register.inclusion_tag("components/tables/order_projects_table.html")
def ui_order_projects_table(projects, customer, show_delete=True):
    return {
        "projects": projects,
        "customer": customer,
        "show_delete": show_delete,
    }
