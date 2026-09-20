"""Clients exclus des KPI / tendances du dashboard Atelier (comptes de recette)."""

from __future__ import annotations

from django.conf import settings
from django.db.models import Q, QuerySet

from apps.customers.models import Customer


def excluded_dashboard_customer_ids() -> frozenset[int]:
    emails = tuple(
        email.strip().lower()
        for email in getattr(settings, "DASHBOARD_EXCLUDED_CUSTOMER_EMAILS", ())
        if email and email.strip()
    )
    names = tuple(
        name.strip()
        for name in getattr(settings, "DASHBOARD_EXCLUDED_CUSTOMER_NAMES", ())
        if name and name.strip()
    )
    if not emails and not names:
        return frozenset()

    query = Q()
    if names:
        query |= Q(name__in=names)
    for email in emails:
        query |= Q(billing_email__iexact=email)
        query |= Q(memberships__user__email__iexact=email)
    return frozenset(
        Customer.objects.filter(query).values_list("pk", flat=True).distinct()
    )


def exclude_dashboard_noise_orders(queryset: QuerySet) -> QuerySet:
    excluded = excluded_dashboard_customer_ids()
    if not excluded:
        return queryset
    return queryset.exclude(customer_id__in=excluded)


def exclude_dashboard_noise_jobs(queryset: QuerySet) -> QuerySet:
    excluded = excluded_dashboard_customer_ids()
    if not excluded:
        return queryset
    return queryset.exclude(order__customer_id__in=excluded)


def exclude_dashboard_noise_print_records(queryset: QuerySet) -> QuerySet:
    excluded = excluded_dashboard_customer_ids()
    if not excluded:
        return queryset
    return queryset.exclude(production_job__order__customer_id__in=excluded)
