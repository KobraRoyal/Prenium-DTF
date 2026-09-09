import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from apps.accounts.models import StaffMembership
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse


def _permission(app_label, codename):
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def _staff_user(*, complete_permissions=True):
    user = get_user_model().objects.create_user(
        email=f"atelier-push-{uuid4()}@example.com",
        password="pass",
        is_staff=True,
    )
    StaffMembership.objects.create(user=user)
    user.user_permissions.add(_permission("accounts", "access_staff_portal"))
    if complete_permissions:
        user.user_permissions.add(
            _permission("orders", "view_order"),
            _permission("production", "view_productionjob"),
        )
    return user


def _endpoint_urls(subscription_public_id=None):
    subscription_public_id = subscription_public_id or uuid4()
    return (
        ("get", reverse("portal:staff-push-notification-state")),
        ("post", reverse("portal:staff-push-notification-subscribe")),
        (
            "post",
            reverse(
                "portal:staff-push-notification-unsubscribe",
                kwargs={"subscription_public_id": subscription_public_id},
            ),
        ),
        ("get", reverse("portal:staff-push-notification-events")),
    )


@pytest.mark.django_db
def test_staff_logout_revokes_all_push_subscriptions():
    user = _staff_user()
    client = Client()
    client.force_login(user)

    with patch(
        "apps.notifications.services.workshop_push.WorkshopNotificationService.unsubscribe_all"
    ) as unsubscribe_all:
        response = client.post(reverse("portal:logout"))

    assert response.status_code == 302
    assert response["Location"] == reverse("portal:login")
    unsubscribe_all.assert_called_once_with(actor=user, source="portal_logout")


@pytest.mark.django_db
@pytest.mark.parametrize("method,url", _endpoint_urls())
def test_push_endpoints_reject_anonymous_users(method, url):
    response = getattr(Client(), method)(url)

    assert response.status_code == 302
    assert reverse("portal:login") in response["Location"]


@pytest.mark.django_db
@pytest.mark.parametrize("method,url", _endpoint_urls())
def test_push_endpoints_reject_client_users(method, url):
    user = get_user_model().objects.create_user(
        email=f"client-push-{uuid4()}@example.com",
        password="pass",
    )
    client = Client()
    client.force_login(user)

    assert getattr(client, method)(url).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("method,url", _endpoint_urls())
def test_push_endpoints_require_both_workshop_domain_permissions(method, url):
    user = _staff_user(complete_permissions=False)
    client = Client()
    client.force_login(user)

    assert getattr(client, method)(url).status_code == 403


@pytest.mark.django_db
def test_push_state_returns_only_public_configuration():
    user = _staff_user()
    client = Client()
    client.force_login(user)
    state = SimpleNamespace(
        enabled=True,
        configured=True,
        vapid_public_key="public-vapid-key",
        subscriptions=(
            SimpleNamespace(public_id=str(uuid4()), last_seen_at="2026-09-08T12:00:00+00:00"),
        ),
    )

    with patch(
        "apps.portal.views_staff_push_notifications.workshop_notification_service.subscription_state",
        return_value=state,
    ) as subscription_state:
        response = client.get(reverse("portal:staff-push-notification-state"))

    assert response.status_code == 200
    assert response.json()["vapid_public_key"] == "public-vapid-key"
    assert set(response.json()) == {
        "ok",
        "enabled",
        "configured",
        "vapid_public_key",
        "subscriptions",
    }
    subscription_state.assert_called_once_with(actor=user)


@pytest.mark.django_db
def test_subscribe_is_csrf_protected_and_delegates_to_service():
    user = _staff_user()
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    subscribe_url = reverse("portal:staff-push-notification-subscribe")

    assert client.post(subscribe_url, data="{}", content_type="application/json").status_code == 403
    dashboard = client.get(reverse("portal:staff-dashboard"))
    csrf_token = client.cookies["csrftoken"].value
    subscription = SimpleNamespace(public_id=uuid4())
    payload = {
        "endpoint": "https://push.example.test/subscription",
        "p256dh": "browser-public-key",
        "auth": "browser-auth-secret",
    }
    with patch(
        "apps.portal.views_staff_push_notifications.workshop_notification_service.subscribe",
        return_value=subscription,
    ) as subscribe:
        response = client.post(
            subscribe_url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

    assert dashboard.status_code == 200
    assert response.status_code == 201
    assert response.json()["subscription"] == {"public_id": str(subscription.public_id)}
    subscribe.assert_called_once_with(actor=user, source="portal", **payload)


@pytest.mark.django_db
def test_push_mutation_routes_reject_wrong_methods():
    user = _staff_user()
    client = Client()
    client.force_login(user)

    assert client.get(reverse("portal:staff-push-notification-subscribe")).status_code == 405
    assert (
        client.get(
            reverse(
                "portal:staff-push-notification-unsubscribe",
                kwargs={"subscription_public_id": uuid4()},
            )
        ).status_code
        == 405
    )


@pytest.mark.django_db
def test_unsubscribe_delegates_uuid_ownership_check_and_propagates_denial():
    user = _staff_user()
    client = Client()
    client.force_login(user)
    foreign_public_id = uuid4()
    url = reverse(
        "portal:staff-push-notification-unsubscribe",
        kwargs={"subscription_public_id": foreign_public_id},
    )

    with patch(
        "apps.portal.views_staff_push_notifications.workshop_notification_service.unsubscribe",
        side_effect=PermissionDenied,
    ) as unsubscribe:
        response = client.post(url)

    assert response.status_code == 403
    unsubscribe.assert_called_once_with(
        actor=user,
        subscription_public_id=foreign_public_id,
        source="portal",
    )


@pytest.mark.django_db
def test_polling_baseline_events_and_empty_cursor_response():
    user = _staff_user()
    client = Client()
    client.force_login(user)
    event_public_id = str(uuid4())
    first_page = SimpleNamespace(
        cursor=event_public_id,
        events=(
            SimpleNamespace(
                public_id=event_public_id,
                event_type="workshop.order_submitted",
                created_at="2026-09-08T12:00:00+00:00",
            ),
        ),
    )
    empty_page = SimpleNamespace(cursor=event_public_id, events=())
    url = reverse("portal:staff-push-notification-events")

    with patch(
        "apps.portal.views_staff_push_notifications.workshop_notification_service.read_recent_events",
        side_effect=(first_page, empty_page),
    ):
        first_response = client.get(url)
        empty_response = client.get(url, {"cursor": event_public_id})

    assert first_response.status_code == 200
    assert first_response.json() == {
        "ok": True,
        "cursor": event_public_id,
        "events": [{"public_id": event_public_id, "created_at": "2026-09-08T12:00:00+00:00"}],
    }
    assert empty_response.status_code == 204
    assert empty_response.content == b""


def test_service_worker_is_root_scoped_no_store_and_contains_only_generic_copy():
    response = Client().get(reverse("service-worker"))
    body = response.content.decode()

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/javascript")
    assert "no-store" in response["Cache-Control"]
    assert response["Service-Worker-Allowed"] == "/"
    assert 'const ATELIER_URL = "/staff/"' in body
    assert "Nouvelle commande Atelier" in body
    assert "Une nouvelle commande est disponible." in body
    for forbidden in ("customer", "client_name", "email", "amount", "filename"):
        assert forbidden not in body.lower()


@pytest.mark.django_db
def test_dashboard_exposes_accessible_push_states_only_to_authorized_workshop_staff():
    authorized_user = _staff_user()
    authorized_client = Client()
    authorized_client.force_login(authorized_user)
    authorized_html = authorized_client.get(reverse("portal:staff-dashboard")).content.decode()

    limited_user = _staff_user(complete_permissions=False)
    limited_client = Client()
    limited_client.force_login(limited_user)
    limited_html = limited_client.get(reverse("portal:staff-dashboard")).content.decode()

    assert "Activer les alertes" in authorized_html
    assert 'aria-live="polite"' in authorized_html
    assert "data-atelier-notifications" in authorized_html
    assert 'id="atelier-dashboard-live-region"' in authorized_html
    assert "atelier-notifications.js" in authorized_html
    assert "Activer les alertes" not in limited_html


def test_atelier_notification_runtime_keeps_permission_user_initiated_and_fallback_safe():
    root = Path(__file__).resolve().parents[2]
    runtime = (root / "backend/static_src/js/atelier-notifications.js").read_text()

    assert "Notification.requestPermission()" in runtime
    assert 'addEventListener("click"' in runtime
    assert "POLL_INTERVAL_MS = 20000" in runtime
    assert 'document.addEventListener("visibilitychange", schedule)' in runtime
    assert 'if (document.hidden || root.dataset.pushState === "enabled") return' in runtime
    assert 'target: "#atelier-dashboard-live-region"' in runtime
    assert 'select: "#atelier-dashboard-live-region"' in runtime
    assert 'target: "#atelier-production-health"' in runtime
    assert 'select: "#atelier-production-health"' in runtime
    assert "atelier-production-chart-canvas" not in runtime
    assert (
        'window.preniumToast?.("Une nouvelle commande est disponible dans l’Atelier.", "info")'
        in runtime
    )
    assert "markEventSeen(publicId)" in runtime


def test_desktop_push_control_keeps_the_breadcrumb_rail_on_one_line():
    root = Path(__file__).resolve().parents[2]
    stylesheet = (root / "backend/static_src/css/entries/portal-core.css").read_text()

    assert "@media (min-width: 480px)" in stylesheet
    assert "flex-wrap: nowrap;" in stylesheet
    assert "margin-left: auto;" in stylesheet
    assert "white-space: nowrap;" in stylesheet
